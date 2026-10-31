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
    precio: Optional[float] = None                 # módulos: precio de catálogo
    precio_final_acordado: Optional[float] = None  # piscinas: precio final único cotizado por el servidor
    color: Optional[str] = None
    cliente_nombre: str
    cliente_localidad: str
    cliente_provincia: Optional[str] = None
    cliente_domicilio: Optional[str] = None
    fecha_entrega_solicitada: Optional[str] = None
    aceptacion_cliente: str
    forma_pago: str = "CONTADO"


class PedidoCotizacion(BaseModel):
    modelo: str
    localidad: str
    provincia: str = ""
    direccion: str = ""
    reserva_fecha: bool = False


class NuevaDistancia(BaseModel):
    localidad: str
    provincia: str = ""
    direccion: str = ""
    km_ida: float
    fuente: str


class NuevaPromocion(BaseModel):
    nombre: str
    valor: float
    desde: date
    hasta: date
    producto: str = "PISCINA"
    requiere_reserva_fecha: bool = True
    nota: str = ""


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
            "precio_final": v.precio_final, "precio_total_acordado": v.precio_total_acordado,
            "flete": v.flete_calculado, "descuento_flete": v.descuento_flete,
            "fecha_entrega_solicitada": v.fecha_entrega_solicitada.isoformat() if v.fecha_entrega_solicitada else None,
            "circuito_estado": cc.estado_contado_efectivo(v), "cerrada_por": v.cerrada_por,
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


@router.post("/api/comercial/contado/cotizar")
def ia_cotizar(body: PedidoCotizacion, request: Request, db: Session = Depends(get_db)):
    """Cotización del servidor: precio final único + desglose interno. Nunca inventa distancias ni promos."""
    _agente(request)
    from utils.cotizacion import cotizar_piscina
    return cotizar_piscina(db, body.modelo, body.localidad, body.provincia, body.reserva_fecha,
                           direccion=body.direccion)


def _socio(request: Request, db: Session = Depends(get_db)):
    from routers.socios import require_socio
    return require_socio(request, db)


@router.post("/api/socio/cotizar")
def cotizar_socio(body: PedidoCotizacion, db: Session = Depends(get_db), _=Depends(_socio)):
    """Panel de socios: misma herramienta de cotización (distancia por ruta, tarifas, promociones)."""
    from utils.cotizacion import cotizar_piscina
    return cotizar_piscina(db, body.modelo, body.localidad, body.provincia, body.reserva_fecha,
                           direccion=body.direccion)


@router.post("/api/comercial/cotizar")
def cotizar_humano(body: PedidoCotizacion, db: Session = Depends(get_db), user: Usuario = Depends(require_auth)):
    """La misma herramienta para vendedores humanos: precio final único + detalle interno."""
    from utils.cotizacion import cotizar_piscina
    return cotizar_piscina(db, body.modelo, body.localidad, body.provincia, body.reserva_fecha,
                           direccion=body.direccion)


# ── Personas: distancias verificadas y promociones autorizadas ───────────────

def _interno(user: Usuario = Depends(require_auth)) -> Usuario:
    if getattr(user, "es_agente_ia", False) or getattr(user, "aliado_codigo", None) or \
            not (set(get_user_roles(user)) & {"ADMIN", "LOGISTICA", "COORDINADOR_OPERATIVO", "PROPIETARIO"}):
        raise HTTPException(403, "Reservado al equipo interno (administración/logística)")
    return user


@router.get("/api/comercial/distancias")
def listar_distancias(db: Session = Depends(get_db), _: Usuario = Depends(_interno)):
    from database.models import DistanciaLocalidad
    return {"distancias": [{"id": x.id, "tipo": x.tipo, "localidad": x.localidad, "provincia": x.provincia,
                            "destino": x.destino_texto, "origen": x.origen_texto, "km_ida": x.km_ida,
                            "proveedor": x.proveedor, "estado": x.estado, "ruta": x.ruta_ref, "fuente": x.fuente,
                            "actualizado_at": x.actualizado_at.isoformat() if x.actualizado_at else None}
                           for x in db.query(DistanciaLocalidad).order_by(DistanciaLocalidad.localidad)]}


@router.post("/api/comercial/distancias")
def cargar_distancia(body: NuevaDistancia, db: Session = Depends(get_db), user: Usuario = Depends(_interno)):
    from utils.cotizacion import cargar_distancia as _cargar
    try:
        x = _cargar(db, body.localidad, body.provincia, body.km_ida, body.fuente, user.id, body.direccion)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "distancia": {"id": x.id, "localidad": x.localidad, "km_ida": x.km_ida}}


@router.get("/api/comercial/promociones")
def listar_promociones(db: Session = Depends(get_db), _: Usuario = Depends(_interno)):
    from database.models import PromocionComercial
    return {"promociones": [{"id": p.id, "nombre": p.nombre, "tipo": p.tipo, "valor": p.valor, "producto": p.producto,
                             "desde": p.desde.isoformat(), "hasta": p.hasta.isoformat(), "activa": bool(p.activa),
                             "requiere_reserva_fecha": bool(p.requiere_reserva_fecha)}
                            for p in db.query(PromocionComercial).order_by(PromocionComercial.id.desc())]}


@router.post("/api/comercial/promociones")
def crear_promocion(body: NuevaPromocion, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    """Solo el propietario autoriza promociones (la IA las aplica, no las crea)."""
    from utils.cotizacion import crear_promocion as _crear
    try:
        p = _crear(db, nombre=body.nombre, valor=body.valor, desde=body.desde, hasta=body.hasta, usuario_id=user.id,
                   producto=body.producto.upper(), requiere_reserva_fecha=body.requiere_reserva_fecha, nota=body.nota)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "promocion": {"id": p.id, "nombre": p.nombre}}


@router.post("/api/comercial/promociones/{promo_id}/desactivar")
def desactivar_promocion(promo_id: int, db: Session = Depends(get_db), _: Usuario = Depends(_propietario)):
    from database.models import PromocionComercial
    p = db.get(PromocionComercial, promo_id)
    if not p:
        raise HTTPException(404, "Promoción inexistente")
    p.activa = False
    db.commit()
    return {"ok": True}


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
