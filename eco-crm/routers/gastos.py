"""
Módulo de Gastos Operativos
Registra todos los gastos de fábrica, instalaciones, ventas y administración.
Soporta imagen, auto-vinculación a ventas/entregas/órdenes y entrada vía Zapia.
"""
import os
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from database.database import get_db
from database.models import (
    Gasto, Usuario, VentaContado, VentaFinanciada,
    Entrega, OrdenFabricaPiscina, OrdenFabricaModulo,
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads/gastos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

CATEGORIAS = [
    "MATERIALES", "COMBUSTIBLE", "COMIDA", "HERRAMIENTAS",
    "FLETE", "INSTALACION", "PRODUCCION", "ADMINISTRATIVO",
    "VEHICULO", "SUELDO", "OTRO"
]
SECTORES = ["FABRICA", "OPERACIONES", "VENTAS", "ADMINISTRACION", "GENERAL"]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def gasto_to_dict(g: Gasto) -> dict:
    link_label = ""
    link_url   = ""
    if g.venta_contado_id:
        link_label = f"Venta contado #{g.venta_contado_id}"
        link_url   = f"/ventas-contado"
    elif g.venta_financiada_id:
        link_label = f"Venta financiada #{g.venta_financiada_id}"
        link_url   = f"/ventas-financiadas"
    elif g.entrega_id:
        link_label = f"Entrega #{g.entrega_id}"
        link_url   = f"/semana-entregas"
    elif g.orden_piscina_id:
        link_label = f"Orden piscina #{g.orden_piscina_id}"
        link_url   = f"/fabrica"
    elif g.orden_modulo_id:
        link_label = f"Orden módulo #{g.orden_modulo_id}"
        link_url   = f"/fabrica"

    return {
        "id":                  g.id,
        "fecha":               g.fecha.isoformat() if g.fecha else "",
        "monto":               g.monto,
        "descripcion":         g.descripcion or "",
        "categoria":           g.categoria or "OTRO",
        "sector":              g.sector or "GENERAL",
        "proveedor":           g.proveedor or "",
        "imagen_url":          g.imagen_url or "",
        "notas":               g.notas or "",
        "cliente_nombre":      g.cliente_nombre or "",
        "estado":              g.estado or "REGISTRADO",
        "origen":              g.origen or "MANUAL",
        "registrado_por":      g.registrado_por.nombre if g.registrado_por else "",
        "created_at":          g.created_at.isoformat() if g.created_at else "",
        "venta_contado_id":    g.venta_contado_id,
        "venta_financiada_id": g.venta_financiada_id,
        "entrega_id":          g.entrega_id,
        "orden_piscina_id":    g.orden_piscina_id,
        "orden_modulo_id":     g.orden_modulo_id,
        "link_label":          link_label,
        "link_url":            link_url,
    }


def _autolink(db: Session, gasto: Gasto, cliente_nombre: str):
    """Intenta vincular el gasto a una venta, entrega u orden según el nombre de cliente."""
    if not cliente_nombre:
        return

    nombre = cliente_nombre.strip()

    # 1. Entrega pendiente con ese cliente
    entrega = db.query(Entrega).filter(
        Entrega.cliente_nombre.ilike(f"%{nombre}%"),
        Entrega.estado.in_(["COORDINADA", "EN_CAMINO"])
    ).order_by(Entrega.fecha_instalacion.desc()).first()
    if entrega:
        gasto.entrega_id = entrega.id
        gasto.cliente_nombre = entrega.cliente_nombre
        return

    # 2. Orden fábrica piscina activa
    orden_p = db.query(OrdenFabricaPiscina).filter(
        OrdenFabricaPiscina.cliente_nombre.ilike(f"%{nombre}%"),
        OrdenFabricaPiscina.estado.in_(["EN_ESPERA", "EN_PROCESO"])
    ).order_by(OrdenFabricaPiscina.created_at.desc()).first()
    if orden_p:
        gasto.orden_piscina_id = orden_p.id
        gasto.cliente_nombre   = orden_p.cliente_nombre
        return

    # 3. Orden fábrica módulo activa
    orden_m = db.query(OrdenFabricaModulo).filter(
        OrdenFabricaModulo.cliente_nombre.ilike(f"%{nombre}%"),
        OrdenFabricaModulo.estado.in_(["EN_ESPERA", "EN_PROCESO"])
    ).order_by(OrdenFabricaModulo.created_at.desc()).first()
    if orden_m:
        gasto.orden_modulo_id = orden_m.id
        gasto.cliente_nombre  = orden_m.cliente_nombre
        return

    # 4. Venta contado
    vc = db.query(VentaContado).filter(
        VentaContado.cliente_nombre.ilike(f"%{nombre}%")
    ).order_by(VentaContado.created_at.desc()).first()
    if vc:
        gasto.venta_contado_id = vc.id
        gasto.cliente_nombre   = vc.cliente_nombre
        return

    # 5. Venta financiada
    vf = db.query(VentaFinanciada).filter(
        VentaFinanciada.cliente_nombre.ilike(f"%{nombre}%")
    ).order_by(VentaFinanciada.created_at.desc()).first()
    if vf:
        gasto.venta_financiada_id = vf.id
        gasto.cliente_nombre      = vf.cliente_nombre


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/gastos", response_class=HTMLResponse)
async def gastos_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("gastos.html", {
        "request":   request,
        "user":      current_user,
        "roles":     roles,
        "categorias": CATEGORIAS,
        "sectores":   SECTORES,
    })


# ─── API ──────────────────────────────────────────────────────────────────────

@router.get("/api/gastos")
async def list_gastos(
    desde:     Optional[str] = None,
    hasta:     Optional[str] = None,
    sector:    Optional[str] = None,
    categoria: Optional[str] = None,
    search:    Optional[str] = None,
    estado:    Optional[str] = None,
    skip:      int = 0,
    limit:     int = 100,
    db:        Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(Gasto)
    if desde:
        try: q = q.filter(Gasto.fecha >= datetime.fromisoformat(desde).date())
        except Exception: pass
    if hasta:
        try: q = q.filter(Gasto.fecha <= datetime.fromisoformat(hasta).date())
        except Exception: pass
    if sector:    q = q.filter(Gasto.sector == sector)
    if categoria: q = q.filter(Gasto.categoria == categoria)
    if estado:    q = q.filter(Gasto.estado == estado)
    if search:
        like = f"%{search}%"
        q = q.filter(
            Gasto.descripcion.ilike(like) |
            Gasto.cliente_nombre.ilike(like) |
            Gasto.proveedor.ilike(like)
        )
    gastos = q.order_by(Gasto.fecha.desc(), Gasto.created_at.desc()).offset(skip).limit(limit).all()
    return [gasto_to_dict(g) for g in gastos]


@router.get("/api/gastos/resumen")
async def resumen_gastos(
    mes:    Optional[int] = None,
    anio:   Optional[int] = None,
    db:     Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Totales del mes por sector y categoría."""
    hoy = date.today()
    m   = mes  or hoy.month
    a   = anio or hoy.year

    gastos = db.query(Gasto).filter(
        extract("month", Gasto.fecha) == m,
        extract("year",  Gasto.fecha) == a,
    ).all()

    total = sum(g.monto for g in gastos)

    por_sector = {}
    for g in gastos:
        por_sector[g.sector] = por_sector.get(g.sector, 0) + g.monto

    por_categoria = {}
    for g in gastos:
        por_categoria[g.categoria] = por_categoria.get(g.categoria, 0) + g.monto

    # Semana actual
    lunes = hoy - __import__("datetime").timedelta(days=hoy.weekday())
    semana = sum(g.monto for g in gastos if g.fecha >= lunes)

    return {
        "mes": m, "anio": a,
        "total_mes": round(total, 2),
        "semana_actual": round(semana, 2),
        "cantidad": len(gastos),
        "por_sector":    {k: round(v, 2) for k, v in sorted(por_sector.items(),    key=lambda x: -x[1])},
        "por_categoria": {k: round(v, 2) for k, v in sorted(por_categoria.items(), key=lambda x: -x[1])},
    }


@router.post("/api/gastos")
async def create_gasto(
    request: Request,
    db:      Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()

    fecha = date.today()
    if data.get("fecha"):
        try: fecha = datetime.fromisoformat(data["fecha"]).date()
        except Exception: pass

    gasto = Gasto(
        fecha       = fecha,
        monto       = float(data.get("monto") or 0),
        descripcion = data.get("descripcion", "").strip(),
        categoria   = data.get("categoria", "OTRO"),
        sector      = data.get("sector",    "GENERAL"),
        proveedor   = data.get("proveedor", ""),
        imagen_url  = data.get("imagen_url", ""),
        notas       = data.get("notas", ""),
        cliente_nombre        = data.get("cliente_nombre", ""),
        venta_contado_id      = data.get("venta_contado_id"),
        venta_financiada_id   = data.get("venta_financiada_id"),
        entrega_id            = data.get("entrega_id"),
        orden_piscina_id      = data.get("orden_piscina_id"),
        orden_modulo_id       = data.get("orden_modulo_id"),
        registrado_por_id     = current_user.id,
        estado  = "REGISTRADO",
        origen  = data.get("origen", "MANUAL"),
    )

    # Auto-link si no viene FK explícita
    if not any([gasto.venta_contado_id, gasto.venta_financiada_id,
                gasto.entrega_id, gasto.orden_piscina_id, gasto.orden_modulo_id]):
        _autolink(db, gasto, gasto.cliente_nombre)

    if not gasto.descripcion:
        raise HTTPException(400, "La descripción es obligatoria")
    if gasto.monto <= 0:
        raise HTTPException(400, "El monto debe ser mayor a 0")

    db.add(gasto)
    db.commit()
    db.refresh(gasto)
    return {"ok": True, "id": gasto.id, "gasto": gasto_to_dict(gasto)}


@router.post("/api/gastos/imagen/{gasto_id}")
async def upload_imagen(
    gasto_id: int,
    file: UploadFile = File(...),
    db:   Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    gasto = db.query(Gasto).filter(Gasto.id == gasto_id).first()
    if not gasto:
        raise HTTPException(404, "Gasto no encontrado")

    ext  = os.path.splitext(file.filename)[1].lower() or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, "wb") as f:
        f.write(await file.read())

    gasto.imagen_url = f"/uploads/gastos/{name}"
    db.commit()
    return {"ok": True, "imagen_url": gasto.imagen_url}


@router.put("/api/gastos/{gasto_id}")
async def update_gasto(
    gasto_id: int,
    request:  Request,
    db:       Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    gasto = db.query(Gasto).filter(Gasto.id == gasto_id).first()
    if not gasto:
        raise HTTPException(404, "Gasto no encontrado")

    data = await request.json()
    for field in ["descripcion", "monto", "categoria", "sector", "proveedor",
                  "imagen_url", "notas", "cliente_nombre", "estado",
                  "venta_contado_id", "venta_financiada_id",
                  "entrega_id", "orden_piscina_id", "orden_modulo_id"]:
        if field in data:
            setattr(gasto, field, data[field])
    if "fecha" in data and data["fecha"]:
        try: gasto.fecha = datetime.fromisoformat(data["fecha"]).date()
        except Exception: pass

    db.commit()
    return {"ok": True}


@router.delete("/api/gastos/{gasto_id}")
async def delete_gasto(
    gasto_id: int,
    db:       Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    gasto = db.query(Gasto).filter(Gasto.id == gasto_id).first()
    if not gasto:
        raise HTTPException(404, "Gasto no encontrado")
    db.delete(gasto)
    db.commit()
    return {"ok": True}
