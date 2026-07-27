"""
Módulo de Materiales y Compras
  C-MAT 1: Pedidos de materiales (URL pública para el equipo)
  C-MAT 2: Inventario de materiales
  C-MAT 3: Control de herramientas y préstamos
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    PedidoMaterialCompras, MaterialInventario, MovimientoMaterial,
    Herramienta, PrestamoHerramienta, Empleado, Usuario,
    ConfiguracionSistema,
)
from routers.auth import require_auth, get_user_roles, require_auth_or_apikey

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_FABRICA = ["ADMIN", "COORDINADOR_OPERATIVO", "FABRICA", "ADMINISTRACION"]

def _check_fabrica(current_user: Usuario, db: Session):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FABRICA):
        raise HTTPException(403, "Sin permisos")
    return roles


# ─── PÁGINAS HTML ─────────────────────────────────────────────────────────────

@router.get("/materiales", response_class=HTMLResponse)
async def materiales_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FABRICA):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/", 302)
    # Consolidado dentro del Depósito: si se entra directo (sin embed), redirigir a la pestaña Pedidos
    if not request.query_params.get("embed"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/panolero?tab=pedidos", status_code=302)
    db_gen = __import__("database.database", fromlist=["get_db"]).get_db()
    db = next(db_gen)
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    return templates.TemplateResponse("materiales.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": [{"id": e.id, "nombre": e.nombre} for e in empleados],
    })


@router.get("/equipo/pedido", response_class=HTMLResponse)
async def equipo_pedido_page(request: Request, db: Session = Depends(get_db)):
    """Página pública — sin login — para que cualquier operario pida materiales."""
    codigo = request.query_params.get("c", "")
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "equipo_codigo_acceso"
    ).first()
    codigo_correcto = cfg.valor if cfg and cfg.valor else "ECO2026"
    if codigo != codigo_correcto:
        return HTMLResponse("""
        <html><body style='font-family:sans-serif;max-width:400px;margin:60px auto;text-align:center;padding:20px'>
        <h2>🔒 Acceso del Equipo</h2>
        <p>Ingresá el código que te dio Rodrigo:</p>
        <form onsubmit='event.preventDefault();window.location.href="/equipo/pedido?c="+document.getElementById("c").value'>
          <input id="c" type="text" placeholder="Código" style='padding:12px;font-size:18px;width:200px;text-align:center;border:2px solid #ccc;border-radius:8px;display:block;margin:16px auto'>
          <button type="submit" style='padding:12px 32px;background:#10b981;color:#fff;border:none;border-radius:8px;font-size:16px;cursor:pointer'>Entrar</button>
        </form></body></html>
        """, status_code=200)
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    return templates.TemplateResponse("equipo_pedido.html", {
        "request": request,
        "empleados": [{"id": e.id, "nombre": e.nombre} for e in empleados],
        "codigo": codigo,
    })


# ─── API C-MAT 1: PEDIDOS ─────────────────────────────────────────────────────

@router.get("/api/materiales/pedidos")
async def list_pedidos(
    estado: Optional[str] = None,
    urgencia: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    q = db.query(PedidoMaterialCompras)
    if estado:
        q = q.filter(PedidoMaterialCompras.estado == estado)
    if urgencia:
        q = q.filter(PedidoMaterialCompras.urgencia == urgencia)
    pedidos = q.order_by(
        PedidoMaterialCompras.urgencia.asc(),
        PedidoMaterialCompras.created_at.asc()
    ).all()
    return [_pedido_to_dict(p) for p in pedidos]


@router.post("/api/materiales/pedidos")
async def create_pedido(request: Request, db: Session = Depends(get_db)):
    """Público — cualquiera puede crear un pedido (desde /equipo/pedido)."""
    data = await request.json()
    pedido = PedidoMaterialCompras(
        material_descripcion=data.get("material_descripcion", ""),
        cantidad=data.get("cantidad", ""),
        unidad=data.get("unidad", ""),
        urgencia=data.get("urgencia", "ESTA_SEMANA"),
        para_orden=data.get("para_orden", ""),
        solicitado_por_nombre=data.get("solicitado_por_nombre", ""),
        solicitado_por_empleado_id=data.get("solicitado_por_empleado_id"),
        estado="PENDIENTE",
    )
    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return {"id": pedido.id, "ok": True}


@router.put("/api/materiales/pedidos/{pedido_id}")
async def update_pedido(
    pedido_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    p = db.query(PedidoMaterialCompras).filter(PedidoMaterialCompras.id == pedido_id).first()
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    data = await request.json()
    for field in ["estado", "notas_rodrigo", "precio_compra"]:
        if field in data:
            setattr(p, field, data[field])
    if data.get("estado") == "COMPRADO" and not p.fecha_compra:
        p.fecha_compra = datetime.now()
        p.comprado_por_id = current_user.id
        # Sumar al stock si hay material vinculado
        if data.get("material_id") and data.get("cantidad_comprada"):
            mat = db.query(MaterialInventario).filter(MaterialInventario.id == data["material_id"]).first()
            if mat:
                mat.stock_actual += float(data["cantidad_comprada"])
                db.add(MovimientoMaterial(
                    material_id=mat.id,
                    tipo="ENTRADA",
                    cantidad=float(data["cantidad_comprada"]),
                    motivo=f"Compra — pedido #{pedido_id}",
                    pedido_id=pedido_id,
                    creado_por_id=current_user.id,
                ))
    db.commit()
    return {"ok": True}


@router.delete("/api/materiales/pedidos/{pedido_id}")
async def delete_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    p = db.query(PedidoMaterialCompras).filter(PedidoMaterialCompras.id == pedido_id).first()
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ─── API C-MAT 2: INVENTARIO ──────────────────────────────────────────────────

@router.get("/api/materiales/inventario")
async def list_inventario(
    bajo_stock: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    _check_fabrica(current_user, db)
    q = db.query(MaterialInventario).filter(MaterialInventario.activo == True)
    materiales = q.order_by(MaterialInventario.nombre).all()
    result = [_material_to_dict(m) for m in materiales]
    if bajo_stock:
        result = [m for m in result if m["bajo_stock"]]
    return result


@router.post("/api/materiales/inventario")
async def create_material(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    data = await request.json()
    mat = MaterialInventario(
        nombre=data.get("nombre", ""),
        unidad=data.get("unidad", "unidad"),
        stock_actual=data.get("stock_actual", 0),
        stock_minimo=data.get("stock_minimo", 0),
        ubicacion=data.get("ubicacion", ""),
        proveedor=data.get("proveedor", ""),
        precio_referencia=data.get("precio_referencia"),
    )
    db.add(mat)
    db.commit()
    db.refresh(mat)
    return {"id": mat.id, "ok": True}


@router.put("/api/materiales/inventario/{mat_id}")
async def update_material(
    mat_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    mat = db.query(MaterialInventario).filter(MaterialInventario.id == mat_id).first()
    if not mat:
        raise HTTPException(404, "Material no encontrado")
    data = await request.json()
    for field in ["nombre", "unidad", "stock_minimo", "ubicacion", "proveedor", "precio_referencia", "activo"]:
        if field in data:
            setattr(mat, field, data[field])
    db.commit()
    return {"ok": True}


@router.post("/api/materiales/inventario/{mat_id}/movimiento")
async def registrar_movimiento(
    mat_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    _check_fabrica(current_user, db)
    mat = db.query(MaterialInventario).filter(MaterialInventario.id == mat_id).first()
    if not mat:
        raise HTTPException(404, "Material no encontrado")
    data = await request.json()
    tipo = data.get("tipo", "ENTRADA")
    cantidad = float(data.get("cantidad", 0))
    if tipo == "SALIDA":
        mat.stock_actual = max(0, mat.stock_actual - cantidad)
    elif tipo == "ENTRADA":
        mat.stock_actual += cantidad
    elif tipo == "AJUSTE":
        mat.stock_actual = cantidad
    db.add(MovimientoMaterial(
        material_id=mat_id,
        tipo=tipo,
        cantidad=cantidad,
        motivo=data.get("motivo", ""),
        creado_por_id=current_user.id,
    ))
    db.commit()
    return {"ok": True, "stock_actual": mat.stock_actual}


# ─── API C-MAT 3: HERRAMIENTAS ────────────────────────────────────────────────

@router.get("/api/materiales/herramientas")
async def list_herramientas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    herramientas = db.query(Herramienta).filter(Herramienta.activa == True).order_by(Herramienta.nombre).all()
    result = []
    for h in herramientas:
        prestamo_activo = db.query(PrestamoHerramienta).filter(
            PrestamoHerramienta.herramienta_id == h.id,
            PrestamoHerramienta.devuelto == False,
        ).first()
        result.append({
            "id": h.id,
            "nombre": h.nombre,
            "numero_serie": h.numero_serie,
            "estado": h.estado,
            "prestado": prestamo_activo is not None,
            "prestado_a": prestamo_activo.empleado_nombre if prestamo_activo else None,
            "prestado_desde": prestamo_activo.fecha_salida.isoformat() if prestamo_activo else None,
            "destino": prestamo_activo.destino if prestamo_activo else None,
            "prestamo_id": prestamo_activo.id if prestamo_activo else None,
        })
    return result


@router.post("/api/materiales/herramientas")
async def create_herramienta(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    data = await request.json()
    h = Herramienta(
        nombre=data.get("nombre", ""),
        numero_serie=data.get("numero_serie", ""),
        estado=data.get("estado", "OK"),
        notas=data.get("notas", ""),
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id, "ok": True}


@router.put("/api/materiales/herramientas/{h_id}")
async def update_herramienta(
    h_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    h = db.query(Herramienta).filter(Herramienta.id == h_id).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    data = await request.json()
    for field in ["nombre", "numero_serie", "estado", "notas", "activa"]:
        if field in data:
            setattr(h, field, data[field])
    db.commit()
    return {"ok": True}


@router.post("/api/materiales/herramientas/{h_id}/prestar")
async def prestar_herramienta(
    h_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    h = db.query(Herramienta).filter(Herramienta.id == h_id).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    activo = db.query(PrestamoHerramienta).filter(
        PrestamoHerramienta.herramienta_id == h_id,
        PrestamoHerramienta.devuelto == False,
    ).first()
    if activo:
        raise HTTPException(400, "La herramienta ya está prestada")
    data = await request.json()
    prestamo = PrestamoHerramienta(
        herramienta_id=h_id,
        empleado_nombre=data.get("empleado_nombre", ""),
        empleado_id=data.get("empleado_id"),
        destino=data.get("destino", ""),
        notas=data.get("notas", ""),
        registrado_por_id=current_user.id,
    )
    db.add(prestamo)
    db.commit()
    db.refresh(prestamo)
    return {"id": prestamo.id, "ok": True}


@router.post("/api/materiales/herramientas/prestamos/{prestamo_id}/devolver")
async def devolver_herramienta(
    prestamo_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    p = db.query(PrestamoHerramienta).filter(PrestamoHerramienta.id == prestamo_id).first()
    if not p:
        raise HTTPException(404, "Préstamo no encontrado")
    p.devuelto = True
    p.fecha_devolucion_real = datetime.now()
    db.commit()
    return {"ok": True}


@router.get("/api/materiales/herramientas/prestamos-activos")
async def prestamos_activos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_fabrica(current_user, db)
    prestamos = db.query(PrestamoHerramienta).filter(
        PrestamoHerramienta.devuelto == False
    ).order_by(PrestamoHerramienta.fecha_salida.desc()).all()
    ahora = datetime.now()
    return [{
        "id": p.id,
        "herramienta_nombre": p.herramienta.nombre if p.herramienta else "",
        "empleado_nombre": p.empleado_nombre,
        "destino": p.destino,
        "fecha_salida": p.fecha_salida.isoformat() if p.fecha_salida else "",
        "dias_fuera": (ahora - p.fecha_salida).days if p.fecha_salida else 0,
        "alerta": (ahora - p.fecha_salida).days >= 3 if p.fecha_salida else False,
    } for p in prestamos]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _pedido_to_dict(p: PedidoMaterialCompras) -> dict:
    return {
        "id": p.id,
        "material_descripcion": p.material_descripcion,
        "cantidad": p.cantidad,
        "unidad": p.unidad,
        "urgencia": p.urgencia,
        "para_orden": p.para_orden,
        "solicitado_por_nombre": p.solicitado_por_nombre,
        "estado": p.estado,
        "notas_rodrigo": p.notas_rodrigo,
        "precio_compra": p.precio_compra,
        "fecha_compra": p.fecha_compra.isoformat() if p.fecha_compra else None,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


def _material_to_dict(m: MaterialInventario) -> dict:
    return {
        "id": m.id,
        "nombre": m.nombre,
        "unidad": m.unidad,
        "stock_actual": m.stock_actual,
        "stock_minimo": m.stock_minimo,
        "bajo_stock": m.stock_actual <= m.stock_minimo,
        "ubicacion": m.ubicacion,
        "proveedor": m.proveedor,
        "precio_referencia": m.precio_referencia,
        "updated_at": m.updated_at.isoformat() if m.updated_at else "",
    }
