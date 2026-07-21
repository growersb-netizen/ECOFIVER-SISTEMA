"""
Módulo de Instalación y Equipos — Eco Módulos & Piscinas.

Gestiona:
  - Equipos instaladores (Rodrigo, equipos externos)
  - Tarifas de instalación por producto/modelo
  - Sistema de cobro contraentrega (se cobra en domicilio antes de instalar)
  - Asignación de equipos a ventas
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    EquipoInstalador, TarifaInstalacion, VentaContado, Usuario
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _equipo_dict(e: EquipoInstalador) -> dict:
    return {
        "id": e.id,
        "nombre": e.nombre,
        "tipo": e.tipo,
        "responsable": e.responsable or "",
        "integrantes": e.integrantes or "",
        "telefono": e.telefono or "",
        "zonas_cobertura": e.zonas_cobertura or "",
        "activo": e.activo,
        "notas": e.notas or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


def _tarifa_dict(t: TarifaInstalacion) -> dict:
    return {
        "id": t.id,
        "producto": t.producto,
        "modelo_especifico": t.modelo_especifico or "",
        "nombre_display": t.nombre_display or f"{t.producto} {t.modelo_especifico or '(todos)'}".strip(),
        "tarifa": t.tarifa or 0,
        "tarifa_km_extra": t.tarifa_km_extra or 0,
        "km_incluidos": t.km_incluidos or 0,
        "incluye_materiales": t.incluye_materiales,
        "descripcion": t.descripcion or "",
        "activa": t.activa,
    }


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/instalacion", response_class=HTMLResponse)
async def instalacion_page(
    request: Request,
    current_user: Usuario = Depends(require_auth),
):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("instalacion.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


# ─── EQUIPOS: LIST ────────────────────────────────────────────────────────────

@router.get("/api/instalacion/equipos")
async def list_equipos(
    solo_activos: bool = False,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(EquipoInstalador)
    if solo_activos:
        q = q.filter(EquipoInstalador.activo == True)
    equipos = q.order_by(EquipoInstalador.tipo, EquipoInstalador.nombre).all()
    return {"equipos": [_equipo_dict(e) for e in equipos]}


# ─── EQUIPOS: CREATE ──────────────────────────────────────────────────────────

@router.post("/api/instalacion/equipos")
async def create_equipo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    if not data.get("nombre"):
        raise HTTPException(400, "El nombre del equipo es obligatorio")
    e = EquipoInstalador(
        nombre=data["nombre"].strip(),
        tipo=data.get("tipo", "PROPIO"),
        responsable=data.get("responsable", ""),
        integrantes=data.get("integrantes", ""),
        telefono=data.get("telefono", ""),
        zonas_cobertura=data.get("zonas_cobertura", ""),
        notas=data.get("notas", ""),
        activo=True,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"ok": True, "equipo": _equipo_dict(e)}


# ─── EQUIPOS: UPDATE ──────────────────────────────────────────────────────────

@router.patch("/api/instalacion/equipos/{equipo_id}")
async def update_equipo(
    equipo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    e = db.query(EquipoInstalador).filter(EquipoInstalador.id == equipo_id).first()
    if not e:
        raise HTTPException(404, "Equipo no encontrado")
    data = await request.json()
    for campo in ["nombre", "tipo", "responsable", "integrantes", "telefono",
                  "zonas_cobertura", "notas", "activo"]:
        if campo in data:
            setattr(e, campo, data[campo])
    db.commit()
    return {"ok": True, "equipo": _equipo_dict(e)}


# ─── TARIFAS: LIST ────────────────────────────────────────────────────────────

@router.get("/api/instalacion/tarifas")
async def list_tarifas(
    producto: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(TarifaInstalacion)
    if producto:
        q = q.filter(TarifaInstalacion.producto == producto.upper())
    tarifas = q.order_by(TarifaInstalacion.producto, TarifaInstalacion.modelo_especifico).all()
    return {"tarifas": [_tarifa_dict(t) for t in tarifas]}


# ─── TARIFAS: CREATE / UPDATE ─────────────────────────────────────────────────

@router.post("/api/instalacion/tarifas")
async def create_tarifa(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    if not data.get("producto"):
        raise HTTPException(400, "El campo 'producto' es obligatorio (PISCINA | MODULO)")
    t = TarifaInstalacion(
        producto=data["producto"].upper(),
        modelo_especifico=data.get("modelo_especifico", ""),
        nombre_display=data.get("nombre_display", ""),
        tarifa=float(data.get("tarifa") or 0),
        tarifa_km_extra=float(data.get("tarifa_km_extra") or 0),
        km_incluidos=int(data.get("km_incluidos") or 0),
        incluye_materiales=bool(data.get("incluye_materiales", False)),
        descripcion=data.get("descripcion", ""),
        activa=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ok": True, "tarifa": _tarifa_dict(t)}


@router.patch("/api/instalacion/tarifas/{tarifa_id}")
async def update_tarifa(
    tarifa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    t = db.query(TarifaInstalacion).filter(TarifaInstalacion.id == tarifa_id).first()
    if not t:
        raise HTTPException(404, "Tarifa no encontrada")
    data = await request.json()
    for campo in ["nombre_display", "modelo_especifico", "descripcion", "activa"]:
        if campo in data:
            setattr(t, campo, data[campo])
    for campo_num in ["tarifa", "tarifa_km_extra"]:
        if campo_num in data and data[campo_num] is not None:
            setattr(t, campo_num, float(data[campo_num]))
    if "km_incluidos" in data and data["km_incluidos"] is not None:
        t.km_incluidos = int(data["km_incluidos"])
    if "incluye_materiales" in data:
        t.incluye_materiales = bool(data["incluye_materiales"])
    db.commit()
    return {"ok": True, "tarifa": _tarifa_dict(t)}


@router.delete("/api/instalacion/tarifas/{tarifa_id}")
async def delete_tarifa(
    tarifa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    t = db.query(TarifaInstalacion).filter(TarifaInstalacion.id == tarifa_id).first()
    if not t:
        raise HTTPException(404, "Tarifa no encontrada")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ─── COTIZADOR DE INSTALACIÓN ─────────────────────────────────────────────────

@router.get("/api/instalacion/cotizar")
async def cotizar_instalacion(
    producto: str,
    modelo: str = "",
    distancia_km: float = 0,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Busca la tarifa de instalación aplicable y calcula el costo total."""
    # Buscar tarifa específica primero, luego genérica
    tarifa = db.query(TarifaInstalacion).filter(
        TarifaInstalacion.producto == producto.upper(),
        TarifaInstalacion.modelo_especifico == modelo,
        TarifaInstalacion.activa == True,
    ).first()

    if not tarifa and modelo:
        tarifa = db.query(TarifaInstalacion).filter(
            TarifaInstalacion.producto == producto.upper(),
            TarifaInstalacion.modelo_especifico == "",
            TarifaInstalacion.activa == True,
        ).first()

    if not tarifa:
        return {
            "encontrada": False,
            "mensaje": "No hay tarifa configurada para este producto. Configurala en /instalacion",
        }

    km_extra = max(0, distancia_km - tarifa.km_incluidos)
    costo_km = km_extra * tarifa.tarifa_km_extra
    total = tarifa.tarifa + costo_km

    return {
        "encontrada": True,
        "tarifa_base": tarifa.tarifa,
        "km_incluidos": tarifa.km_incluidos,
        "km_extra": km_extra,
        "costo_km_extra": costo_km,
        "total": total,
        "incluye_materiales": tarifa.incluye_materiales,
        "descripcion": tarifa.descripcion,
        "nombre_display": tarifa.nombre_display,
    }


# ─── VENTAS CONTRAENTREGA: LIST ───────────────────────────────────────────────

@router.get("/api/instalacion/contraentregas")
async def list_contraentregas(
    cobro_estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Lista ventas con modalidad contraentrega y su estado de cobro."""
    q = db.query(VentaContado).filter(VentaContado.modalidad_cobro == "CONTRAENTREGA")
    if cobro_estado:
        q = q.filter(VentaContado.cobro_estado == cobro_estado.upper())
    ventas = q.order_by(VentaContado.fecha_instalacion).all()

    def _venta_dict(v):
        equipo = v.equipo_instalador
        return {
            "id": v.id,
            "cliente_nombre": v.cliente_nombre,
            "cliente_telefono": v.cliente_telefono or "",
            "cliente_localidad": v.cliente_localidad or "",
            "producto": v.producto,
            "modelo_especifico": v.modelo_especifico or "",
            "precio_final": v.precio_final,
            "tarifa_instalacion": v.tarifa_instalacion,
            "total_a_cobrar": (v.precio_final or 0) + (v.tarifa_instalacion or 0),
            "equipo_nombre": equipo.nombre if equipo else "",
            "fecha_instalacion": v.fecha_instalacion.isoformat() if v.fecha_instalacion else "",
            "cobro_estado": v.cobro_estado or "PENDIENTE",
            "cobro_monto_real": v.cobro_monto_real,
            "cobro_fecha": v.cobro_fecha.isoformat() if v.cobro_fecha else "",
            "cobro_notas": v.cobro_notas or "",
            "estado": v.estado,
        }

    return {"contraentregas": [_venta_dict(v) for v in ventas]}


# ─── REGISTRAR COBRO CONTRAENTREGA ────────────────────────────────────────────

@router.post("/api/instalacion/contraentregas/{venta_id}/cobro")
async def registrar_cobro(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Registra el cobro realizado en el domicilio del cliente."""
    v = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    data = await request.json()

    v.cobro_estado = data.get("cobro_estado", "COBRADO")
    if data.get("cobro_monto_real") is not None:
        v.cobro_monto_real = float(data["cobro_monto_real"])
    v.cobro_fecha = datetime.utcnow()
    v.cobro_notas = data.get("cobro_notas", "")

    if v.cobro_estado == "COBRADO":
        v.estado = "INSTALADO"

    db.commit()
    return {"ok": True, "cobro_estado": v.cobro_estado, "venta_estado": v.estado}


# ─── ASIGNAR EQUIPO A VENTA ───────────────────────────────────────────────────

@router.patch("/api/instalacion/ventas/{venta_id}/asignar-equipo")
async def asignar_equipo(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    v = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    data = await request.json()

    if "equipo_instalador_id" in data:
        v.equipo_instalador_id = data["equipo_instalador_id"]
    if "tarifa_instalacion" in data:
        v.tarifa_instalacion = float(data["tarifa_instalacion"])
    if "modalidad_cobro" in data:
        v.modalidad_cobro = data["modalidad_cobro"]
        if data["modalidad_cobro"] == "CONTRAENTREGA" and not v.cobro_estado:
            v.cobro_estado = "PENDIENTE"

    db.commit()
    return {"ok": True}
