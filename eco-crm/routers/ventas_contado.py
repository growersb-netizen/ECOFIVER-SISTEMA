import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    VentaContado, Usuario,
    Entrega, OrdenFabricaPiscina, OrdenFabricaModulo, Lead, Interaccion,
    OrdenProduccion,
)
from routers.auth import require_auth, require_roles, get_user_roles, require_auth_or_apikey
from routers.notificaciones import notificar_nueva_venta

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PRECIO_FLETE_KM = 3000  # $/km unificado para todos los productos


def venta_to_dict(v: VentaContado, db=None) -> dict:
    op = None
    if db is not None:
        o = (
            db.query(OrdenProduccion)
            .filter(OrdenProduccion.venta_contado_id == v.id)
            .order_by(OrdenProduccion.id.desc())
            .first()
        )
        if o:
            op = {"id": o.id, "numero": o.numero, "estado": o.estado, "etapa_actual": o.etapa_actual}
    return {
        "id": v.id,
        "orden_produccion": op,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "superficie_m2": v.superficie_m2,
        "precio_final": v.precio_final or 0,
        "forma_pago": v.forma_pago or "CONTADO",
        "vendedor_id": v.vendedor_id,
        "vendedor_nombre": v.vendedor.nombre if v.vendedor else "",
        "fecha_instalacion": v.fecha_instalacion.isoformat() if v.fecha_instalacion else None,
        "rango_horario": v.rango_horario or "",
        "distancia_km": v.distancia_km,
        "flete_calculado": v.flete_calculado,
        "estado": v.estado or "COORDINADO",
        "notas": v.notas or "",
        "desde_stock": v.desde_stock or False,
        # ── Particularidades módulo ────────────────────────────────────────────
        "con_banio": v.con_banio or False,
        "con_cocina": v.con_cocina or False,
        "con_puerta_ingreso": v.con_puerta_ingreso or False,
        "con_ventana_balcon": v.con_ventana_balcon or False,
        "sobre_piso": v.sobre_piso or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


def _siguiente_numero_op(db) -> str:
    """Genera el próximo número de Orden de Producción (OP-AAAA-NNN)."""
    anio = datetime.now().year
    prefix = f"OP-{anio}-"
    ultima = (
        db.query(OrdenProduccion)
        .filter(OrdenProduccion.numero.like(f"{prefix}%"))
        .order_by(OrdenProduccion.id.desc())
        .first()
    )
    num = 1
    if ultima:
        try:
            num = int(ultima.numero.split("-")[-1]) + 1
        except Exception:
            num = 1
    return f"{prefix}{num:03d}"


def _crear_orden_produccion_desde_venta(db, venta: VentaContado):
    """
    Puente Venta → Producción: crea la Orden de Producción formal (con etapas)
    vinculada a la venta, para que aparezca automáticamente en el módulo Producción.
    Idempotente: no duplica si ya existe una orden para esta venta.
    """
    existe = (
        db.query(OrdenProduccion)
        .filter(OrdenProduccion.venta_contado_id == venta.id)
        .first()
    )
    if existe:
        return existe

    aberturas = {
        "puerta_ingreso": bool(venta.con_puerta_ingreso),
        "ventana_balcon": bool(venta.con_ventana_balcon),
        "banio": bool(venta.con_banio),
        "cocina": bool(venta.con_cocina),
        "sobre_piso": venta.sobre_piso or "",
    }
    orden = OrdenProduccion(
        numero=_siguiente_numero_op(db),
        producto=(venta.producto or "MODULO").upper(),
        modelo=venta.modelo_especifico or "",
        color=venta.color or "",
        superficie_m2=venta.superficie_m2,
        aberturas_json=json.dumps(aberturas),
        cliente_nombre=venta.cliente_nombre,
        venta_contado_id=venta.id,
        prioridad="NORMAL",
        fecha_compromiso=venta.fecha_instalacion,
        estado="PENDIENTE",
        etapa_actual="ESTRUCTURA",
        notas=venta.notas or "",
        created_by_id=venta.vendedor_id,
    )
    db.add(orden)
    return orden


def _crear_circuito_post_venta(db, venta: VentaContado, desde_stock: bool):
    """
    Al guardar una venta contado:
    - Siempre crea una Entrega con la fecha del vendedor (tentativa).
    - Si no es desde stock, también crea la(s) OrdenFabrica + la Orden de Producción formal.
    """
    producto_desc = venta.modelo_especifico or venta.producto or ""
    if venta.color:
        producto_desc += f" · {venta.color}"

    # 1 ─ Crear Entrega (siempre)
    entrega = Entrega(
        venta_contado_id=venta.id,
        cliente_nombre=venta.cliente_nombre,
        cliente_localidad=venta.cliente_localidad or "",
        producto=producto_desc,
        fecha_instalacion=venta.fecha_instalacion,
        fecha_original_venta=venta.fecha_instalacion,
        rango_horario=venta.rango_horario or "",
        estado="COORDINADA",
        confirmada=False,
        requiere_fabricacion=not desde_stock,
        auto_generada=True,
    )
    db.add(entrega)

    # 2 ─ Crear OrdenFabrica si no sale desde stock
    if not desde_stock:
        producto = (venta.producto or "").upper()

        if producto in ("PISCINA", "COMBO"):
            db.add(OrdenFabricaPiscina(
                venta_contado_id=venta.id,
                cliente_nombre=venta.cliente_nombre,
                modelo=venta.modelo_especifico or "",
                color=venta.color or "",
                estado="EN_ESPERA",
            ))

        if producto in ("MODULO", "COMBO"):
            db.add(OrdenFabricaModulo(
                venta_contado_id=venta.id,
                cliente_nombre=venta.cliente_nombre,
                superficie_m2=venta.superficie_m2 or 0,
                configuracion=venta.notas or "",
                estado="EN_ESPERA",
            ))

        # 3 ─ Puente Venta → Producción: orden formal con etapas, vinculada a la venta
        _crear_orden_produccion_desde_venta(db, venta)

    db.commit()


@router.get("/ventas-contado", response_class=HTMLResponse)
async def ventas_contado_page(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    vendedores = db.query(Usuario).filter(Usuario.activo == True).all()
    return templates.TemplateResponse("ventas_contado.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "vendedores": [{"id": u.id, "nombre": u.nombre} for u in vendedores],
    })


@router.get("/api/ventas-contado")
async def list_ventas_contado(
    estado: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    q = db.query(VentaContado)
    if estado:
        q = q.filter(VentaContado.estado == estado)
    if search:
        q = q.filter(VentaContado.cliente_nombre.ilike(f"%{search}%"))
    ventas = q.order_by(VentaContado.created_at.desc()).all()
    return [venta_to_dict(v, db) for v in ventas]


@router.post("/api/ventas-contado")
async def create_venta_contado(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    data = await request.json()

    fecha_instalacion = None
    if data.get("fecha_instalacion"):
        try:
            fecha_instalacion = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            pass

    # Calcular flete ($3.000/km unificado)
    distancia_km = data.get("distancia_km")
    flete_calculado = None
    if distancia_km:
        flete_calculado = float(distancia_km) * PRECIO_FLETE_KM

    desde_stock = bool(data.get("desde_stock", False))

    venta = VentaContado(
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color"),
        superficie_m2=data.get("superficie_m2"),
        precio_final=data.get("precio_final", 0),
        forma_pago=data.get("forma_pago", "CONTADO"),
        vendedor_id=data.get("vendedor_id") or current_user.id,
        fecha_instalacion=fecha_instalacion,
        rango_horario=data.get("rango_horario", ""),
        distancia_km=distancia_km,
        flete_calculado=flete_calculado,
        estado=data.get("estado", "COORDINADO"),
        notas=data.get("notas", ""),
        desde_stock=desde_stock,
        # ── Particularidades módulo ────────────────────────────────────────
        con_banio=bool(data.get("con_banio", False)),
        con_cocina=bool(data.get("con_cocina", False)),
        con_puerta_ingreso=bool(data.get("con_puerta_ingreso", False)),
        con_ventana_balcon=bool(data.get("con_ventana_balcon", False)),
        sobre_piso=data.get("sobre_piso") or None,
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
                notas=f"Venta contado #{venta.id} — {venta.modelo_especifico or venta.producto}",
                asesor_id=venta.vendedor_id,
            ))
            db.commit()

    # ── Circuito automático: Entrega + OrdenFabrica ──────────────────────────
    _crear_circuito_post_venta(db, venta, desde_stock)

    # ── Notificaciones ───────────────────────────────────────────────────────
    notificar_nueva_venta(
        db,
        tipo_venta="CONTADO",
        cliente_nombre=venta.cliente_nombre,
        producto=venta.producto or "",
        modelo=venta.modelo_especifico or "",
        monto=venta.precio_final or 0,
        vendedor_id=venta.vendedor_id,
        referencia_id=venta.id,
    )
    db.commit()

    return {
        "id": venta.id,
        "ok": True,
        "flete_calculado": flete_calculado,
        "circuito": "stock" if desde_stock else "fabricacion",
    }


@router.put("/api/ventas-contado/{venta_id}")
async def update_venta_contado(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()

    if "fecha_instalacion" in data and data["fecha_instalacion"]:
        try:
            venta.fecha_instalacion = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            pass

    if "distancia_km" in data and data["distancia_km"]:
        venta.distancia_km = float(data["distancia_km"])
        venta.flete_calculado = venta.distancia_km * PRECIO_FLETE_KM

    for field in ["cliente_nombre", "cliente_telefono", "cliente_localidad", "producto",
                  "modelo_especifico", "color", "superficie_m2", "precio_final", "forma_pago",
                  "vendedor_id", "rango_horario", "estado", "notas", "sobre_piso"]:
        if field in data:
            setattr(venta, field, data[field])

    # Particularidades módulo (booleanos)
    for bfield in ["con_banio", "con_cocina", "con_puerta_ingreso", "con_ventana_balcon"]:
        if bfield in data:
            setattr(venta, bfield, bool(data[bfield]))

    db.commit()

    # ── Si el vendedor cambió la fecha y Renzo aún no confirmó, sincronizar Entrega ──
    if "fecha_instalacion" in data and venta.fecha_instalacion:
        entrega = db.query(Entrega).filter(
            Entrega.venta_contado_id == venta_id,
            Entrega.auto_generada == True,
            Entrega.confirmada == False,
        ).first()
        if entrega:
            entrega.fecha_instalacion = venta.fecha_instalacion
            db.commit()

    return {"ok": True}


@router.get("/api/ventas-contado/{venta_id}")
async def get_venta_contado(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    return venta_to_dict(venta, db)


@router.post("/api/ventas-contado/{venta_id}/cancelar")
async def cancelar_venta_contado(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """
    Cancela una venta contado:
    - Estado → CANCELADA
    - Cancela la Entrega asociada
    - Notifica al vendedor para que gestione el reagendamiento
    """
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    # ── Verificar permisos: ADMIN, COORDINADOR_OPERATIVO o el vendedor que cargó la venta
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        if venta.vendedor_id != current_user.id:
            raise HTTPException(403, "Solo el vendedor que cargó la venta, un Admin o Coordinador Operativo puede cancelarla")

    data = await request.json()
    motivo = (data.get("motivo") or "").strip()

    # ── Cancelar la venta ────────────────────────────────────────────────────
    venta.estado = "CANCELADA"
    nota_cancelacion = f"\n⚠️ CANCELADA por {current_user.nombre}"
    if motivo:
        nota_cancelacion += f": {motivo}"
    venta.notas = (venta.notas or "") + nota_cancelacion

    # ── Cancelar la Entrega asociada (auto-generada) ─────────────────────────
    entrega = db.query(Entrega).filter(
        Entrega.venta_contado_id == venta_id,
        Entrega.estado != "INSTALADA",
    ).first()
    if entrega:
        entrega.estado = "CANCELADA"

    db.commit()

    # ── Notificar al vendedor que cargó la venta ─────────────────────────────
    if venta.vendedor_id:
        from routers.notificaciones import crear_notificacion
        crear_notificacion(
            db,
            usuario_id=venta.vendedor_id,
            titulo=f"⚠️ Venta cancelada — {venta.cliente_nombre}",
            mensaje=(
                f"La venta de {venta.producto or ''} {venta.modelo_especifico or ''} "
                f"para {venta.cliente_nombre} ({venta.cliente_localidad or ''}) fue CANCELADA.\n"
                f"Motivo: {motivo or 'Sin especificar'}\n\n"
                f"Gestioná el reagendamiento o reacomodamiento de la operación "
                f"desde Ventas Contado."
            ),
            tipo="ALERTA",
            referencia_id=venta.id,
            referencia_tipo="venta_contado",
        )
        db.commit()

    return {"ok": True}


@router.delete("/api/ventas-contado/{venta_id}")
async def delete_venta_contado(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    venta = db.query(VentaContado).filter(VentaContado.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    db.delete(venta)
    db.commit()
    return {"ok": True}


@router.post("/api/calcular-flete")
async def calcular_flete(
    request: Request,
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    distancia_km = float(data.get("distancia_km", 0))
    flete = distancia_km * PRECIO_FLETE_KM
    return {
        "distancia_km": distancia_km,
        "precio_por_km": PRECIO_FLETE_KM,
        "flete_calculado": flete,
        "nota": "Valor estimado. Logística confirma el precio exacto."
    }
