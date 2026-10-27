"""
Endpoints para organizadores — gestión del equipo, leads, ventas y videollamadas.
Solo accesibles por socios con es_organizador = True.
"""
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Aliado, Lead, VentaContado, Videollamada
from routers.socios import require_socio

router = APIRouter()


def _require_org(socio: Aliado) -> Aliado:
    if not socio.es_organizador:
        raise HTTPException(403, "Solo organizadores pueden acceder a esta función")
    return socio


def _codigos_equipo(socio: Aliado, db: Session) -> list[str]:
    asesores = db.query(Aliado.codigo).filter(Aliado.organizacion_codigo == socio.codigo).all()
    return [socio.codigo] + [a.codigo for a in asesores]


# ── Estructura ─────────────────────────────────────────────────────────────────

@router.get("/api/organizador/estructura")
async def org_estructura(socio: Aliado = Depends(require_socio), db: Session = Depends(get_db)):
    _require_org(socio)
    asesores = (
        db.query(Aliado)
        .filter(Aliado.organizacion_codigo == socio.codigo, Aliado.estado == "activo")
        .order_by(Aliado.nombre)
        .all()
    )
    hace_30 = datetime.now(timezone.utc) - timedelta(days=30)
    result = []
    for a in asesores:
        ventas_mes = db.query(VentaContado).filter(
            VentaContado.aliado_codigo == a.codigo,
            VentaContado.created_at >= hace_30,
        ).count()
        leads_activos = db.query(Lead).filter(
            Lead.aliado_codigo == a.codigo,
            Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]),
        ).count()
        result.append({
            "codigo": a.codigo, "nombre": a.nombre, "zona": a.zona or "",
            "telefono": a.telefono or "", "verificado": bool(a.perfil_completo),
            "ventas_mes": ventas_mes, "leads_activos": leads_activos,
        })
    return {"organizador": socio.codigo, "socios": result}


# ── Leads ──────────────────────────────────────────────────────────────────────

@router.get("/api/organizador/leads")
async def org_leads(
    asignado_a: Optional[str] = None,
    estado: Optional[str] = None,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    codigos = _codigos_equipo(socio, db)
    q = db.query(Lead).filter(Lead.aliado_codigo.in_(codigos))
    if asignado_a:
        q = q.filter(Lead.aliado_codigo == asignado_a.upper())
    if estado:
        q = q.filter(Lead.estado == estado)
    leads = q.order_by(Lead.created_at.desc()).limit(500).all()
    return {"total": len(leads), "leads": [
        {
            "id": l.id, "nombre": l.nombre, "telefono": l.telefono,
            "localidad": l.localidad or "", "producto_interes": l.producto_interes or "SIN_DEFINIR",
            "forma_pago": l.forma_pago or "SIN_DEFINIR", "estado": l.estado or "NUEVO",
            "etiqueta_color": l.etiqueta_color or "", "aliado_codigo": l.aliado_codigo or "",
            "created_at": l.created_at.isoformat() if l.created_at else "",
        }
        for l in leads
    ]}


@router.post("/api/organizador/leads")
async def org_crear_lead(
    request: Request,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    data = await request.json()
    nombre = (data.get("nombre") or "").strip()
    telefono = (data.get("telefono") or "").strip()
    if not nombre or not telefono:
        raise HTTPException(400, "nombre y telefono son obligatorios")
    aliado_codigo = (data.get("aliado_codigo") or socio.codigo).strip().upper()
    codigos = _codigos_equipo(socio, db)
    if aliado_codigo not in codigos:
        raise HTTPException(400, "El asesor destino no pertenece a tu organización")
    lead = Lead(
        nombre=nombre, telefono=telefono,
        localidad=(data.get("localidad") or "").strip(),
        producto_interes=(data.get("producto_interes") or "SIN_DEFINIR").upper(),
        origen="ORGANIZADOR", estado="NUEVO",
        aliado_codigo=aliado_codigo,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return {"ok": True, "id": lead.id}


@router.put("/api/organizador/leads/{lead_id}/reasignar")
async def org_reasignar_lead(
    lead_id: int,
    request: Request,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    codigos = _codigos_equipo(socio, db)
    if lead.aliado_codigo not in codigos:
        raise HTTPException(403, "Este lead no pertenece a tu organización")
    data = await request.json()
    nuevo = (data.get("aliado_codigo") or "").strip().upper()
    if nuevo not in codigos:
        raise HTTPException(400, "El asesor destino no pertenece a tu organización")
    lead.aliado_codigo = nuevo
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lead.notas = (lead.notas or "") + f"\n[{ts}] 🔀 Reasignado a {nuevo} por org. {socio.codigo}"
    db.commit()
    return {"ok": True, "aliado_codigo": nuevo}


@router.delete("/api/organizador/leads/{lead_id}")
async def org_eliminar_lead(
    lead_id: int,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    codigos = _codigos_equipo(socio, db)
    if lead.aliado_codigo not in codigos:
        raise HTTPException(403, "Este lead no pertenece a tu organización")
    db.delete(lead)
    db.commit()
    return {"ok": True}


# ── Ventas ─────────────────────────────────────────────────────────────────────

@router.get("/api/organizador/ventas")
async def org_ventas(
    periodo_dias: int = 30,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    codigos = _codigos_equipo(socio, db)
    desde = datetime.now(timezone.utc) - timedelta(days=periodo_dias)
    ventas = (
        db.query(VentaContado)
        .filter(VentaContado.aliado_codigo.in_(codigos), VentaContado.created_at >= desde)
        .order_by(VentaContado.created_at.desc())
        .all()
    )
    return {"total": len(ventas), "ventas": [
        {
            "id": v.id, "cliente_nombre": v.cliente_nombre, "aliado_codigo": v.aliado_codigo,
            "producto": v.producto or "", "modelo_especifico": v.modelo_especifico or "",
            "precio_final": v.precio_final or 0,
            "created_at": v.created_at.isoformat() if v.created_at else "",
        }
        for v in ventas
    ]}


@router.post("/api/organizador/ventas/contado")
async def org_crear_venta_contado(
    request: Request,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    data = await request.json()
    aliado_codigo = (data.get("aliado_codigo") or socio.codigo).strip().upper()
    codigos = _codigos_equipo(socio, db)
    if aliado_codigo not in codigos:
        raise HTTPException(400, "El asesor destino no pertenece a tu organización")
    venta = VentaContado(
        cliente_nombre=(data.get("cliente_nombre") or "").strip(),
        cliente_telefono=(data.get("cliente_telefono") or "").strip(),
        producto=(data.get("producto") or "").strip().upper(),
        modelo_especifico=(data.get("modelo_especifico") or "").strip(),
        precio_final=float(data.get("precio_final") or 0),
        aliado_codigo=aliado_codigo,
        estado="nueva",
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)
    return {"ok": True, "id": venta.id}


# ── Videollamadas ──────────────────────────────────────────────────────────────

def _vl_dict(v: Videollamada) -> dict:
    return {
        "id": v.id,
        "cliente_nombre": v.cliente_nombre or "",
        "cliente_telefono": v.cliente_telefono or "",
        "producto_interes": v.producto_interes or "",
        "forma_pago": v.forma_pago or "",
        "modelo_especifico": v.modelo_especifico or "",
        "cantidad_cuotas": v.cantidad_cuotas,
        "aliado_codigo": v.aliado_codigo or "",
        "fecha_hora": v.fecha_hora.isoformat() if v.fecha_hora else None,
        "estado": v.estado or "AGENDADA",
        "resultado": v.resultado or "PENDIENTE",
        "notas": v.notas or "",
        "devolucion": v.devolucion or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


@router.get("/api/organizador/videollamadas")
async def org_videollamadas(
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    try:
        codigos = _codigos_equipo(socio, db)
        codigos_validos = [c for c in codigos if c]  # elimina None
        vls = (
            db.query(Videollamada)
            .filter(Videollamada.aliado_codigo.in_(codigos_validos))
            .order_by(Videollamada.fecha_hora.asc())
            .limit(200)
            .all()
        )
        return {"total": len(vls), "videollamadas": [_vl_dict(v) for v in vls]}
    except Exception as exc:
        log.error("[org_videollamadas] %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, detail=f"Error al cargar VL: {exc}")


@router.put("/api/organizador/videollamadas/{vl_id}/resultado")
async def org_vl_resultado(
    vl_id: int,
    request: Request,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    """El organizador registra estado y resultado de una VL de su equipo."""
    _require_org(socio)
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    codigos = _codigos_equipo(socio, db)
    if vl.aliado_codigo not in codigos:
        raise HTTPException(403, "No pertenece a tu organización")
    data = await request.json()
    if "estado" in data:
        vl.estado = data["estado"]
    if "resultado" in data:
        vl.resultado = data["resultado"]
    if data.get("notas"):
        ts = datetime.now().strftime("%d/%m %H:%M")
        vl.notas = (vl.notas or "") + f"\n[{ts}] {data['notas']}"
    db.commit()
    return {"ok": True}


@router.put("/api/organizador/videollamadas/{vl_id}/devolucion")
async def org_vl_devolucion(
    vl_id: int,
    request: Request,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    """El organizador registra la devolución de la VL para que el asesor la vea en su panel."""
    _require_org(socio)
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    codigos = _codigos_equipo(socio, db)
    if vl.aliado_codigo not in codigos:
        raise HTTPException(403, "No pertenece a tu organización")
    data = await request.json()
    vl.devolucion = (data.get("devolucion") or "").strip()
    db.commit()
    return {"ok": True}


@router.delete("/api/organizador/videollamadas/{vl_id}")
async def org_eliminar_vl(
    vl_id: int,
    socio: Aliado = Depends(require_socio),
    db: Session = Depends(get_db),
):
    _require_org(socio)
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    codigos = _codigos_equipo(socio, db)
    if vl.aliado_codigo not in codigos:
        raise HTTPException(403, "No pertenece a tu organización")
    db.delete(vl)
    db.commit()
    return {"ok": True}
