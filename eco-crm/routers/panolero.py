"""
Módulo Pañolero — Control de herramientas e insumos
Panel unificado para el Coordinador Operativo (Hernán), Admin y Administración.
Gestiona: herramientas (préstamos/devoluciones), insumos/materiales (stock + movimientos),
alertas de stock bajo y herramientas vencidas.
Acceso: ADMIN | COORDINADOR_OPERATIVO | ADMINISTRACION
"""
from datetime import datetime, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Herramienta, PrestamoHerramienta,
    MaterialInventario, MovimientoMaterial,
    Empleado, Usuario, Gasto,
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_PANOLERO = ["ADMIN", "COORDINADOR_OPERATIVO", "ADMINISTRACION", "FABRICA"]
ROLES_COSTOS   = ["ADMIN", "ADMINISTRACION"]   # quiénes pueden ver/editar costos y precios


def _check(current_user: Usuario):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_PANOLERO):
        raise HTTPException(403, "Sin permisos para acceder al pañolero")
    return roles


def _check_costos(current_user: Usuario, roles: list):
    """Lanza 403 si el usuario no tiene permisos de costos."""
    if not any(r in roles for r in ROLES_COSTOS):
        raise HTTPException(403, "Solo ADMIN o ADMINISTRACIÓN pueden gestionar costos")


def _prestamo_dict(p: PrestamoHerramienta) -> dict:
    vencido = False
    if not p.devuelto and p.fecha_devolucion_esperada:
        vencido = p.fecha_devolucion_esperada < datetime.now()
    return {
        "id": p.id,
        "herramienta_id": p.herramienta_id,
        "herramienta_nombre": p.herramienta.nombre if p.herramienta else "",
        "empleado_nombre": p.empleado_nombre or "",
        "sector": p.sector or "",
        "motivo_uso": p.motivo_uso or "",
        "destino": p.destino or "",
        "fecha_salida": p.fecha_salida.isoformat() if p.fecha_salida else "",
        "fecha_devolucion_esperada": p.fecha_devolucion_esperada.isoformat() if p.fecha_devolucion_esperada else "",
        "fecha_devolucion_real": p.fecha_devolucion_real.isoformat() if p.fecha_devolucion_real else "",
        "devuelto": p.devuelto,
        "vencido": vencido,
        "notas": p.notas or "",
        "registrado_por": p.registrado_por.nombre if p.registrado_por else "",
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


def _herramienta_dict(h: Herramienta, prestamo_activo=None) -> dict:
    en_uso = prestamo_activo is not None
    vencido = False
    if en_uso and prestamo_activo.fecha_devolucion_esperada:
        vencido = prestamo_activo.fecha_devolucion_esperada < datetime.now()
    return {
        "id": h.id,
        "nombre": h.nombre,
        "descripcion": h.descripcion or "",
        "categoria": h.categoria or "GENERAL",
        "codigo": h.codigo or "",
        "numero_serie": h.numero_serie or "",
        "estado": h.estado or "OK",
        "sector_base": h.sector_base or "DEPOSITO",
        "ubicacion_actual": h.ubicacion_actual or "Depósito",
        "activa": h.activa,
        "en_uso": en_uso,
        "prestamo_activo": _prestamo_dict(prestamo_activo) if prestamo_activo else None,
        "vencido": vencido,
        "notas": h.notas or "",
        "precio_costo": h.precio_costo,
        "fecha_adquisicion": h.fecha_adquisicion.isoformat() if h.fecha_adquisicion else None,
    }


def _insumo_dict(m: MaterialInventario) -> dict:
    alerta = (m.stock_minimo or 0) > 0 and (m.stock_actual or 0) <= (m.stock_minimo or 0)
    critico = alerta and (m.stock_actual or 0) <= 0
    pct = 0
    if (m.stock_minimo or 0) > 0:
        pct = min(100, int(((m.stock_actual or 0) / (m.stock_minimo * 2)) * 100))
    return {
        "id": m.id,
        "nombre": m.nombre,
        "categoria": m.categoria or "CONSUMIBLE",
        "unidad": m.unidad or "unidad",
        "stock_actual": m.stock_actual or 0,
        "stock_minimo": m.stock_minimo or 0,
        "ubicacion": m.ubicacion or "",
        "proveedor": m.proveedor or "",
        "precio_referencia": m.precio_referencia,
        "alerta": alerta,
        "critico": critico,
        "pct_stock": pct,
        "updated_at": m.updated_at.isoformat() if m.updated_at else "",
    }


# ─── PÁGINA PRINCIPAL ─────────────────────────────────────────────────────────

@router.get("/panolero", response_class=HTMLResponse)
async def panolero_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = _check(current_user)
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    usuarios = db.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.nombre).all()
    return templates.TemplateResponse("panolero.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": [{"id": e.id, "nombre": e.nombre} for e in empleados],
        "usuarios": [{"id": u.id, "nombre": u.nombre} for u in usuarios],
    })


# ─── API — RESUMEN (header stats) ────────────────────────────────────────────

@router.get("/api/panolero/resumen")
async def get_resumen(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)

    total_herramientas = db.query(Herramienta).filter(Herramienta.activa == True).count()
    en_uso = db.query(PrestamoHerramienta).filter(PrestamoHerramienta.devuelto == False).count()
    disponibles = max(0, total_herramientas - en_uso)

    vencidos = db.query(PrestamoHerramienta).filter(
        PrestamoHerramienta.devuelto == False,
        PrestamoHerramienta.fecha_devolucion_esperada != None,
        PrestamoHerramienta.fecha_devolucion_esperada < datetime.now(),
    ).count()

    materiales_bajos = db.query(MaterialInventario).filter(
        MaterialInventario.activo == True,
        MaterialInventario.stock_minimo > 0,
        MaterialInventario.stock_actual <= MaterialInventario.stock_minimo,
    ).count()

    hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    movs_hoy = db.query(MovimientoMaterial).filter(MovimientoMaterial.created_at >= hoy_inicio).count()
    prestamos_hoy = db.query(PrestamoHerramienta).filter(PrestamoHerramienta.created_at >= hoy_inicio).count()

    return {
        "total_herramientas": total_herramientas,
        "herramientas_en_uso": en_uso,
        "herramientas_disponibles": disponibles,
        "prestamos_vencidos": vencidos,
        "materiales_bajos": materiales_bajos,
        "movimientos_hoy": movs_hoy + prestamos_hoy,
        "total_insumos": db.query(MaterialInventario).filter(MaterialInventario.activo == True).count(),
    }


# ─── API — HERRAMIENTAS ────────────────────────────────────────────────────────

@router.get("/api/panolero/herramientas")
async def list_herramientas(
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    en_uso: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    q = db.query(Herramienta).filter(Herramienta.activa == True)
    if estado:
        q = q.filter(Herramienta.estado == estado)
    if categoria:
        q = q.filter(Herramienta.categoria == categoria)
    if search:
        q = q.filter(Herramienta.nombre.ilike(f"%{search}%"))

    herramientas = q.order_by(Herramienta.nombre).all()

    result = []
    for h in herramientas:
        prestamo_activo = (
            db.query(PrestamoHerramienta)
            .filter(PrestamoHerramienta.herramienta_id == h.id, PrestamoHerramienta.devuelto == False)
            .order_by(PrestamoHerramienta.created_at.desc())
            .first()
        )
        item = _herramienta_dict(h, prestamo_activo)
        if en_uso is not None and item["en_uso"] != en_uso:
            continue
        result.append(item)

    return result


@router.post("/api/panolero/herramientas")
async def create_herramienta(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    data = await request.json()
    fecha_adq = None
    if data.get("fecha_adquisicion"):
        try:
            fecha_adq = datetime.fromisoformat(data["fecha_adquisicion"])
        except Exception:
            pass
    h = Herramienta(
        nombre=data.get("nombre", ""),
        descripcion=data.get("descripcion", ""),
        categoria=data.get("categoria", "GENERAL"),
        codigo=data.get("codigo", ""),
        sector_base=data.get("sector_base", "DEPOSITO"),
        numero_serie=data.get("numero_serie", ""),
        estado=data.get("estado", "OK"),
        ubicacion_actual=data.get("ubicacion_actual", "Depósito"),
        notas=data.get("notas", ""),
        precio_costo=data.get("precio_costo") or None,
        fecha_adquisicion=fecha_adq,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id, "ok": True}


@router.put("/api/panolero/herramientas/{hid}")
async def update_herramienta(
    hid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    data = await request.json()
    for field in ["nombre", "descripcion", "categoria", "codigo", "sector_base", "numero_serie",
                  "estado", "ubicacion_actual", "notas", "activa", "precio_costo"]:
        if field in data:
            setattr(h, field, data[field])
    if "fecha_adquisicion" in data and data["fecha_adquisicion"]:
        try:
            h.fecha_adquisicion = datetime.fromisoformat(data["fecha_adquisicion"])
        except Exception:
            pass
    db.commit()
    return {"ok": True}


@router.post("/api/panolero/herramientas/{hid}/entregar")
async def entregar_herramienta(
    hid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    if h.estado in ("ROTA", "BAJA"):
        raise HTTPException(400, f"La herramienta está en estado '{h.estado}' y no puede entregarse")

    activo = db.query(PrestamoHerramienta).filter(
        PrestamoHerramienta.herramienta_id == hid,
        PrestamoHerramienta.devuelto == False,
    ).first()
    if activo:
        raise HTTPException(400, "La herramienta ya está en uso. Registrá la devolución primero.")

    data = await request.json()
    fecha_devolucion_esperada = None
    if data.get("fecha_devolucion_esperada"):
        try:
            fecha_devolucion_esperada = datetime.fromisoformat(data["fecha_devolucion_esperada"])
        except Exception:
            pass

    _da = (data.get("destino_area") or "").upper() or None
    if _da not in ("PRODUCCION", "INSTALACION", "OTRO", None):
        _da = "OTRO"
    prestamo = PrestamoHerramienta(
        herramienta_id=hid,
        empleado_nombre=data.get("empleado_nombre", ""),
        empleado_id=data.get("empleado_id"),
        usuario_crm_id=data.get("usuario_crm_id"),
        sector=data.get("sector", ""),
        destino_area=_da,
        motivo_uso=data.get("motivo_uso", ""),
        destino=data.get("destino", ""),
        fecha_salida=datetime.now(),
        fecha_devolucion_esperada=fecha_devolucion_esperada,
        devuelto=False,
        notas=data.get("notas", ""),
        registrado_por_id=current_user.id,
    )
    h.ubicacion_actual = data.get("destino", "") or "En uso"
    h.responsable_actual_id = data.get("usuario_crm_id") or None

    db.add(prestamo)
    db.commit()
    db.refresh(prestamo)
    return {"ok": True, "prestamo_id": prestamo.id}


@router.post("/api/panolero/herramientas/{hid}/devolver")
async def devolver_herramienta(
    hid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")

    prestamo = (
        db.query(PrestamoHerramienta)
        .filter(PrestamoHerramienta.herramienta_id == hid, PrestamoHerramienta.devuelto == False)
        .order_by(PrestamoHerramienta.created_at.desc())
        .first()
    )
    if not prestamo:
        raise HTTPException(400, "No hay préstamo activo para esta herramienta")

    data = await request.json()
    prestamo.devuelto = True
    prestamo.fecha_devolucion_real = datetime.now()
    if data.get("notas"):
        prestamo.notas = (prestamo.notas or "") + f"\n[Dev. {datetime.now().strftime('%d/%m %H:%M')}] {data['notas']}"

    nuevo_estado = data.get("estado")
    if nuevo_estado:
        h.estado = nuevo_estado
    h.ubicacion_actual = "Depósito"
    h.responsable_actual_id = None

    db.commit()
    return {"ok": True}


@router.get("/api/panolero/herramientas/{hid}/historial")
async def historial_herramienta(
    hid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    prestamos = (
        db.query(PrestamoHerramienta)
        .filter(PrestamoHerramienta.herramienta_id == hid)
        .order_by(PrestamoHerramienta.created_at.desc())
        .all()
    )
    return {
        "herramienta": _herramienta_dict(h),
        "historial": [_prestamo_dict(p) for p in prestamos],
    }


# ─── API — EN USO (quién tiene qué) ──────────────────────────────────────────

@router.get("/api/panolero/en-uso")
async def get_en_uso(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    prestamos = (
        db.query(PrestamoHerramienta)
        .filter(PrestamoHerramienta.devuelto == False)
        .order_by(PrestamoHerramienta.fecha_salida.desc())
        .all()
    )
    return [_prestamo_dict(p) for p in prestamos]


# ─── API — INSUMOS (usa MaterialInventario existente) ─────────────────────────

@router.get("/api/panolero/insumos")
async def list_insumos(
    con_alerta: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    q = db.query(MaterialInventario).filter(MaterialInventario.activo == True)
    if search:
        q = q.filter(MaterialInventario.nombre.ilike(f"%{search}%"))
    materiales = q.order_by(MaterialInventario.nombre).all()

    result = [_insumo_dict(m) for m in materiales]
    if con_alerta:
        result = [m for m in result if m["alerta"]]
    return result


@router.post("/api/panolero/insumos")
async def create_insumo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    data = await request.json()
    m = MaterialInventario(
        nombre=data.get("nombre", ""),
        categoria=data.get("categoria", "CONSUMIBLE"),
        unidad=data.get("unidad", "unidad"),
        stock_actual=float(data.get("stock_actual", 0)),
        stock_minimo=float(data.get("stock_minimo", 0)),
        ubicacion=data.get("ubicacion", ""),
        proveedor=data.get("proveedor", ""),
        precio_referencia=data.get("precio_referencia"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "ok": True}


@router.put("/api/panolero/insumos/{mid}")
async def update_insumo(
    mid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    m = db.query(MaterialInventario).filter(MaterialInventario.id == mid).first()
    if not m:
        raise HTTPException(404, "Insumo no encontrado")
    data = await request.json()
    for field in ["nombre", "categoria", "unidad", "stock_actual", "stock_minimo",
                  "ubicacion", "proveedor", "precio_referencia", "activo"]:
        if field in data:
            setattr(m, field, data[field])
    db.commit()
    return {"ok": True, **_insumo_dict(m)}


@router.post("/api/panolero/insumos/{mid}/movimiento")
async def registrar_movimiento_insumo(
    mid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    m = db.query(MaterialInventario).filter(MaterialInventario.id == mid).first()
    if not m:
        raise HTTPException(404, "Insumo no encontrado")

    data = await request.json()
    tipo = data.get("tipo", "SALIDA").upper()   # ENTRADA | SALIDA | AJUSTE
    cantidad = float(data.get("cantidad", 0))

    if cantidad <= 0:
        raise HTTPException(400, "La cantidad debe ser mayor a 0")

    stock_anterior = m.stock_actual or 0
    if tipo == "ENTRADA":
        m.stock_actual = stock_anterior + cantidad
        # Si se informa precio, actualizar precio de referencia (solo ADMIN/ADMINISTRACION)
        precio_nuevo = data.get("precio_referencia_nuevo")
        if precio_nuevo is not None:
            roles = get_user_roles(current_user)
            if any(r in roles for r in ROLES_COSTOS):
                m.precio_referencia = float(precio_nuevo)
    elif tipo == "SALIDA":
        if stock_anterior < cantidad:
            raise HTTPException(400, f"Stock insuficiente. Disponible: {stock_anterior} {m.unidad}")
        m.stock_actual = stock_anterior - cantidad
    elif tipo == "AJUSTE":
        m.stock_actual = cantidad
    else:
        raise HTTPException(400, "Tipo inválido. Usar: ENTRADA | SALIDA | AJUSTE")

    # motivo enriquecido con quién/para qué
    motivo_completo = data.get("motivo", "")
    responsable = data.get("responsable", "")
    sector = data.get("sector", "")
    # Destino del consumo: PRODUCCION (fabricar) | INSTALACION (entregar) | OTRO
    destino_area = (data.get("destino_area") or "").upper() or None
    if destino_area not in ("PRODUCCION", "INSTALACION", "OTRO", None):
        destino_area = "OTRO"
    if responsable:
        motivo_completo = f"[{sector or 'General'}] {responsable}: {motivo_completo}"

    mov = MovimientoMaterial(
        material_id=mid,
        tipo=tipo,
        cantidad=cantidad,
        motivo=motivo_completo,
        destino_area=destino_area if tipo == "SALIDA" else None,
        creado_por_id=current_user.id,
    )
    db.add(mov)
    db.commit()

    return {
        "ok": True,
        "stock_anterior": stock_anterior,
        "stock_resultante": m.stock_actual,
        "alerta": (m.stock_minimo or 0) > 0 and m.stock_actual <= (m.stock_minimo or 0),
        "critico": m.stock_actual <= 0,
    }


@router.get("/api/panolero/insumos/{mid}/historial")
async def historial_insumo(
    mid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    m = db.query(MaterialInventario).filter(MaterialInventario.id == mid).first()
    if not m:
        raise HTTPException(404, "Insumo no encontrado")
    movs = (
        db.query(MovimientoMaterial)
        .filter(MovimientoMaterial.material_id == mid)
        .order_by(MovimientoMaterial.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "insumo": _insumo_dict(m),
        "historial": [
            {
                "id": mv.id,
                "tipo": mv.tipo,
                "cantidad": mv.cantidad,
                "motivo": mv.motivo or "",
                "registrado_por": mv.creado_por.nombre if mv.creado_por else "",
                "created_at": mv.created_at.isoformat() if mv.created_at else "",
            }
            for mv in movs
        ],
    }


# ─── API — MOVIMIENTOS RECIENTES (feed unificado) ─────────────────────────────

@router.get("/api/panolero/movimientos")
async def get_movimientos(
    limite: int = 60,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)

    prestamos = (
        db.query(PrestamoHerramienta)
        .order_by(PrestamoHerramienta.created_at.desc())
        .limit(limite)
        .all()
    )
    movs = (
        db.query(MovimientoMaterial)
        .order_by(MovimientoMaterial.created_at.desc())
        .limit(limite)
        .all()
    )

    result = []
    for p in prestamos:
        accion = "DEVOLUCION" if p.devuelto else "ENTREGA"
        result.append({
            "tipo": "herramienta",
            "accion": accion,
            "icon": "🔧",
            "nombre": p.herramienta.nombre if p.herramienta else "—",
            "responsable": p.empleado_nombre or "",
            "sector": p.sector or "",
            "destino": p.destino or "",
            "motivo": p.motivo_uso or "",
            "fecha": p.created_at.isoformat() if p.created_at else "",
            "registrado_por": p.registrado_por.nombre if p.registrado_por else "",
            "ref_id": p.id,
        })
    for mv in movs:
        icons = {"ENTRADA": "📥", "SALIDA": "📤", "AJUSTE": "🔄"}
        result.append({
            "tipo": "insumo",
            "accion": mv.tipo,
            "icon": icons.get(mv.tipo, "📦"),
            "nombre": mv.material.nombre if mv.material else "—",
            "cantidad": mv.cantidad,
            "unidad": mv.material.unidad if mv.material else "",
            "motivo": mv.motivo or "",
            "fecha": mv.created_at.isoformat() if mv.created_at else "",
            "registrado_por": mv.creado_por.nombre if mv.creado_por else "",
            "ref_id": mv.id,
        })

    result.sort(key=lambda x: x["fecha"], reverse=True)
    return result[:limite]


# ─── API — CONSUMO POR SECTOR (Producción vs Instalación) ─────────────────────

@router.get("/api/panolero/consumo-por-sector")
async def consumo_por_sector(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Consumo separado por sector: PRODUCCION (fabricar) vs INSTALACION (entregar).
    Suma salidas de insumos (cantidad + valor $) y préstamos de herramientas por área.
    """
    roles = _check(current_user)
    ver_costos = any(r in roles for r in ROLES_COSTOS)
    desde = datetime.now() - timedelta(days=max(1, dias))

    AREAS = ["PRODUCCION", "INSTALACION", "OTRO"]
    base = {a: {"insumos_movs": 0, "insumos_cantidad": 0.0, "insumos_valor": 0.0,
                "herramientas": 0} for a in AREAS}

    # ── Salidas de insumos ──
    salidas = (
        db.query(MovimientoMaterial)
        .filter(MovimientoMaterial.tipo == "SALIDA", MovimientoMaterial.created_at >= desde)
        .all()
    )
    detalle_insumos = {a: {} for a in AREAS}  # area -> {nombre: cantidad}
    for mv in salidas:
        area = (mv.destino_area or "OTRO").upper()
        if area not in base:
            area = "OTRO"
        cant = mv.cantidad or 0
        precio = (mv.material.precio_referencia or 0) if mv.material else 0
        base[area]["insumos_movs"] += 1
        base[area]["insumos_cantidad"] += cant
        base[area]["insumos_valor"] += cant * precio
        nombre = mv.material.nombre if mv.material else f"#{mv.material_id}"
        detalle_insumos[area][nombre] = detalle_insumos[area].get(nombre, 0) + cant

    # ── Préstamos de herramientas ──
    prestamos = (
        db.query(PrestamoHerramienta)
        .filter(PrestamoHerramienta.fecha_salida >= desde)
        .all()
    )
    for p in prestamos:
        area = (p.destino_area or "OTRO").upper()
        if area not in base:
            area = "OTRO"
        base[area]["herramientas"] += 1

    def empaquetar(area):
        d = base[area]
        top = sorted(detalle_insumos[area].items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "area": area,
            "insumos_movimientos": d["insumos_movs"],
            "insumos_cantidad": round(d["insumos_cantidad"], 2),
            "insumos_valor": round(d["insumos_valor"], 2) if ver_costos else None,
            "herramientas_entregadas": d["herramientas"],
            "top_insumos": [{"nombre": n, "cantidad": round(c, 2)} for n, c in top],
        }

    return {
        "dias": dias,
        "ver_costos": ver_costos,
        "produccion": empaquetar("PRODUCCION"),
        "instalacion": empaquetar("INSTALACION"),
        "otro": empaquetar("OTRO"),
    }


# ─── API — ALERTAS ────────────────────────────────────────────────────────────

@router.get("/api/panolero/alertas")
async def get_alertas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)
    alertas = []

    # Herramientas con préstamo vencido
    vencidos = (
        db.query(PrestamoHerramienta)
        .filter(
            PrestamoHerramienta.devuelto == False,
            PrestamoHerramienta.fecha_devolucion_esperada != None,
            PrestamoHerramienta.fecha_devolucion_esperada < datetime.now(),
        )
        .all()
    )
    for p in vencidos:
        dias = (datetime.now() - p.fecha_devolucion_esperada).days
        alertas.append({
            "tipo": "HERRAMIENTA_VENCIDA",
            "nivel": "ROJA",
            "titulo": f"Herramienta no devuelta",
            "nombre": p.herramienta.nombre if p.herramienta else f"ID {p.herramienta_id}",
            "detalle": f"Tiene: {p.empleado_nombre or 'desconocido'} · {dias} día{'s' if dias != 1 else ''} de atraso",
            "herramienta_id": p.herramienta_id,
            "prestamo_id": p.id,
        })

    # Herramientas en uso sin fecha de devolución hace más de 7 días
    hace_7d = datetime.now() - timedelta(days=7)
    sin_fecha = (
        db.query(PrestamoHerramienta)
        .filter(
            PrestamoHerramienta.devuelto == False,
            PrestamoHerramienta.fecha_devolucion_esperada == None,
            PrestamoHerramienta.fecha_salida < hace_7d,
        )
        .all()
    )
    for p in sin_fecha:
        dias = (datetime.now() - p.fecha_salida).days
        alertas.append({
            "tipo": "HERRAMIENTA_SIN_FECHA",
            "nivel": "AMARILLA",
            "titulo": "Sin fecha de devolución",
            "nombre": p.herramienta.nombre if p.herramienta else f"ID {p.herramienta_id}",
            "detalle": f"Tiene: {p.empleado_nombre or 'desconocido'} · hace {dias} días",
            "herramienta_id": p.herramienta_id,
            "prestamo_id": p.id,
        })

    # Insumos con stock bajo o sin stock
    bajos = (
        db.query(MaterialInventario)
        .filter(
            MaterialInventario.activo == True,
            MaterialInventario.stock_minimo > 0,
            MaterialInventario.stock_actual <= MaterialInventario.stock_minimo,
        )
        .order_by(MaterialInventario.stock_actual)
        .all()
    )
    for m in bajos:
        critico = (m.stock_actual or 0) <= 0
        alertas.append({
            "tipo": "STOCK_BAJO",
            "nivel": "ROJA" if critico else "AMARILLA",
            "titulo": "Sin stock" if critico else "Stock bajo",
            "nombre": m.nombre,
            "detalle": f"Stock actual: {m.stock_actual} {m.unidad or ''} · Mínimo: {m.stock_minimo} {m.unidad or ''}",
            "insumo_id": m.id,
            "proveedor": m.proveedor or "",
        })

    return {
        "total": len(alertas),
        "rojas": sum(1 for a in alertas if a["nivel"] == "ROJA"),
        "amarillas": sum(1 for a in alertas if a["nivel"] == "AMARILLA"),
        "items": alertas,
    }


# ─── DEFINICIÓN DE SECTORES ───────────────────────────────────────────────────

SECTORES_FABRICA = [
    {"id": "DEPOSITO",       "nombre": "Depósito / Pañolero", "icon": "🏠", "color": "#6366f1"},
    {"id": "ESTRUCTURA",     "nombre": "Estructura",          "icon": "🏗️", "color": "#0ea5e9"},
    {"id": "REVESTIMIENTO",  "nombre": "Revestimiento",       "icon": "🪵", "color": "#f59e0b"},
    {"id": "TERMINACIONES",  "nombre": "Terminaciones",       "icon": "🔨", "color": "#10b981"},
    {"id": "PINTURA",        "nombre": "Pintura",             "icon": "🖌️", "color": "#8b5cf6"},
    {"id": "PISCINAS",       "nombre": "Taller Piscinas",     "icon": "🏊", "color": "#06b6d4"},
    {"id": "INSTALACION",    "nombre": "Instalación / Campo", "icon": "🚛", "color": "#ef4444"},
    {"id": "MANTENIMIENTO",  "nombre": "Mantenimiento",       "icon": "⚙️", "color": "#f97316"},
    {"id": "PATIO",          "nombre": "Patio / Exterior",    "icon": "🌿", "color": "#84cc16"},
]

SECTOR_IDS = {s["id"] for s in SECTORES_FABRICA}


# ─── API — SECTORES ───────────────────────────────────────────────────────────

@router.get("/api/panolero/sectores")
async def get_sectores(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Devuelve cada sector con:
    - permanentes: herramientas cuyo sector_base es este sector
    - visitando:   herramientas actualmente prestadas a este sector (pero viven en otro)
    - en_deposito: herramientas del sector que están en el depósito (disponibles)
    """
    _check(current_user)

    # Todas las herramientas activas
    todas = db.query(Herramienta).filter(Herramienta.activa == True).all()

    # Préstamos activos indexados por herramienta_id
    prestamos_activos = {
        p.herramienta_id: p
        for p in db.query(PrestamoHerramienta).filter(PrestamoHerramienta.devuelto == False).all()
    }

    def h_mini(h: Herramienta, prestamo=None) -> dict:
        vencido = False
        if prestamo and prestamo.fecha_devolucion_esperada:
            vencido = prestamo.fecha_devolucion_esperada < datetime.now()
        return {
            "id": h.id,
            "nombre": h.nombre,
            "categoria": h.categoria or "GENERAL",
            "codigo": h.codigo or "",
            "estado": h.estado or "OK",
            "sector_base": h.sector_base or "DEPOSITO",
            "en_prestamo": prestamo is not None,
            "prestamo_empleado": prestamo.empleado_nombre if prestamo else "",
            "prestamo_destino": prestamo.destino if prestamo else "",
            "prestamo_sector": prestamo.sector if prestamo else "",
            "vencido": vencido,
        }

    result = []
    for sector in SECTORES_FABRICA:
        sid = sector["id"]

        # Permanentes = sector_base == sid
        permanentes_todos = [h for h in todas if (h.sector_base or "DEPOSITO") == sid]

        # Separar entre los que están disponibles (en depósito o en sector) vs prestados
        en_deposito  = [h for h in permanentes_todos if sid not in ("INSTALACION",) and h.id not in prestamos_activos]
        en_prestamo  = [h for h in permanentes_todos if h.id in prestamos_activos]

        # Visitando = herramientas de OTRO sector que tienen un préstamo activo hacia ESTE sector
        visitando = [
            h for h in todas
            if (h.sector_base or "DEPOSITO") != sid
            and h.id in prestamos_activos
            and (prestamos_activos[h.id].sector or "") == sid
        ]

        result.append({
            **sector,
            "total_permanentes": len(permanentes_todos),
            "disponibles": [h_mini(h) for h in en_deposito],
            "en_prestamo": [h_mini(h, prestamos_activos[h.id]) for h in en_prestamo],
            "visitando": [h_mini(h, prestamos_activos[h.id]) for h in visitando],
        })

    return result


@router.put("/api/panolero/herramientas/{hid}/valor")
async def asignar_valor_herramienta(
    hid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Asigna / actualiza el costo de adquisición de una herramienta.
    Solo accesible por ADMIN y ADMINISTRACION.
    """
    roles = _check(current_user)
    _check_costos(current_user, roles)

    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")

    data = await request.json()
    if "precio_costo" in data:
        h.precio_costo = float(data["precio_costo"]) if data["precio_costo"] else None
    if data.get("fecha_adquisicion"):
        try:
            h.fecha_adquisicion = datetime.fromisoformat(data["fecha_adquisicion"])
        except Exception:
            pass
    db.commit()
    return {"ok": True, "precio_costo": h.precio_costo}


@router.post("/api/panolero/herramientas/{hid}/asignar-sector")
async def asignar_sector_base(
    hid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Asigna el sector de residencia permanente de una herramienta."""
    _check(current_user)
    h = db.query(Herramienta).filter(Herramienta.id == hid).first()
    if not h:
        raise HTTPException(404, "Herramienta no encontrada")
    data = await request.json()
    sector = data.get("sector_base", "DEPOSITO")
    if sector not in SECTOR_IDS:
        raise HTTPException(400, f"Sector inválido. Válidos: {', '.join(SECTOR_IDS)}")
    h.sector_base = sector
    db.commit()
    return {"ok": True, "herramienta_id": hid, "sector_base": sector}


@router.get("/api/panolero/sectores/lista")
async def get_sectores_lista(
    current_user: Usuario = Depends(require_auth),
):
    """Devuelve solo la definición estática de sectores (para selectores en forms)."""
    _check(current_user)
    return SECTORES_FABRICA


# ─── API — INVENTARIO GENERAL ─────────────────────────────────────────────────

@router.get("/api/panolero/inventario-general")
async def get_inventario_general(
    tipo: Optional[str] = None,       # HERRAMIENTA | INSUMO
    categoria: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Vista unificada de todos los activos del pañolero: herramientas + insumos.
    Incluye valorización patrimonial para la gestión de activos de la fábrica.
    """
    _check(current_user)

    items = []

    # ── Herramientas ──────────────────────────────────────────────────────────
    if tipo in (None, "HERRAMIENTA"):
        q_h = db.query(Herramienta).filter(Herramienta.activa == True)
        if search:
            q_h = q_h.filter(Herramienta.nombre.ilike(f"%{search}%"))
        if categoria:
            q_h = q_h.filter(Herramienta.categoria == categoria)

        prestamos_activos_ids = {
            p.herramienta_id
            for p in db.query(PrestamoHerramienta)
            .filter(PrestamoHerramienta.devuelto == False).all()
        }

        for h in q_h.order_by(Herramienta.nombre).all():
            en_uso = h.id in prestamos_activos_ids
            precio = h.precio_costo or 0
            items.append({
                "tipo": "HERRAMIENTA",
                "id": h.id,
                "nombre": h.nombre,
                "categoria": h.categoria or "GENERAL",
                "codigo": h.codigo or "",
                "unidad": "unidad",
                "stock_actual": 0 if en_uso else 1,
                "stock_minimo": None,
                "en_uso_qty": 1 if en_uso else 0,
                "precio_unitario": precio,
                "valor_total": precio,
                "fecha_adquisicion": h.fecha_adquisicion.isoformat() if h.fecha_adquisicion else None,
                "ubicacion": h.sector_base or "DEPOSITO",
                "estado": "EN_USO" if en_uso else (h.estado or "OK"),
                "alerta": h.estado in ("ROTA", "EN_REPARACION"),
                "critico": h.estado in ("ROTA", "BAJA"),
                "notas": h.notas or "",
            })

    # ── Insumos / Materiales ──────────────────────────────────────────────────
    if tipo in (None, "INSUMO"):
        q_i = db.query(MaterialInventario).filter(MaterialInventario.activo == True)
        if search:
            q_i = q_i.filter(MaterialInventario.nombre.ilike(f"%{search}%"))
        if categoria:
            q_i = q_i.filter(MaterialInventario.categoria == categoria)

        for m in q_i.order_by(MaterialInventario.nombre).all():
            stock = m.stock_actual or 0
            minimo = m.stock_minimo or 0
            alerta = minimo > 0 and stock <= minimo
            critico = alerta and stock <= 0
            precio_u = m.precio_referencia or 0
            items.append({
                "tipo": "INSUMO",
                "id": m.id,
                "nombre": m.nombre,
                "categoria": m.categoria or "CONSUMIBLE",
                "codigo": "",
                "unidad": m.unidad or "unidad",
                "stock_actual": stock,
                "stock_minimo": minimo,
                "en_uso_qty": None,
                "precio_unitario": precio_u,
                "valor_total": stock * precio_u,
                "fecha_adquisicion": None,
                "ubicacion": m.ubicacion or "",
                "estado": "CRITICO" if critico else ("ALERTA" if alerta else "OK"),
                "alerta": alerta,
                "critico": critico,
                "notas": "",
            })

    # Ordenar: alertas/críticos primero, luego por nombre
    items.sort(key=lambda x: (0 if x["critico"] else (1 if x["alerta"] else 2), x["nombre"]))

    valor_herramientas = sum(i["valor_total"] for i in items if i["tipo"] == "HERRAMIENTA")
    valor_insumos      = sum(i["valor_total"] for i in items if i["tipo"] == "INSUMO")

    return {
        "resumen": {
            "total_items":         len(items),
            "total_herramientas":  sum(1 for i in items if i["tipo"] == "HERRAMIENTA"),
            "total_insumos":       sum(1 for i in items if i["tipo"] == "INSUMO"),
            "valor_herramientas":  valor_herramientas,
            "valor_insumos":       valor_insumos,
            "valor_total":         valor_herramientas + valor_insumos,
            "items_con_alerta":    sum(1 for i in items if i["alerta"] or i["critico"]),
        },
        "items": items,
    }


# ─── GASTOS RÁPIDOS DESDE PAÑOLERO ───────────────────────────────────────────

@router.post("/api/panolero/gastos")
async def registrar_gasto_rapido(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Registra un gasto operativo directamente desde el pañolero."""
    roles = _check(current_user)
    data = await request.json()

    monto = data.get("monto")
    descripcion = data.get("descripcion", "").strip()
    categoria = data.get("categoria", "MATERIALES").upper()
    sector = data.get("sector", "FABRICA").upper()
    proveedor = data.get("proveedor", "").strip()
    notas = data.get("notas", "").strip()
    fecha_str = data.get("fecha")

    if not monto or float(monto) <= 0:
        raise HTTPException(400, "El monto debe ser mayor a 0")
    if not descripcion:
        raise HTTPException(400, "La descripción es obligatoria")

    if fecha_str:
        try:
            fecha = date_type.fromisoformat(fecha_str)
        except Exception:
            fecha = date_type.today()
    else:
        fecha = date_type.today()

    gasto = Gasto(
        fecha=fecha,
        monto=float(monto),
        descripcion=descripcion,
        categoria=categoria,
        sector=sector,
        proveedor=proveedor,
        notas=notas,
    )
    db.add(gasto)
    db.commit()
    db.refresh(gasto)

    return {
        "ok": True,
        "gasto_id": gasto.id,
        "monto": gasto.monto,
        "descripcion": gasto.descripcion,
        "categoria": gasto.categoria,
        "fecha": str(gasto.fecha),
    }


@router.get("/api/panolero/gastos/recientes")
async def gastos_recientes_panolero(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Últimos 20 gastos del sector FABRICA para mostrar en pañolero."""
    _check(current_user)
    desde = date_type.today() - timedelta(days=30)
    gastos = (
        db.query(Gasto)
        .filter(Gasto.sector.in_(["FABRICA", "GENERAL"]))
        .filter(Gasto.fecha >= desde)
        .order_by(Gasto.fecha.desc(), Gasto.id.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": g.id,
            "fecha": str(g.fecha),
            "monto": g.monto,
            "descripcion": g.descripcion,
            "categoria": g.categoria,
            "proveedor": g.proveedor or "",
        }
        for g in gastos
    ]
