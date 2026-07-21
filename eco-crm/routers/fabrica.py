from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    StockPiscina, OrdenFabricaPiscina,
    StockPanel, OrdenFabricaModulo,
    PedidoMaterial, Usuario, Notificacion
)
from routers.auth import require_auth, require_roles, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

COLORES_PISCINA = ["Blanco", "Beige", "Verde agua", "Celeste", "Azul"]
MODELOS_PISCINA = [
    "Arco Romano Chico Recto", "Arco Romano Chico Curvo",
    "Arco Romano Mediano Recto", "Arco Romano Mediano Curvo",
    "Arco Romano Grande Recto", "Arco Romano Grande Curvo",
    "Minimalista Chica", "Minimalista Mediana", "Minimalista Grande",
    "Playa y Abanico Chica", "Playa y Abanico Mediana", "Playa y Abanico Grande",
    "Miniportante", "Autoportante", "Minideck Chico", "Minideck Grande"
]


def notify_terminada(db: Session, tipo: str, nombre_cliente: str, ref_id: int):
    renzos = db.query(Usuario).filter(Usuario.activo == True).all()
    for u in renzos:
        roles = []
        try:
            import json
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            pass
        if "COORDINADOR_OPERATIVO" in roles or "ADMIN" in roles:
            n = Notificacion(
                usuario_id=u.id,
                titulo=f"Orden terminada: {tipo}",
                mensaje=f"La orden para {nombre_cliente} está lista para coordinar entrega.",
                tipo="FABRICA",
                referencia_id=ref_id,
                referencia_tipo=tipo,
            )
            db.add(n)


@router.get("/fabrica", response_class=HTMLResponse)
async def fabrica_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("fabrica.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "modelos_piscina": MODELOS_PISCINA,
        "colores_piscina": COLORES_PISCINA,
    })


# ─── STOCK PISCINAS ───────────────────────────────────────────────────────────

@router.get("/api/fabrica/stock-piscinas")
async def get_stock_piscinas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    stock = db.query(StockPiscina).order_by(StockPiscina.modelo, StockPiscina.color).all()
    return [{
        "id": s.id, "modelo": s.modelo, "color": s.color, "cantidad": s.cantidad,
        "alerta": s.cantidad <= 1
    } for s in stock]


@router.put("/api/fabrica/stock-piscinas/{stock_id}")
async def update_stock_piscina(
    stock_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    stock = db.query(StockPiscina).filter(StockPiscina.id == stock_id).first()
    if not stock:
        raise HTTPException(404, "Stock no encontrado")
    data = await request.json()
    stock.cantidad = data.get("cantidad", stock.cantidad)
    db.commit()
    return {"ok": True}


@router.post("/api/fabrica/stock-piscinas")
async def create_stock_piscina(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    existing = db.query(StockPiscina).filter(
        StockPiscina.modelo == data["modelo"],
        StockPiscina.color == data["color"]
    ).first()
    if existing:
        existing.cantidad = (existing.cantidad or 0) + int(data.get("cantidad", 0))
        db.commit()
        return {"id": existing.id, "ok": True}
    s = StockPiscina(modelo=data["modelo"], color=data["color"], cantidad=data.get("cantidad", 0))
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "ok": True}


# ─── ÓRDENES PISCINAS ─────────────────────────────────────────────────────────

@router.get("/api/fabrica/ordenes-piscinas")
async def get_ordenes_piscinas(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(OrdenFabricaPiscina)
    if estado:
        q = q.filter(OrdenFabricaPiscina.estado == estado)
    ordenes = q.order_by(OrdenFabricaPiscina.created_at.desc()).all()
    return [{
        "id": o.id,
        "cliente_nombre": o.cliente_nombre,
        "modelo": o.modelo,
        "color": o.color,
        "fecha_inicio": o.fecha_inicio.isoformat() if o.fecha_inicio else None,
        "fecha_estimada_fin": o.fecha_estimada_fin.isoformat() if o.fecha_estimada_fin else None,
        "estado": o.estado,
        "notas": o.notas or "",
        "created_at": o.created_at.isoformat() if o.created_at else "",
    } for o in ordenes]


@router.post("/api/fabrica/ordenes-piscinas")
async def create_orden_piscina(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    fecha_inicio = None
    fecha_fin = None
    if data.get("fecha_inicio"):
        try:
            fecha_inicio = datetime.fromisoformat(data["fecha_inicio"])
        except Exception:
            pass
    if data.get("fecha_estimada_fin"):
        try:
            fecha_fin = datetime.fromisoformat(data["fecha_estimada_fin"])
        except Exception:
            pass
    orden = OrdenFabricaPiscina(
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        cliente_nombre=data.get("cliente_nombre", ""),
        modelo=data.get("modelo", ""),
        color=data.get("color", ""),
        fecha_inicio=fecha_inicio,
        fecha_estimada_fin=fecha_fin,
        estado=data.get("estado", "EN_ESPERA"),
        notas=data.get("notas", ""),
    )
    db.add(orden)
    db.commit()
    db.refresh(orden)
    return {"id": orden.id, "ok": True}


@router.put("/api/fabrica/ordenes-piscinas/{orden_id}")
async def update_orden_piscina(
    orden_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    orden = db.query(OrdenFabricaPiscina).filter(OrdenFabricaPiscina.id == orden_id).first()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    data = await request.json()

    for dt_f in ["fecha_inicio", "fecha_estimada_fin"]:
        if dt_f in data and data[dt_f]:
            try:
                setattr(orden, dt_f, datetime.fromisoformat(data[dt_f]))
            except Exception:
                pass

    old_estado = orden.estado
    for field in ["cliente_nombre", "modelo", "color", "estado", "notas"]:
        if field in data:
            setattr(orden, field, data[field])

    if data.get("estado") == "TERMINADA" and old_estado != "TERMINADA" and not orden.notificado:
        notify_terminada(db, "piscina", orden.cliente_nombre, orden.id)
        orden.notificado = True

    db.commit()
    return {"ok": True}


# ─── STOCK PANELES ────────────────────────────────────────────────────────────

@router.get("/api/fabrica/stock-paneles")
async def get_stock_paneles(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    stock = db.query(StockPanel).order_by(StockPanel.tipo_panel).all()
    return [{
        "id": s.id, "tipo_panel": s.tipo_panel, "cantidad": s.cantidad,
        "stock_minimo": s.stock_minimo, "alerta": s.cantidad <= s.stock_minimo
    } for s in stock]


@router.put("/api/fabrica/stock-paneles/{stock_id}")
async def update_stock_panel(
    stock_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    stock = db.query(StockPanel).filter(StockPanel.id == stock_id).first()
    if not stock:
        raise HTTPException(404, "Stock no encontrado")
    data = await request.json()
    if "cantidad" in data:
        stock.cantidad = data["cantidad"]
    if "stock_minimo" in data:
        stock.stock_minimo = data["stock_minimo"]
    db.commit()
    return {"ok": True}


# ─── ÓRDENES MÓDULOS ──────────────────────────────────────────────────────────

@router.get("/api/fabrica/ordenes-modulos")
async def get_ordenes_modulos(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(OrdenFabricaModulo)
    if estado:
        q = q.filter(OrdenFabricaModulo.estado == estado)
    ordenes = q.order_by(OrdenFabricaModulo.created_at.desc()).all()
    return [{
        "id": o.id,
        "cliente_nombre": o.cliente_nombre,
        "superficie_m2": o.superficie_m2,
        "configuracion": o.configuracion or "",
        "fecha_inicio": o.fecha_inicio.isoformat() if o.fecha_inicio else None,
        "fecha_estimada_fin": o.fecha_estimada_fin.isoformat() if o.fecha_estimada_fin else None,
        "estado": o.estado,
        "notas": o.notas or "",
        "created_at": o.created_at.isoformat() if o.created_at else "",
    } for o in ordenes]


@router.post("/api/fabrica/ordenes-modulos")
async def create_orden_modulo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    fecha_inicio = None
    fecha_fin = None
    if data.get("fecha_inicio"):
        try:
            fecha_inicio = datetime.fromisoformat(data["fecha_inicio"])
        except Exception:
            pass
    if data.get("fecha_estimada_fin"):
        try:
            fecha_fin = datetime.fromisoformat(data["fecha_estimada_fin"])
        except Exception:
            pass
    orden = OrdenFabricaModulo(
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        cliente_nombre=data.get("cliente_nombre", ""),
        superficie_m2=data.get("superficie_m2", 0),
        configuracion=data.get("configuracion", ""),
        fecha_inicio=fecha_inicio,
        fecha_estimada_fin=fecha_fin,
        estado=data.get("estado", "EN_ESPERA"),
        notas=data.get("notas", ""),
    )
    db.add(orden)
    db.commit()
    db.refresh(orden)
    return {"id": orden.id, "ok": True}


@router.put("/api/fabrica/ordenes-modulos/{orden_id}")
async def update_orden_modulo(
    orden_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    orden = db.query(OrdenFabricaModulo).filter(OrdenFabricaModulo.id == orden_id).first()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    data = await request.json()

    for dt_f in ["fecha_inicio", "fecha_estimada_fin"]:
        if dt_f in data and data[dt_f]:
            try:
                setattr(orden, dt_f, datetime.fromisoformat(data[dt_f]))
            except Exception:
                pass

    old_estado = orden.estado
    for field in ["cliente_nombre", "superficie_m2", "configuracion", "estado", "notas"]:
        if field in data:
            setattr(orden, field, data[field])

    if data.get("estado") == "TERMINADA" and old_estado != "TERMINADA" and not orden.notificado:
        notify_terminada(db, "modulo", orden.cliente_nombre, orden.id)
        orden.notificado = True

    db.commit()
    return {"ok": True}


# ─── PEDIDOS MATERIALES ───────────────────────────────────────────────────────

@router.get("/api/fabrica/pedidos-materiales")
async def get_pedidos_materiales(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(PedidoMaterial)
    if estado:
        q = q.filter(PedidoMaterial.estado == estado)
    pedidos = q.order_by(PedidoMaterial.fecha_pedido.desc()).all()
    return [{
        "id": p.id,
        "material": p.material,
        "cantidad": p.cantidad,
        "unidad": p.unidad,
        "proveedor": p.proveedor or "",
        "estado": p.estado,
        "fecha_pedido": p.fecha_pedido.isoformat() if p.fecha_pedido else "",
        "fecha_recepcion": p.fecha_recepcion.isoformat() if p.fecha_recepcion else None,
        "notas": p.notas or "",
    } for p in pedidos]


@router.post("/api/fabrica/pedidos-materiales")
async def create_pedido_material(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    pedido = PedidoMaterial(
        orden_modulo_id=data.get("orden_modulo_id"),
        material=data.get("material", ""),
        cantidad=data.get("cantidad", 0),
        unidad=data.get("unidad", "unidades"),
        proveedor=data.get("proveedor", ""),
        estado=data.get("estado", "PENDIENTE"),
        notas=data.get("notas", ""),
    )
    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return {"id": pedido.id, "ok": True}


@router.put("/api/fabrica/pedidos-materiales/{pedido_id}")
async def update_pedido_material(
    pedido_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    pedido = db.query(PedidoMaterial).filter(PedidoMaterial.id == pedido_id).first()
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    data = await request.json()
    for field in ["material", "cantidad", "unidad", "proveedor", "estado", "notas"]:
        if field in data:
            setattr(pedido, field, data[field])
    if data.get("estado") == "RECIBIDO":
        pedido.fecha_recepcion = datetime.now()
    db.commit()
    return {"ok": True}
