"""
API del circuito comercial (contado / financiación / Admisión) y del panel
económico del propietario. Los permisos se verifican acá, no en los prompts.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ComisionPropietario, ExpedienteEvento, ExpedienteFinanciacion, Usuario, VentaContado
from routers.auth import get_user_roles, require_auth
from utils import circuito_comercial as cc
from utils import comisiones_propietario as cp
from utils.api_keys import api_key_valida
from utils.motor_tareas import AGENTES_EMPRESA, ErrorMotor
from utils.origen import es_agente_ia

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _err(e: ErrorMotor):
    raise HTTPException(e.codigo, str(e))


def _agente(request: Request) -> str:
    """Llamada del sistema de agentes: API key + identidad del multiagente + agente que actúa."""
    from utils.origen import _clave_de
    if not api_key_valida(_clave_de(request)):           # la identidad no reemplaza a la clave
        raise HTTPException(401, "API key inválida")
    if not es_agente_ia(request):
        raise HTTPException(403, "Operación exclusiva del sistema de agentes IA")
    agente = (request.headers.get("X-Agente") or "").strip().lower()
    if agente not in AGENTES_EMPRESA:
        raise HTTPException(403, "Falta el agente que realiza la operación (X-Agente)")
    return agente


def _propietario(user: Usuario = Depends(require_auth)) -> Usuario:
    """Panel personal: solo el rol PROPIETARIO (un ADMIN de socio no ve tus ingresos)."""
    if getattr(user, "es_agente_ia", False) or getattr(user, "aliado_codigo", None) or \
            "PROPIETARIO" not in get_user_roles(user):
        raise HTTPException(403, "Información reservada al propietario")
    return user


def _admision(user: Usuario = Depends(require_auth)) -> Usuario:
    if getattr(user, "es_agente_ia", False) or getattr(user, "aliado_codigo", None) or \
            "ADMISION" not in get_user_roles(user):
        raise HTTPException(403, "Reservado al Departamento de Admisión")
    return user


class CierreContado(BaseModel):
    lead_id: int
    producto: str
    modelo: str
    precio: float
    color: Optional[str] = None
    cliente_nombre: str
    cliente_localidad: str
    cliente_domicilio: str
    aceptacion_cliente: str
    forma_pago: str = "CONTADO"


class Evidencia(BaseModel):
    evidencia: str
    monto: Optional[float] = None
    fecha: Optional[datetime] = None


class Apertura(BaseModel):
    producto: str
    cliente_nombre: str
    cliente_telefono: str = ""
    modelo: str = ""
    lead_id: Optional[int] = None
    valor_cuota_estimado: Optional[float] = None
    datos_apertura: dict = {}


class CambioExpediente(BaseModel):
    estado: str
    detalle: str = ""
    venta_financiada_id: Optional[int] = None
    videollamada_id: Optional[int] = None


class Motivo(BaseModel):
    motivo: str


class NuevoObjetivo(BaseModel):
    periodo: str
    indicador: str
    valor: float
    producto: str = ""
    canal: str = ""
    nota: str = ""


class NuevoGasto(BaseModel):
    tipo: str
    fecha: date
    monto: float
    campana: str = ""
    producto: str = ""
    canal: str = ""
    nota: str = ""


def _venta_dict(v: VentaContado) -> dict:
    return {"id": v.id, "cliente_nombre": v.cliente_nombre, "producto": v.producto, "modelo": v.modelo_especifico,
            "precio_final": v.precio_final, "circuito_estado": cc.estado_contado_efectivo(v), "cerrada_por": v.cerrada_por,
            "lead_id": v.lead_id, "entrega_confirmada_at": v.entrega_confirmada_at.isoformat() if v.entrega_confirmada_at else None,
            "cobro_estado": v.cobro_estado, "created_at": v.created_at.isoformat() if v.created_at else None}


# ── Agentes IA ────────────────────────────────────────────────────────────────

@router.post("/api/comercial/contado/cierres")
def ia_cerrar_contado(body: CierreContado, request: Request, db: Session = Depends(get_db)):
    agente = _agente(request)
    try:
        v, creada = cc.cerrar_contado_ia(db, agente, body.model_dump())
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "creada": creada, "venta": _venta_dict(v)}


@router.post("/api/comercial/contado/{venta_id}/solicitar-entrega")
def ia_solicitar_entrega(venta_id: int, request: Request, db: Session = Depends(get_db)):
    agente = _agente(request)
    v = db.get(VentaContado, venta_id)
    if not v or v.cerrada_por != f"agente:{agente}":
        raise HTTPException(404, "Venta inexistente o cerrada por otro agente")
    try:
        cc.solicitar_entrega(db, v, f"agente:{agente}")
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "venta": _venta_dict(v)}


@router.post("/api/comercial/financiacion/expedientes")
def ia_abrir_expediente(body: Apertura, request: Request, db: Session = Depends(get_db)):
    agente = _agente(request)
    try:
        e = cc.abrir_expediente(db, body.model_dump(), agente=agente)
    except ErrorMotor as e2:
        _err(e2)
    return {"ok": True, "expediente": cc.expediente_dict(e, con_datos=False)}


@router.post("/api/comercial/financiacion/expedientes/{exp_id}/estado")
def ia_estado_expediente(exp_id: int, body: CambioExpediente, request: Request, db: Session = Depends(get_db)):
    agente = _agente(request)
    e = db.get(ExpedienteFinanciacion, exp_id)
    if not e:
        raise HTTPException(404, "Expediente inexistente")
    try:
        cc.cambiar_estado_expediente(db, e, body.estado, agente=agente, detalle=body.detalle,
                                     videollamada_id=body.videollamada_id)
    except ErrorMotor as e2:
        _err(e2)
    return {"ok": True, "expediente": cc.expediente_dict(e, con_datos=False)}


# ── Personas: contado ─────────────────────────────────────────────────────────

@router.get("/api/comercial/contado")
def listar_contado(estado: Optional[str] = None, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    q = db.query(VentaContado).filter(VentaContado.circuito_estado.isnot(None))
    if estado:
        q = q.filter(VentaContado.circuito_estado == estado.upper())
    return {"ventas": [_venta_dict(v) for v in q.order_by(VentaContado.id.desc()).limit(200)]}


@router.post("/api/comercial/contado/{venta_id}/confirmar-entrega")
def confirmar_entrega(venta_id: int, body: Evidencia, request: Request, db: Session = Depends(get_db),
                      user: Usuario = Depends(require_auth)):
    if es_agente_ia(request):
        raise HTTPException(403, "Los agentes IA no confirman entregas")
    v = db.get(VentaContado, venta_id)
    if not v:
        raise HTTPException(404, "Venta inexistente")
    try:
        cc.confirmar_entrega(db, v, user, body.evidencia, body.fecha)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "venta": _venta_dict(v)}


@router.post("/api/comercial/contado/{venta_id}/confirmar-cobro")
def confirmar_cobro(venta_id: int, body: Evidencia, request: Request, db: Session = Depends(get_db),
                    user: Usuario = Depends(require_auth)):
    if es_agente_ia(request):
        raise HTTPException(403, "Los agentes IA no registran cobros")
    v = db.get(VentaContado, venta_id)
    if not v:
        raise HTTPException(404, "Venta inexistente")
    try:
        cc.confirmar_cobro(db, v, user, body.evidencia, body.monto)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "venta": _venta_dict(v)}


@router.post("/api/comercial/contado/{venta_id}/cobro-no-concretado")
def cobro_no_concretado(venta_id: int, body: Motivo, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    v = db.get(VentaContado, venta_id)
    if not v:
        raise HTTPException(404, "Venta inexistente")
    try:
        cc.cobro_no_concretado(db, v, user, body.motivo)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "venta": _venta_dict(v)}


# ── Admisión (humana) ─────────────────────────────────────────────────────────

@router.get("/api/admision/expedientes")
def admision_listar(estado: Optional[str] = None, db: Session = Depends(get_db), _: Usuario = Depends(_admision)):
    q = db.query(ExpedienteFinanciacion)
    if estado:
        q = q.filter(ExpedienteFinanciacion.estado == estado.upper())
    return {"expedientes": [cc.expediente_dict(e) for e in q.order_by(ExpedienteFinanciacion.id.desc()).limit(200)]}


@router.get("/api/admision/expedientes/{exp_id}")
def admision_ver(exp_id: int, db: Session = Depends(get_db), _: Usuario = Depends(_admision)):
    e = db.get(ExpedienteFinanciacion, exp_id)
    if not e:
        raise HTTPException(404, "Expediente inexistente")
    ev = db.query(ExpedienteEvento).filter_by(expediente_id=e.id).order_by(ExpedienteEvento.id).all()
    return cc.expediente_dict(e, ev)


@router.post("/api/admision/expedientes/{exp_id}/estado")
def admision_decidir(exp_id: int, body: CambioExpediente, request: Request, db: Session = Depends(get_db),
                     user: Usuario = Depends(_admision)):
    if es_agente_ia(request):
        raise HTTPException(403, "Los agentes IA no deciden financiaciones")
    e = db.get(ExpedienteFinanciacion, exp_id)
    if not e:
        raise HTTPException(404, "Expediente inexistente")
    try:
        cc.cambiar_estado_expediente(db, e, body.estado, usuario=user, detalle=body.detalle,
                                     venta_financiada_id=body.venta_financiada_id, videollamada_id=body.videollamada_id)
    except ErrorMotor as e2:
        _err(e2)
    return {"ok": True, "expediente": cc.expediente_dict(e)}


@router.post("/api/admision/expedientes/{exp_id}/cuotas-iniciales")
def admision_cuotas_iniciales(exp_id: int, body: Evidencia, request: Request, db: Session = Depends(get_db),
                              user: Usuario = Depends(require_auth)):
    if es_agente_ia(request):
        raise HTTPException(403, "Los agentes IA no registran pagos")
    e = db.get(ExpedienteFinanciacion, exp_id)
    if not e:
        raise HTTPException(404, "Expediente inexistente")
    try:
        cc.confirmar_cuotas_iniciales(db, e, user, body.evidencia, body.fecha)
    except ErrorMotor as e2:
        _err(e2)
    return {"ok": True, "expediente": cc.expediente_dict(e)}


@router.get("/api/admision/resumen")
def admision_resumen(db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    """Indicadores agregados (sin datos personales): los puede ver dirección."""
    from sqlalchemy import func
    filas = db.query(ExpedienteFinanciacion.estado, func.count(ExpedienteFinanciacion.id)).group_by(
        ExpedienteFinanciacion.estado).all()
    return {"por_estado": {e: n for e, n in filas}}


# ── Panel del propietario ─────────────────────────────────────────────────────

@router.get("/api/propietario/panel")
def propietario_panel(periodo: Optional[str] = None, db: Session = Depends(get_db), _: Usuario = Depends(_propietario)):
    try:
        return cp.panel(db, periodo or datetime.utcnow().strftime("%Y-%m"))
    except ErrorMotor as e:
        _err(e)


@router.get("/api/propietario/comisiones")
def propietario_comisiones(db: Session = Depends(get_db), _: Usuario = Depends(_propietario)):
    return {"comisiones": [cp.comision_dict(c) for c in
                           db.query(ComisionPropietario).order_by(ComisionPropietario.id.desc()).limit(500)]}


@router.post("/api/propietario/comisiones/{comision_id}/cobrada")
def propietario_cobrada(comision_id: int, body: Evidencia, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        return {"ok": True, "comision": cp.comision_dict(cp.marcar_cobrada(db, comision_id, user.id, body.evidencia, body.fecha))}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/propietario/comisiones/{comision_id}/anular")
def propietario_anular(comision_id: int, body: Motivo, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        return {"ok": True, "comision": cp.comision_dict(cp.anular(db, comision_id, user.id, body.motivo))}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/propietario/objetivos")
def propietario_objetivo(body: NuevoObjetivo, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        o = cp.fijar_objetivo(db, periodo=body.periodo, indicador=body.indicador, valor=body.valor, usuario_id=user.id,
                              producto=body.producto, canal=body.canal, nota=body.nota)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "objetivo": {"id": o.id, "version": o.version, "valor": o.valor}}


@router.post("/api/propietario/gastos")
def propietario_gasto(body: NuevoGasto, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        g = cp.registrar_gasto(db, tipo=body.tipo, fecha=body.fecha, monto=body.monto, usuario_id=user.id,
                               campana=body.campana, producto=body.producto, canal=body.canal, nota=body.nota)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "gasto": {"id": g.id, "tipo": g.tipo, "monto": g.monto}}
