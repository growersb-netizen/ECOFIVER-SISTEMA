"""
Panel de Entrega Rápida — registro ágil de salidas de herramientas e insumos.
Diseñado para uso móvil: buscar ítem, seleccionar destinatario, confirmar en 2 taps.
Acceso: ADMIN | COORDINADOR_OPERATIVO | ADMINISTRACION
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Herramienta, PrestamoHerramienta,
    MaterialInventario, MovimientoMaterial,
    Empleado, Usuario,
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_ENTREGA = ["ADMIN", "COORDINADOR_OPERATIVO", "ADMINISTRACION", "FABRICA"]


def _check(current_user: Usuario):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_ENTREGA):
        raise HTTPException(403, "Sin permisos para registrar entregas")
    return roles


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/entrega-rapida", response_class=HTMLResponse)
async def entrega_rapida_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = _check(current_user)
    # Consolidado dentro del Depósito: si se entra directo (sin embed), redirigir a la pestaña
    if not request.query_params.get("embed"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/panolero?tab=entrega", status_code=302)
    empleados = (
        db.query(Empleado)
        .filter(Empleado.activo == True)
        .order_by(Empleado.nombre)
        .all()
    )
    return templates.TemplateResponse("entrega_rapida.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": [{"id": e.id, "nombre": e.nombre, "rol": e.rol_empresa or ""} for e in empleados],
    })


# ─── API — ÍTEMS DISPONIBLES ──────────────────────────────────────────────────

@router.get("/api/entrega-rapida/items")
async def get_items_disponibles(
    q: Optional[str] = None,
    tipo: Optional[str] = None,   # HERRAMIENTA | INSUMO
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)

    herramientas = []
    insumos = []

    if tipo in (None, "HERRAMIENTA"):
        # Herramientas activas
        query_h = db.query(Herramienta).filter(Herramienta.activa == True)
        if q:
            query_h = query_h.filter(Herramienta.nombre.ilike(f"%{q}%"))
        hs = query_h.order_by(Herramienta.nombre).all()

        # Prestamos activos
        prestamos_activos = {
            p.herramienta_id: p
            for p in db.query(PrestamoHerramienta).filter(
                PrestamoHerramienta.devuelto == False
            ).all()
        }

        for h in hs:
            p = prestamos_activos.get(h.id)
            en_uso = p is not None
            herramientas.append({
                "id": h.id,
                "tipo": "HERRAMIENTA",
                "nombre": h.nombre,
                "descripcion": h.descripcion or "",
                "categoria": h.categoria or "GENERAL",
                "codigo": h.codigo or "",
                "sector_base": h.sector_base or "DEPOSITO",
                "ubicacion": h.ubicacion_actual or "Depósito",
                "disponible": not en_uso,
                "en_uso_por": p.empleado_nombre if en_uso and p else "",
                "en_uso_sector": p.sector if en_uso and p else "",
                "estado": h.estado or "OK",
            })

    if tipo in (None, "INSUMO"):
        query_m = db.query(MaterialInventario)
        if q:
            query_m = query_m.filter(MaterialInventario.nombre.ilike(f"%{q}%"))
        ms = query_m.order_by(MaterialInventario.nombre).all()

        for m in ms:
            stock = m.stock_actual or 0
            critico = stock <= 0
            alerta = (m.stock_minimo or 0) > 0 and stock <= (m.stock_minimo or 0)
            insumos.append({
                "id": m.id,
                "tipo": "INSUMO",
                "nombre": m.nombre,
                "categoria": m.categoria or "CONSUMIBLE",
                "unidad": m.unidad or "unidad",
                "stock_actual": stock,
                "stock_minimo": m.stock_minimo or 0,
                "ubicacion": m.ubicacion or "",
                "disponible": stock > 0,
                "critico": critico,
                "alerta": alerta,
            })

    return {
        "herramientas": herramientas,
        "insumos": insumos,
        "total": len(herramientas) + len(insumos),
    }


# ─── API — REGISTRAR ENTREGA ──────────────────────────────────────────────────

@router.post("/api/entrega-rapida/entregar")
async def registrar_entrega(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Registra una entrega: préstamo de herramienta O salida de insumo.
    Body:
      tipo: HERRAMIENTA | INSUMO
      item_id: int
      empleado_id: int (opcional si se usa empleado_nombre)
      empleado_nombre: str
      sector: str
      cantidad: float (solo para INSUMO)
      dias_prestamo: int (solo para HERRAMIENTA, default 3)
      notas: str
    """
    roles = _check(current_user)
    data = await request.json()

    tipo = data.get("tipo", "").upper()
    item_id = data.get("item_id")
    empleado_id = data.get("empleado_id")
    empleado_nombre = data.get("empleado_nombre", "").strip()
    sector = data.get("sector", "").strip()
    notas = data.get("notas", "").strip()
    # Destino del consumo: PRODUCCION (fabricar) | INSTALACION (entregar) | OTRO
    destino_area = (data.get("destino_area") or "").upper() or None
    if destino_area not in ("PRODUCCION", "INSTALACION", "OTRO", None):
        destino_area = "OTRO"

    if not item_id:
        raise HTTPException(400, "item_id requerido")
    if not empleado_nombre and not empleado_id:
        raise HTTPException(400, "Debe indicar el destinatario")

    # Resolver nombre de empleado si se pasó solo ID
    if empleado_id and not empleado_nombre:
        emp = db.query(Empleado).filter(Empleado.id == empleado_id).first()
        if emp:
            empleado_nombre = emp.nombre

    ahora = datetime.now()

    if tipo == "HERRAMIENTA":
        h = db.query(Herramienta).filter(Herramienta.id == item_id).first()
        if not h:
            raise HTTPException(404, "Herramienta no encontrada")

        # Verificar que no esté en uso
        existente = db.query(PrestamoHerramienta).filter(
            PrestamoHerramienta.herramienta_id == item_id,
            PrestamoHerramienta.devuelto == False,
        ).first()
        if existente:
            raise HTTPException(409, f"'{h.nombre}' ya está en uso por {existente.empleado_nombre}")

        dias = int(data.get("dias_prestamo", 3))
        prestamo = PrestamoHerramienta(
            herramienta_id=item_id,
            empleado_nombre=empleado_nombre,
            sector=sector,
            destino_area=destino_area,
            motivo_uso=notas,
            fecha_salida=ahora,
            fecha_devolucion_esperada=ahora + timedelta(days=dias),
            devuelto=False,
            usuario_crm_id=current_user.id,
        )
        db.add(prestamo)

        # Actualizar ubicación
        h.ubicacion_actual = sector if sector else empleado_nombre

        db.commit()
        db.refresh(prestamo)
        return {
            "ok": True,
            "tipo": "HERRAMIENTA",
            "accion": "prestamo_creado",
            "prestamo_id": prestamo.id,
            "herramienta": h.nombre,
            "entregado_a": empleado_nombre,
            "devolucion_esperada": prestamo.fecha_devolucion_esperada.isoformat(),
        }

    elif tipo == "INSUMO":
        cantidad = float(data.get("cantidad", 1))
        if cantidad <= 0:
            raise HTTPException(400, "La cantidad debe ser mayor a 0")

        m = db.query(MaterialInventario).filter(MaterialInventario.id == item_id).first()
        if not m:
            raise HTTPException(404, "Insumo no encontrado")

        stock_anterior = m.stock_actual or 0
        if stock_anterior < cantidad:
            raise HTTPException(400, f"Stock insuficiente: hay {stock_anterior} {m.unidad}")

        # Actualizar stock
        m.stock_actual = stock_anterior - cantidad
        m.updated_at = ahora

        # Registrar movimiento
        motivo_mov = f"Entregado a {empleado_nombre}" + (f" — {sector}" if sector else "") + (f". {notas}" if notas else "")
        mov = MovimientoMaterial(
            material_id=item_id,
            tipo="SALIDA",
            cantidad=cantidad,
            motivo=motivo_mov,
            destino_area=destino_area,
            creado_por_id=current_user.id,
        )
        db.add(mov)
        db.commit()
        db.refresh(mov)

        return {
            "ok": True,
            "tipo": "INSUMO",
            "accion": "salida_registrada",
            "movimiento_id": mov.id,
            "insumo": m.nombre,
            "cantidad": cantidad,
            "unidad": m.unidad,
            "stock_nuevo": m.stock_actual,
            "entregado_a": empleado_nombre,
        }

    else:
        raise HTTPException(400, "tipo debe ser HERRAMIENTA o INSUMO")


# ─── API — DEVOLVER HERRAMIENTA ───────────────────────────────────────────────

@router.post("/api/entrega-rapida/devolver/{prestamo_id}")
async def devolver_herramienta(
    prestamo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    data = await request.json()
    notas = data.get("notas", "")

    p = db.query(PrestamoHerramienta).filter(PrestamoHerramienta.id == prestamo_id).first()
    if not p:
        raise HTTPException(404, "Préstamo no encontrado")
    if p.devuelto:
        raise HTTPException(409, "Ya fue devuelta")

    p.devuelto = True
    p.fecha_devolucion_real = datetime.now()
    if notas:
        p.notas = (p.notas or "") + f" | Devolución: {notas}"

    h = db.query(Herramienta).filter(Herramienta.id == p.herramienta_id).first()
    if h:
        h.ubicacion_actual = h.sector_base or "Depósito"

    db.commit()
    return {"ok": True, "herramienta": h.nombre if h else "", "devuelta": True}


# ─── API — RECIENTES ──────────────────────────────────────────────────────────

@router.get("/api/entrega-rapida/recientes")
async def get_recientes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Últimas 30 entregas (herramientas + insumos) de las últimas 24h."""
    _check(current_user)
    desde = datetime.now() - timedelta(hours=24)

    prestamos = (
        db.query(PrestamoHerramienta)
        .filter(PrestamoHerramienta.fecha_salida >= desde)
        .order_by(PrestamoHerramienta.fecha_salida.desc())
        .limit(20)
        .all()
    )

    movimientos = (
        db.query(MovimientoMaterial)
        .filter(
            MovimientoMaterial.tipo == "SALIDA",
            MovimientoMaterial.created_at >= desde,
        )
        .order_by(MovimientoMaterial.created_at.desc())
        .limit(20)
        .all()
    )

    recientes = []

    for p in prestamos:
        h = db.query(Herramienta).filter(Herramienta.id == p.herramienta_id).first()
        recientes.append({
            "tipo": "HERRAMIENTA",
            "id": p.id,
            "item_nombre": h.nombre if h else f"#{p.herramienta_id}",
            "entregado_a": p.empleado_nombre or "",
            "sector": p.sector or "",
            "fecha": p.fecha_salida.isoformat() if p.fecha_salida else "",
            "devuelto": p.devuelto,
            "prestamo_id": p.id,
        })

    for mv in movimientos:
        m = db.query(MaterialInventario).filter(MaterialInventario.id == mv.material_id).first()
        recientes.append({
            "tipo": "INSUMO",
            "id": mv.id,
            "item_nombre": m.nombre if m else f"#{mv.material_id}",
            "cantidad": mv.cantidad,
            "unidad": m.unidad if m else "",
            "notas": mv.motivo or "",
            "fecha": mv.created_at.isoformat() if mv.created_at else "",
            "devuelto": None,
        })

    # Ordenar por fecha descendente
    recientes.sort(key=lambda x: x["fecha"], reverse=True)

    return recientes[:30]
