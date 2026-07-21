from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import VentaFinanciada, Pago, Usuario, Lead, Interaccion
from routers.auth import require_auth, require_roles, get_user_roles
from routers.notificaciones import notificar_nueva_venta

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def calcular_proximo_vencimiento(venta: VentaFinanciada) -> Optional[datetime]:
    if not venta.fecha_primer_vencimiento:
        return None
    cuotas_pagadas = venta.cuotas_pagas or 0
    proximo = venta.fecha_primer_vencimiento + timedelta(days=30 * cuotas_pagadas)
    return proximo


def dias_atraso(venta: VentaFinanciada) -> int:
    proximo = calcular_proximo_vencimiento(venta)
    if not proximo:
        return 0
    if proximo < datetime.now():
        return (datetime.now() - proximo).days
    return 0


def venta_to_dict(v: VentaFinanciada) -> dict:
    cuotas_pendientes = max(0, (v.cantidad_cuotas or 0) - (v.cuotas_pagas or 0))
    proximo_vcto = calcular_proximo_vencimiento(v)
    atraso = dias_atraso(v)

    return {
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "superficie_m2": v.superficie_m2,
        "forma_pago": v.forma_pago or "",
        "precio_total": v.precio_total or 0,
        "anticipo": v.anticipo or 0,
        "cantidad_cuotas": v.cantidad_cuotas or 0,
        "valor_cuota": v.valor_cuota or 0,
        "fecha_inicio_plan": v.fecha_inicio_plan.isoformat() if v.fecha_inicio_plan else None,
        "fecha_primer_vencimiento": v.fecha_primer_vencimiento.isoformat() if v.fecha_primer_vencimiento else None,
        "cuotas_pagas": v.cuotas_pagas or 0,
        "cuotas_pendientes": cuotas_pendientes,
        "proximo_vencimiento": proximo_vcto.isoformat() if proximo_vcto else None,
        "monto_proxima_cuota": v.valor_cuota or 0,
        "dias_atraso": atraso,
        "asesor_apertura_id": v.asesor_apertura_id,
        "asesor_apertura_nombre": v.asesor_apertura.nombre if v.asesor_apertura else "",
        "supervisor_cierre_id": v.supervisor_cierre_id,
        "supervisor_cierre_nombre": v.supervisor_cierre.nombre if v.supervisor_cierre else "",
        "estado_plan": v.estado_plan or "ACTIVO",
        "estado_admision": v.estado_admision,
        "notas": v.notas or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
        "alerta": "ROJA" if atraso > 0 else ("AMARILLA" if proximo_vcto and (proximo_vcto - datetime.now()).days <= 3 else None),
    }


@router.get("/ventas-financiadas", response_class=HTMLResponse)
async def ventas_financiadas_page(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    usuarios = db.query(Usuario).filter(Usuario.activo == True).all()
    return templates.TemplateResponse("ventas_financiadas.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "usuarios": [{"id": u.id, "nombre": u.nombre} for u in usuarios],
    })


@router.get("/api/ventas-financiadas")
async def list_ventas_financiadas(
    estado_plan: Optional[str] = None,
    forma_pago: Optional[str] = None,
    search: Optional[str] = None,
    con_atraso: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(VentaFinanciada)
    if estado_plan:
        q = q.filter(VentaFinanciada.estado_plan == estado_plan)
    if forma_pago:
        q = q.filter(VentaFinanciada.forma_pago == forma_pago)
    if search:
        q = q.filter(VentaFinanciada.cliente_nombre.ilike(f"%{search}%"))

    ventas = q.order_by(VentaFinanciada.created_at.desc()).all()

    if con_atraso:
        ventas = [v for v in ventas if dias_atraso(v) > 0]

    return [venta_to_dict(v) for v in ventas]


@router.post("/api/ventas-financiadas")
async def create_venta_financiada(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()

    fecha_inicio = None
    fecha_primer_vcto = None
    if data.get("fecha_inicio_plan"):
        try:
            fecha_inicio = datetime.fromisoformat(data["fecha_inicio_plan"])
        except Exception:
            pass
    if data.get("fecha_primer_vencimiento"):
        try:
            fecha_primer_vcto = datetime.fromisoformat(data["fecha_primer_vencimiento"])
        except Exception:
            pass

    venta = VentaFinanciada(
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color"),
        superficie_m2=data.get("superficie_m2"),
        forma_pago=data.get("forma_pago", "PMI"),
        precio_total=data.get("precio_total", 0),
        anticipo=data.get("anticipo", 0),
        cantidad_cuotas=data.get("cantidad_cuotas", 1),
        valor_cuota=data.get("valor_cuota", 0),
        fecha_inicio_plan=fecha_inicio,
        fecha_primer_vencimiento=fecha_primer_vcto,
        cuotas_pagas=0,
        asesor_apertura_id=data.get("asesor_apertura_id") or current_user.id,
        supervisor_cierre_id=data.get("supervisor_cierre_id"),
        estado_plan=data.get("estado_plan", "ACTIVO"),
        estado_admision=data.get("estado_admision"),
        notas=data.get("notas", ""),
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    # ── A5: Auto-vincular lead por teléfono ─────────────────────────────────
    if venta.cliente_telefono:
        lead = db.query(Lead).filter(
            Lead.telefono.ilike(f"%{venta.cliente_telefono.strip()}%")
        ).order_by(Lead.created_at.desc()).first()
        if lead and lead.estado not in ["CERRADO_GANADO", "CERRADO_PERDIDO"]:
            lead.estado = "CERRADO_GANADO"
            db.add(Interaccion(
                lead_id=lead.id,
                tipo="VENTA",
                resultado="VENTA_CONCRETADA",
                notas=f"Venta financiada #{venta.id} — {venta.modelo_especifico or venta.producto}",
                asesor_id=venta.asesor_apertura_id,
            ))
            db.commit()

    # ── Notificaciones ───────────────────────────────────────────────────────
    notificar_nueva_venta(
        db,
        tipo_venta="FINANCIADA",
        cliente_nombre=venta.cliente_nombre,
        producto=venta.producto or "",
        modelo=venta.modelo_especifico or "",
        monto=venta.precio_total or 0,
        vendedor_id=venta.asesor_apertura_id,
        supervisor_id=venta.supervisor_cierre_id,
        referencia_id=venta.id,
    )
    db.commit()

    return {"id": venta.id, "ok": True}


@router.put("/api/ventas-financiadas/{venta_id}")
async def update_venta_financiada(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()

    for dt_field in ["fecha_inicio_plan", "fecha_primer_vencimiento"]:
        if dt_field in data and data[dt_field]:
            try:
                setattr(venta, dt_field, datetime.fromisoformat(data[dt_field]))
            except Exception:
                pass

    for field in ["cliente_nombre", "cliente_telefono", "cliente_localidad", "producto",
                  "modelo_especifico", "color", "superficie_m2", "forma_pago", "precio_total",
                  "anticipo", "cantidad_cuotas", "valor_cuota", "cuotas_pagas",
                  "asesor_apertura_id", "supervisor_cierre_id", "estado_plan",
                  "estado_admision", "notas"]:
        if field in data:
            setattr(venta, field, data[field])

    db.commit()
    return {"ok": True}


@router.post("/api/ventas-financiadas/{venta_id}/pago")
async def registrar_pago(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()
    pago = Pago(
        venta_financiada_id=venta_id,
        monto=data.get("monto", venta.valor_cuota or 0),
        notas=data.get("notas", ""),
    )
    db.add(pago)
    venta.cuotas_pagas = (venta.cuotas_pagas or 0) + 1

    if venta.cuotas_pagas >= venta.cantidad_cuotas:
        venta.estado_plan = "FINALIZADO"
    elif dias_atraso(venta) > 0:
        venta.estado_plan = "ACTIVO"

    db.commit()
    return {"ok": True, "cuotas_pagas": venta.cuotas_pagas}


@router.get("/api/ventas-financiadas/{venta_id}")
async def get_venta_financiada(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    return venta_to_dict(venta)
