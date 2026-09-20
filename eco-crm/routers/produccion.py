"""
Módulo de Órdenes de Producción (C-OP 1, 2, 3, 4)
  C-OP 1: Órdenes de producción formales
  C-OP 2: Panel del operario (URL con token, sin login)
  C-OP 3: Dashboard de fábrica
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    OrdenProduccion, EtapaOrden, Empleado, Usuario,
    VentaContado, VentaFinanciada, OrdenFabricaPiscina, OrdenFabricaModulo,
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_FABRICA = ["ADMIN", "COORDINADOR_OPERATIVO", "FABRICA", "ADMINISTRACION"]

ETAPAS_MODULO = ["ESTRUCTURA", "REVESTIMIENTO", "TERMINACIONES", "CONTROL"]
ETAPAS_PISCINA = ["ESTRUCTURA", "TERMINACIONES", "CONTROL"]


def _check_fabrica(current_user: Usuario, db: Session):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FABRICA):
        raise HTTPException(403, "Sin permisos")
    return roles


# ─── PÁGINAS HTML ─────────────────────────────────────────────────────────────

@router.get("/produccion", response_class=HTMLResponse)
async def produccion_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FABRICA):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/", 302)
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    return templates.TemplateResponse("produccion.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": [{"id": e.id, "nombre": e.nombre, "token": e.token_operario} for e in empleados],
    })


@router.get("/operario/{token}", response_class=HTMLResponse)
async def operario_panel(token: str, request: Request, db: Session = Depends(get_db)):
    """Panel del operario — sin login — acceso por token personal."""
    empleado = db.query(Empleado).filter(
        Empleado.token_operario == token,
        Empleado.activo == True,
    ).first()
    if not empleado:
        return HTMLResponse("<h2 style='text-align:center;margin-top:60px;font-family:sans-serif'>❌ Token inválido. Pedile el link correcto a Rodrigo.</h2>", status_code=404)

    ordenes = db.query(OrdenProduccion).filter(
        OrdenProduccion.estado.in_(["PENDIENTE", "EN_PROCESO", "CONTROL_CALIDAD"]),
    ).order_by(OrdenProduccion.prioridad.desc(), OrdenProduccion.fecha_compromiso.asc()).all()

    # Filtrar las que tienen a este empleado asignado
    mis_ordenes = []
    todas_ordenes = []
    for o in ordenes:
        try:
            ids = json.loads(o.operario_ids_json or "[]")
        except Exception:
            ids = []
        if empleado.id in ids:
            mis_ordenes.append(_orden_to_dict(o))
        else:
            todas_ordenes.append(_orden_to_dict(o))

    return templates.TemplateResponse("operario_panel.html", {
        "request": request,
        "empleado": {"id": empleado.id, "nombre": empleado.nombre, "token": token},
        "mis_ordenes": mis_ordenes,
        "todas_ordenes": todas_ordenes,
    })


# ─── API C-OP 1: ÓRDENES ──────────────────────────────────────────────────────

@router.get("/api/produccion/ordenes")
async def list_ordenes(
    estado: Optional[str] = None,
    prioridad: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    q = db.query(OrdenProduccion)
    if estado:
        q = q.filter(OrdenProduccion.estado == estado)
    if prioridad:
        q = q.filter(OrdenProduccion.prioridad == prioridad)
    ordenes = q.order_by(
        OrdenProduccion.prioridad.desc(),
        OrdenProduccion.created_at.desc()
    ).all()
    return [_orden_to_dict(o) for o in ordenes]


@router.get("/api/produccion/siguiente-numero")
async def siguiente_numero(db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    _check_fabrica(current_user, db)
    anio = datetime.now().year
    prefix = f"OP-{anio}-"
    ultima = db.query(OrdenProduccion).filter(
        OrdenProduccion.numero.like(f"{prefix}%")
    ).order_by(OrdenProduccion.id.desc()).first()
    if ultima:
        try:
            num = int(ultima.numero.split("-")[-1]) + 1
        except Exception:
            num = 1
    else:
        num = 1
    return {"numero": f"{prefix}{num:03d}"}


@router.post("/api/produccion/ordenes")
async def create_orden(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    data = await request.json()

    fecha_compromiso = None
    if data.get("fecha_compromiso"):
        try:
            fecha_compromiso = datetime.fromisoformat(data["fecha_compromiso"])
        except Exception:
            pass

    # Auto-generar número si no viene
    numero = data.get("numero") or (await siguiente_numero(db, current_user))["numero"]

    orden = OrdenProduccion(
        numero=numero,
        producto=data.get("producto", "MODULO"),
        modelo=data.get("modelo", ""),
        color=data.get("color", ""),
        superficie_m2=data.get("superficie_m2"),
        aberturas_json=json.dumps(data.get("aberturas", {})),
        cliente_nombre=data.get("cliente_nombre", ""),
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        prioridad=data.get("prioridad", "NORMAL"),
        fecha_compromiso=fecha_compromiso,
        operario_ids_json=json.dumps(data.get("operario_ids", [])),
        estado="PENDIENTE",
        etapa_actual="ESTRUCTURA",
        notas=data.get("notas", ""),
        mensaje_operario=data.get("mensaje_operario", ""),
        created_by_id=current_user.id,
    )
    db.add(orden)
    db.commit()
    db.refresh(orden)
    return {"id": orden.id, "numero": orden.numero, "ok": True}


@router.get("/api/produccion/ordenes/{orden_id}")
async def get_orden(
    orden_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    return _orden_to_dict(orden, include_etapas=True)


@router.put("/api/produccion/ordenes/{orden_id}")
async def update_orden(
    orden_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    data = await request.json()

    if "fecha_compromiso" in data and data["fecha_compromiso"]:
        try:
            orden.fecha_compromiso = datetime.fromisoformat(data["fecha_compromiso"])
        except Exception:
            pass

    for field in ["estado", "etapa_actual", "prioridad", "notas", "mensaje_operario",
                  "modelo", "color", "superficie_m2", "cliente_nombre"]:
        if field in data:
            setattr(orden, field, data[field])

    if "operario_ids" in data:
        orden.operario_ids_json = json.dumps(data["operario_ids"])

    db.commit()

    # Notificar si se termina
    if data.get("estado") == "TERMINADO":
        _notificar_orden_terminada(db, orden)

    return {"ok": True}


@router.post("/api/produccion/ordenes/{orden_id}/etapa")
async def registrar_etapa(
    orden_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Público para operarios — registran avance por etapa (desde panel con token)."""
    data = await request.json()
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")

    etapa = EtapaOrden(
        orden_id=orden_id,
        etapa=data.get("etapa", orden.etapa_actual),
        estado=data.get("estado", "EN_PROCESO"),
        notas=data.get("notas", ""),
        foto_url=data.get("foto_url"),
        registrado_por_nombre=data.get("registrado_por_nombre", ""),
        empleado_id=data.get("empleado_id"),
    )
    db.add(etapa)

    # Avanzar etapa si está terminada
    if data.get("estado") == "TERMINADO":
        producto = orden.producto.upper()
        etapas = ETAPAS_MODULO if producto in ("MODULO", "COMBO") else ETAPAS_PISCINA
        idx = etapas.index(orden.etapa_actual) if orden.etapa_actual in etapas else 0
        if idx + 1 < len(etapas):
            orden.etapa_actual = etapas[idx + 1]
            if etapas[idx + 1] == "CONTROL":
                orden.estado = "CONTROL_CALIDAD"
            else:
                orden.estado = "EN_PROCESO"
        else:
            orden.estado = "TERMINADO"
            _notificar_orden_terminada(db, orden)
    elif data.get("estado") == "EN_PROCESO" and orden.estado == "PENDIENTE":
        orden.estado = "EN_PROCESO"

    db.commit()
    return {"ok": True, "etapa_actual": orden.etapa_actual, "estado": orden.estado}


@router.post("/api/produccion/empleados/{emp_id}/generar-token")
async def generar_token_operario(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin permisos")
    emp = db.query(Empleado).filter(Empleado.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    emp.token_operario = str(uuid.uuid4())
    db.commit()
    return {"token": emp.token_operario, "url": f"/operario/{emp.token_operario}"}


# ─── API C-OP 3: DASHBOARD ────────────────────────────────────────────────────

@router.get("/api/produccion/dashboard")
async def dashboard_fabrica(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    ahora = datetime.now()

    activas = db.query(OrdenProduccion).filter(
        OrdenProduccion.estado.in_(["PENDIENTE", "EN_PROCESO", "CONTROL_CALIDAD"])
    ).order_by(OrdenProduccion.prioridad.desc(), OrdenProduccion.fecha_compromiso.asc()).all()

    terminadas_hoy = db.query(OrdenProduccion).filter(
        OrdenProduccion.estado == "TERMINADO",
        OrdenProduccion.updated_at >= ahora.replace(hour=0, minute=0, second=0),
    ).count()

    atrasadas = [o for o in activas if o.fecha_compromiso and o.fecha_compromiso < ahora]

    return {
        "activas": [_orden_to_dict(o) for o in activas],
        "terminadas_hoy": terminadas_hoy,
        "total_activas": len(activas),
        "urgentes": len([o for o in activas if o.prioridad == "URGENTE"]),
        "atrasadas": len(atrasadas),
        "por_estado": {
            "PENDIENTE": len([o for o in activas if o.estado == "PENDIENTE"]),
            "EN_PROCESO": len([o for o in activas if o.estado == "EN_PROCESO"]),
            "CONTROL_CALIDAD": len([o for o in activas if o.estado == "CONTROL_CALIDAD"]),
        }
    }


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _orden_to_dict(o: OrdenProduccion, include_etapas: bool = False) -> dict:
    try:
        operario_ids = json.loads(o.operario_ids_json or "[]")
    except Exception:
        operario_ids = []
    try:
        aberturas = json.loads(o.aberturas_json or "{}")
    except Exception:
        aberturas = {}

    result = {
        "id": o.id,
        "numero": o.numero,
        "producto": o.producto,
        "modelo": o.modelo,
        "color": o.color,
        "superficie_m2": o.superficie_m2,
        "aberturas": aberturas,
        "cliente_nombre": o.cliente_nombre,
        "prioridad": o.prioridad,
        "fecha_compromiso": o.fecha_compromiso.isoformat() if o.fecha_compromiso else None,
        "operario_ids": operario_ids,
        "estado": o.estado,
        "etapa_actual": o.etapa_actual,
        "notas": o.notas,
        "mensaje_operario": o.mensaje_operario,
        "created_at": o.created_at.isoformat() if o.created_at else "",
        "dias_restantes": (o.fecha_compromiso - datetime.now()).days if o.fecha_compromiso else None,
    }
    if include_etapas:
        result["etapas"] = [{
            "id": e.id,
            "etapa": e.etapa,
            "estado": e.estado,
            "notas": e.notas,
            "foto_url": e.foto_url,
            "registrado_por_nombre": e.registrado_por_nombre,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        } for e in o.etapas]
    return result


def _notificar_orden_terminada(db: Session, orden: OrdenProduccion):
    """Notifica a Rodrigo por WA cuando una orden termina.
    También sincroniza OrdenFabricaPiscina/Modulo vinculada a TERMINADA para que
    Logística vea fab_lista=True en el calendario sin intervención manual.
    """
    # Sincronizar OrdenFabrica vinculada → TERMINADA
    try:
        venta_id = orden.venta_contado_id or orden.venta_financiada_id
        if venta_id:
            producto = (orden.producto or "").upper()
            if producto in ("PISCINA", "COMBO"):
                fab = db.query(OrdenFabricaPiscina).filter(
                    OrdenFabricaPiscina.venta_contado_id == orden.venta_contado_id
                    if orden.venta_contado_id else
                    OrdenFabricaPiscina.venta_financiada_id == orden.venta_financiada_id
                ).first()
                if fab and fab.estado == "EN_ESPERA":
                    fab.estado = "TERMINADA"
            if producto in ("MODULO", "COMBO"):
                fab_m = db.query(OrdenFabricaModulo).filter(
                    OrdenFabricaModulo.venta_contado_id == orden.venta_contado_id
                    if orden.venta_contado_id else
                    OrdenFabricaModulo.venta_financiada_id == orden.venta_financiada_id
                ).first()
                if fab_m and fab_m.estado == "EN_ESPERA":
                    fab_m.estado = "TERMINADA"
            db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PROD→FAB SYNC] {e}")

    # Notificar a Rodrigo por WA
    try:
        from utils.whatsapp import notificar_rodrigo
        msg = (
            f"✅ *Orden terminada* — {orden.numero}\n"
            f"📦 {orden.producto}: {orden.modelo}\n"
            f"👤 Cliente: {orden.cliente_nombre}\n"
            f"🏭 Lista para despacho"
        )
        notificar_rodrigo(db, msg)
    except Exception:
        pass
