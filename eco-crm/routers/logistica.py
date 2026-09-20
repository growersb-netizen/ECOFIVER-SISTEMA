import calendar as cal_module
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Entrega, Reclamo, Usuario,
    OrdenFabricaPiscina, OrdenFabricaModulo,
    VentaContado,
)
from routers.auth import require_auth, require_roles, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/logistica", response_class=HTMLResponse)
async def logistica_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("logistica.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.get("/semana-entregas")
async def semana_entregas_page(current_user: Usuario = Depends(require_auth)):
    # Absorbido en el hub de Logística → tab "Esta Semana"
    return RedirectResponse(url="/logistica?tab=semana", status_code=307)


@router.get("/api/logistica/semana")
async def get_semana_entregas(
    offset: Optional[int] = 0,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Devuelve entregas desde hoy + 6 días (rolling 7 días).
    offset=0 → hoy; offset=7 → próxima semana. No permite fechas pasadas.
    También incluye 'vencidas': entregas no realizadas de días anteriores."""
    dias_offset = offset or 0  # permite negativos (pasado)
    hoy = datetime.now().date()
    inicio_date = hoy + timedelta(days=dias_offset)
    fin_date    = inicio_date + timedelta(days=6)

    inicio = datetime.combine(inicio_date, datetime.min.time())
    fin    = datetime.combine(fin_date,    datetime.max.time().replace(microsecond=0))

    def _serial(e, ventas_map, fab_map):
        fab_estado = fab_map.get(e.id) if e.requiere_fabricacion else None
        return {
            "id": e.id,
            "cliente_nombre": e.cliente_nombre or "",
            "cliente_localidad": e.cliente_localidad or "",
            "cliente_telefono": (ventas_map[e.venta_contado_id].cliente_telefono or "")
                                if e.venta_contado_id in ventas_map else "",
            "producto": e.producto or "",
            "rango_horario": e.rango_horario or "",
            "equipo_asignado": e.equipo_asignado or "",
            "estado": e.estado or "COORDINADA",
            "confirmada": e.confirmada,
            "notas": e.notas or "",
            "fecha_instalacion": e.fecha_instalacion.date().isoformat() if e.fecha_instalacion else None,
            "requiere_fabricacion": e.requiere_fabricacion,
            "fab_estado": fab_estado,
        }

    # Entregas del rango
    entregas_rango = db.query(Entrega).filter(
        Entrega.fecha_instalacion >= inicio,
        Entrega.fecha_instalacion <= fin,
    ).order_by(Entrega.fecha_instalacion.asc()).all()

    # Entregas VENCIDAS: fecha < hoy Y estado != INSTALADA
    fin_ayer = datetime.combine(hoy, datetime.min.time())
    vencidas_q = db.query(Entrega).filter(
        Entrega.fecha_instalacion < fin_ayer,
        Entrega.estado != "INSTALADA",
    ).order_by(Entrega.fecha_instalacion.asc()).all()

    # Teléfonos
    all_entregas = entregas_rango + vencidas_q
    all_ids = [e.venta_contado_id for e in all_entregas if e.venta_contado_id]
    ventas_map: dict = {}
    if all_ids:
        ventas = db.query(VentaContado).filter(VentaContado.id.in_(all_ids)).all()
        ventas_map = {v.id: v for v in ventas}

    # Estado de fabricación por entrega_id
    fab_map: dict = {}
    fab_entries = [e for e in all_entregas if e.requiere_fabricacion]
    if fab_entries:
        vc_ids = [e.venta_contado_id for e in fab_entries if e.venta_contado_id]
        vf_ids = [e.venta_financiada_id for e in fab_entries if e.venta_financiada_id]
        # Map venta_id → estado (piscinas + módulos)
        vc_fab: dict = {}
        vf_fab: dict = {}
        if vc_ids:
            for o in db.query(OrdenFabricaPiscina).filter(OrdenFabricaPiscina.venta_contado_id.in_(vc_ids)).all():
                vc_fab[o.venta_contado_id] = o.estado
            for o in db.query(OrdenFabricaModulo).filter(OrdenFabricaModulo.venta_contado_id.in_(vc_ids)).all():
                vc_fab.setdefault(o.venta_contado_id, o.estado)
        if vf_ids:
            for o in db.query(OrdenFabricaPiscina).filter(OrdenFabricaPiscina.venta_financiada_id.in_(vf_ids)).all():
                vf_fab[o.venta_financiada_id] = o.estado
            for o in db.query(OrdenFabricaModulo).filter(OrdenFabricaModulo.venta_financiada_id.in_(vf_ids)).all():
                vf_fab.setdefault(o.venta_financiada_id, o.estado)
        for e in fab_entries:
            if e.venta_contado_id and e.venta_contado_id in vc_fab:
                fab_map[e.id] = vc_fab[e.venta_contado_id]
            elif e.venta_financiada_id and e.venta_financiada_id in vf_fab:
                fab_map[e.id] = vf_fab[e.venta_financiada_id]

    DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dias = []
    for i in range(7):
        dia_date = inicio_date + timedelta(days=i)
        wd = dia_date.weekday()
        dia_entregas = [
            _serial(e, ventas_map, fab_map)
            for e in entregas_rango
            if e.fecha_instalacion and e.fecha_instalacion.date() == dia_date
        ]
        dias.append({
            "fecha": dia_date.isoformat(),
            "dia": DIAS[wd],
            "dia_corto": DIAS[wd][:3],
            "numero": dia_date.day,
            "mes": dia_date.strftime("%b"),
            "es_hoy": dia_date == hoy,
            "entregas": dia_entregas,
            "total": len(dia_entregas),
        })

    return {
        "inicio": inicio_date.isoformat(),
        "fin": fin_date.isoformat(),
        "offset": dias_offset,
        "dias": dias,
        "total_semana": len(entregas_rango),
        "vencidas": [_serial(e, ventas_map, fab_map) for e in vencidas_q],
    }


# ─── ENTREGAS ─────────────────────────────────────────────────────────────────

@router.get("/api/logistica/entregas")
async def get_entregas(
    estado: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(Entrega)
    if estado:
        q = q.filter(Entrega.estado == estado)
    if desde:
        try:
            q = q.filter(Entrega.fecha_instalacion >= datetime.fromisoformat(desde))
        except Exception:
            pass
    if hasta:
        try:
            q = q.filter(Entrega.fecha_instalacion <= datetime.fromisoformat(hasta))
        except Exception:
            pass
    entregas = q.order_by(Entrega.fecha_instalacion.asc()).all()

    # Obtener teléfonos desde ventas_contado (batch, sin N+1)
    venta_ids = [e.venta_contado_id for e in entregas if e.venta_contado_id]
    ventas_map: dict = {}
    if venta_ids:
        ventas = db.query(VentaContado).filter(VentaContado.id.in_(venta_ids)).all()
        ventas_map = {v.id: v for v in ventas}

    return [{
        "id": e.id,
        "cliente_nombre": e.cliente_nombre,
        "cliente_telefono": (ventas_map[e.venta_contado_id].cliente_telefono or "")
                            if e.venta_contado_id in ventas_map else "",
        "cliente_localidad": e.cliente_localidad or "",
        "producto": e.producto or "",
        "fecha_instalacion": e.fecha_instalacion.isoformat() if e.fecha_instalacion else None,
        "rango_horario": e.rango_horario or "",
        "equipo_asignado": e.equipo_asignado or "",
        "estado": e.estado,
        "notas": e.notas or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
    } for e in entregas]


@router.post("/api/logistica/entregas")
async def create_entrega(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    fecha = None
    if data.get("fecha_instalacion"):
        try:
            fecha = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            pass
    entrega = Entrega(
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        fecha_instalacion=fecha,
        rango_horario=data.get("rango_horario", ""),
        equipo_asignado=data.get("equipo_asignado", ""),
        estado=data.get("estado", "COORDINADA"),
        notas=data.get("notas", ""),
    )
    db.add(entrega)
    db.commit()
    db.refresh(entrega)
    return {"id": entrega.id, "ok": True}


@router.put("/api/logistica/entregas/{entrega_id}")
async def update_entrega(
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(404, "Entrega no encontrada")
    data = await request.json()

    if "fecha_instalacion" in data and data["fecha_instalacion"]:
        try:
            entrega.fecha_instalacion = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            pass

    estado_anterior = entrega.estado
    for field in ["cliente_nombre", "cliente_localidad", "producto", "rango_horario",
                  "equipo_asignado", "estado", "notas"]:
        if field in data:
            setattr(entrega, field, data[field])

    # Cuando se marca INSTALADA: generar token de seguimiento en el lead
    if data.get("estado") == "INSTALADA" and estado_anterior != "INSTALADA":
        _generar_token_seguimiento(db, entrega)

    # Cuando se devuelve a ventas: notificar al vendedor que cargó la venta
    if data.get("estado") == "DEVOLVER_A_VENTAS" and estado_anterior != "DEVOLVER_A_VENTAS":
        _notificar_devolucion_a_ventas(db, entrega, data.get("notas", ""))

    db.commit()
    return {"ok": True}


def _notificar_devolucion_a_ventas(db: Session, entrega: Entrega, notas: str = ""):
    """
    Cuando logística devuelve una entrega a ventas, notifica al vendedor
    que cargó la venta original para que gestione la operación.
    """
    try:
        if not entrega.venta_contado_id:
            return
        venta = db.query(VentaContado).filter(VentaContado.id == entrega.venta_contado_id).first()
        if not venta or not venta.vendedor_id:
            return
        from routers.notificaciones import crear_notificacion
        crear_notificacion(
            db,
            usuario_id=venta.vendedor_id,
            titulo=f"🔄 Entrega devuelta a ventas — {entrega.cliente_nombre}",
            mensaje=(
                f"La entrega de {entrega.cliente_nombre} ({entrega.cliente_localidad or ''}) "
                f"— {entrega.producto or ''} —\n"
                f"fue devuelta a ventas para reagendamiento.\n"
                + (f"Notas de logística: {notas}\n" if notas else "")
                + "\nGestioná el reagendamiento desde Ventas Contado."
            ),
            tipo="ALERTA",
            referencia_id=venta.id,
            referencia_tipo="venta_contado",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[DEVOLVER_A_VENTAS] No se pudo notificar: {e}")


def _generar_token_seguimiento(db: Session, entrega: Entrega):
    """
    Genera un token único de seguimiento en el lead asociado a esta entrega
    y dispara un WA invitando al cliente a dejar testimonio.
    """
    import secrets
    try:
        # Buscar lead por teléfono del cliente
        from database.models import Lead, VentaContado
        telefono = ""
        if entrega.venta_contado_id:
            vc = db.query(VentaContado).filter(VentaContado.id == entrega.venta_contado_id).first()
            if vc:
                telefono = vc.cliente_telefono or ""

        if not telefono:
            return

        lead = db.query(Lead).filter(Lead.telefono == telefono).order_by(Lead.id.desc()).first()
        if not lead or lead.seguimiento_token:
            return  # ya tiene token o no existe lead

        token = secrets.token_urlsafe(20)
        lead.seguimiento_token = token
        db.flush()

        # Enviar WA de solicitud de testimonio
        _enviar_wa_testimonio(db, telefono, entrega.cliente_nombre or "", token)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[SEGUIMIENTO TOKEN] {e}")


def _enviar_wa_testimonio(db: Session, telefono: str, nombre: str, token: str):
    """Envía mensaje WA invitando al cliente a dejar su opinión (usa WA Cloud API configurado)."""
    try:
        import os
        base_url = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app")
        link = f"{base_url}/seguimiento/{token}"
        mensaje = (
            f"¡Hola {nombre}! 🎉\n\n"
            f"¡Tu instalación fue completada exitosamente!\n\n"
            f"Nos encantaría conocer tu experiencia. "
            f"¿Podés contarnos cómo te fue?\n\n"
            f"👉 {link}\n\n"
            f"¡Gracias por confiar en EcoFiver!"
        )
        from utils.whatsapp import send_whatsapp_text
        send_whatsapp_text(db, telefono, mensaje)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[WA TESTIMONIO] {e}")


# ─── CALENDARIO DE ENTREGAS ──────────────────────────────────────────────────

def _entrega_to_dict(e: Entrega, fab_lista: bool = False, cliente_telefono: str = "") -> dict:
    return {
        "id": e.id,
        "venta_contado_id": e.venta_contado_id,
        "cliente_nombre": e.cliente_nombre or "",
        "cliente_telefono": cliente_telefono,
        "cliente_localidad": e.cliente_localidad or "",
        "producto": e.producto or "",
        "fecha_instalacion": e.fecha_instalacion.isoformat() if e.fecha_instalacion else None,
        "fecha_original_venta": e.fecha_original_venta.isoformat() if e.fecha_original_venta else None,
        "rango_horario": e.rango_horario or "",
        "equipo_asignado": e.equipo_asignado or "",
        "estado": e.estado or "COORDINADA",
        "notas": e.notas or "",
        "confirmada": e.confirmada or False,
        "confirmada_por": e.confirmada_por.nombre if (e.confirmada and e.confirmada_por) else None,
        "requiere_fabricacion": e.requiere_fabricacion or False,
        "fab_lista": fab_lista,
        "auto_generada": e.auto_generada or False,
    }


def _check_fab_lista(db: Session, entrega: Entrega) -> bool:
    """Verifica si la(s) orden(es) de fábrica de esta entrega ya están listas."""
    if not entrega.requiere_fabricacion or not entrega.venta_contado_id:
        return True  # no requiere fab → está lista
    piscina_ok = db.query(OrdenFabricaPiscina).filter(
        OrdenFabricaPiscina.venta_contado_id == entrega.venta_contado_id,
        OrdenFabricaPiscina.estado.in_(["TERMINADA", "ENTREGADA"]),
    ).first()
    modulo_ok = db.query(OrdenFabricaModulo).filter(
        OrdenFabricaModulo.venta_contado_id == entrega.venta_contado_id,
        OrdenFabricaModulo.estado.in_(["TERMINADA", "ENTREGADA"]),
    ).first()
    return bool(piscina_ok or modulo_ok)


@router.get("/api/logistica/calendario")
async def get_calendario(
    desde: Optional[str] = None,
    dias: int = 90,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Devuelve entregas agrupadas por día, para el calendario de Renzo.
    Por defecto: desde hoy, 90 días hacia adelante.
    """
    fecha_desde = datetime.fromisoformat(desde) if desde else datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    fecha_hasta = fecha_desde + timedelta(days=dias)

    entregas = (
        db.query(Entrega)
        .filter(
            Entrega.fecha_instalacion >= fecha_desde,
            Entrega.fecha_instalacion < fecha_hasta,
            Entrega.estado.notin_(["INSTALADA"]),  # las instaladas ya pasaron
        )
        .order_by(Entrega.fecha_instalacion.asc())
        .all()
    )

    # Batch-fetch teléfonos desde ventas_contado
    venta_ids_cal = [e.venta_contado_id for e in entregas if e.venta_contado_id]
    ventas_map_cal: dict = {}
    if venta_ids_cal:
        vs = db.query(VentaContado).filter(VentaContado.id.in_(venta_ids_cal)).all()
        ventas_map_cal = {v.id: v for v in vs}

    # Agrupar por día (YYYY-MM-DD)
    por_dia: dict = defaultdict(list)
    for e in entregas:
        fab_lista = _check_fab_lista(db, e)
        tel = (ventas_map_cal[e.venta_contado_id].cliente_telefono or "") \
              if e.venta_contado_id in ventas_map_cal else ""
        dia_key = e.fecha_instalacion.strftime("%Y-%m-%d")
        por_dia[dia_key].append(_entrega_to_dict(e, fab_lista, tel))

    result = [
        {"fecha": k, "entregas": v}
        for k, v in sorted(por_dia.items())
    ]
    return result


@router.get("/api/logistica/calendario-mes")
async def get_calendario_mes(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Devuelve totales y detalle de entregas para un mes completo.
    Usado por el calendario mensual del coordinador / admin.
    """
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin permisos")

    now = datetime.now()
    year = year or now.year
    month = month or now.month

    first_day = datetime(year, month, 1, 0, 0, 0)
    last_day_num = cal_module.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num, 23, 59, 59)

    entregas = (
        db.query(Entrega)
        .filter(
            Entrega.fecha_instalacion >= first_day,
            Entrega.fecha_instalacion <= last_day,
        )
        .order_by(Entrega.fecha_instalacion.asc())
        .all()
    )

    # Batch-fetch teléfonos desde ventas_contado
    venta_ids_mes = [e.venta_contado_id for e in entregas if e.venta_contado_id]
    ventas_map_mes: dict = {}
    if venta_ids_mes:
        vs = db.query(VentaContado).filter(VentaContado.id.in_(venta_ids_mes)).all()
        ventas_map_mes = {v.id: v for v in vs}

    por_dia: dict = defaultdict(list)
    for e in entregas:
        fab_lista = _check_fab_lista(db, e)
        tel = (ventas_map_mes[e.venta_contado_id].cliente_telefono or "") \
              if e.venta_contado_id in ventas_map_mes else ""
        dia_key = e.fecha_instalacion.strftime("%Y-%m-%d")
        por_dia[dia_key].append(_entrega_to_dict(e, fab_lista, tel))

    return {
        "year": year,
        "month": month,
        "counts": {k: len(v) for k, v in por_dia.items()},
        "entregas": {k: v for k, v in por_dia.items()},
    }


@router.post("/api/logistica/entregas/{entrega_id}/confirmar")
async def confirmar_entrega(
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Renzo confirma (o modifica) la fecha de entrega con el cliente."""
    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not entrega:
        raise HTTPException(404, "Entrega no encontrada")

    data = await request.json()

    # Actualizar fecha si se envió una nueva
    if data.get("fecha_instalacion"):
        try:
            entrega.fecha_instalacion = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            pass

    # Actualizar campos opcionales
    for field in ["rango_horario", "equipo_asignado", "notas"]:
        if field in data and data[field] is not None:
            setattr(entrega, field, data[field])

    entrega.confirmada = True
    entrega.confirmada_por_id = current_user.id

    db.commit()
    return {"ok": True, "confirmada_por": current_user.nombre}


# ─── RECLAMOS ─────────────────────────────────────────────────────────────────

@router.get("/api/logistica/reclamos")
async def get_reclamos(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(Reclamo)
    if estado:
        q = q.filter(Reclamo.estado == estado)
    reclamos = q.order_by(Reclamo.fecha_reclamo.desc()).all()
    return [{
        "id": r.id,
        "cliente_nombre": r.cliente_nombre,
        "cliente_telefono": r.cliente_telefono or "",
        "fecha_reclamo": r.fecha_reclamo.isoformat() if r.fecha_reclamo else "",
        "descripcion": r.descripcion or "",
        "estado": r.estado,
        "solucion": r.solucion or "",
        "fecha_resolucion": r.fecha_resolucion.isoformat() if r.fecha_resolucion else None,
    } for r in reclamos]


@router.post("/api/logistica/reclamos")
async def create_reclamo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    reclamo = Reclamo(
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_telefono=data.get("cliente_telefono", ""),
        descripcion=data.get("descripcion", ""),
        estado=data.get("estado", "NUEVO"),
        responsable_id=current_user.id,
    )
    db.add(reclamo)
    db.commit()
    db.refresh(reclamo)
    return {"id": reclamo.id, "ok": True}


# ─── COORDINACIÓN DE ENTREGAS (vista Renzo) ───────────────────────────────────

@router.get("/coordinacion-entregas")
async def coordinacion_entregas_page(current_user: Usuario = Depends(require_auth)):
    # Absorbido en el hub de Logística → tab "Lista entregas" › "Pendientes de coordinación"
    return RedirectResponse(url="/logistica?tab=entregas", status_code=307)


@router.get("/api/coordinacion-entregas")
async def get_coordinacion_entregas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Ventas de contado en estado COORDINADO ordenadas por fecha de instalación próxima."""
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin permisos")

    ventas_raw = (
        db.query(VentaContado)
        .filter(VentaContado.estado == "COORDINADO")
        .all()
    )
    # Ordenar: con fecha primero (asc), sin fecha al final
    ventas = sorted(
        ventas_raw,
        key=lambda v: v.fecha_instalacion or datetime.max,
    )

    return [{
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "superficie_m2": v.superficie_m2,
        "fecha_instalacion": v.fecha_instalacion.isoformat() if v.fecha_instalacion else None,
        "rango_horario": v.rango_horario or "",
        "notas": v.notas or "",
        "desde_stock": v.desde_stock or False,
    } for v in ventas]


@router.put("/api/logistica/reclamos/{reclamo_id}")
async def update_reclamo(
    reclamo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    reclamo = db.query(Reclamo).filter(Reclamo.id == reclamo_id).first()
    if not reclamo:
        raise HTTPException(404, "Reclamo no encontrado")
    data = await request.json()

    for field in ["cliente_nombre", "cliente_telefono", "descripcion", "estado", "solucion"]:
        if field in data:
            setattr(reclamo, field, data[field])

    if data.get("estado") == "RESUELTO" and not reclamo.fecha_resolucion:
        reclamo.fecha_resolucion = datetime.now()

    db.commit()
    return {"ok": True}
