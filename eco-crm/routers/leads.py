import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List
import io

from fastapi import APIRouter, Depends, HTTPException, Request, Query, UploadFile, File, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from database.database import get_db
from database.models import Lead, Videollamada, Usuario, Notificacion, ConfiguracionSistema, Interaccion
from routers.auth import require_auth, require_roles, get_user_roles, get_current_user

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


# ─── ROUND-ROBIN ASSIGNMENT ───────────────────────────────────────────────────

def _get_rr_pool_ids(db: Session) -> Optional[set]:
    """
    Devuelve el conjunto de IDs configurados para round-robin.
    Retorna None si no hay configuración (= usar todos los asesores elegibles).
    Retorna set vacío si la configuración existe pero está vacía (= nadie configurado aún).
    """
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "leads_rr_asesores"
    ).first()
    if cfg and cfg.valor:
        try:
            ids = json.loads(cfg.valor)
            return set(ids) if ids else None
        except Exception:
            pass
    return None


def asignar_asesor_round_robin(db: Session) -> Optional[int]:
    """
    Devuelve el id del asesor del pool round-robin con menos leads activos.
    El pool se configura en Configuración → Distribución Leads.
    Si el pool no está configurado, usa todos los asesores elegibles.
    """
    pool_ids = _get_rr_pool_ids(db)

    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    candidatos = []
    for u in asesores:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []
        tiene_rol = "ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles
        en_pool = (pool_ids is None) or (u.id in pool_ids)
        if tiene_rol and en_pool:
            candidatos.append(u)

    if not candidatos:
        return None

    conteos = {}
    for u in candidatos:
        conteos[u.id] = db.query(Lead).filter(
            Lead.asesor_apertura_id == u.id,
            Lead.estado.notin_(["CERRADO", "PERDIDO"])
        ).count()

    elegido = min(candidatos, key=lambda u: (conteos[u.id], u.id))
    return elegido.id


def _asignar_diferente(db: Session, excluir_id: int) -> Optional[int]:
    """Round-robin excluyendo al asesor actual (para rotación)."""
    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    candidatos = []
    for u in asesores:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []
        if ("ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles) and u.id != excluir_id:
            candidatos.append(u)

    if not candidatos:
        return None

    conteos = {}
    for u in candidatos:
        conteos[u.id] = db.query(Lead).filter(
            Lead.asesor_apertura_id == u.id,
            Lead.estado.notin_(["CERRADO", "PERDIDO"])
        ).count()

    elegido = min(candidatos, key=lambda u: (conteos[u.id], u.id))
    return elegido.id


def rotar_leads_inactivos():
    """
    Cron job: reasigna leads NUEVO sin actividad según config `leads_rotacion_horas`.
    Solo se ejecuta si `leads_modo_distribucion == ROTACION_24H`.
    """
    from database.database import SessionLocal
    db = SessionLocal()
    try:
        cfg_modo = db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == "leads_modo_distribucion"
        ).first()
        if not cfg_modo or cfg_modo.valor != "ROTACION_24H":
            return

        cfg_horas = db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == "leads_rotacion_horas"
        ).first()
        horas = int(cfg_horas.valor) if cfg_horas else 24

        limite = datetime.now() - timedelta(hours=horas)

        leads_inactivos = db.query(Lead).filter(
            Lead.estado == "NUEVO",
            Lead.asesor_apertura_id.isnot(None),
            # updated_at puede ser None si nunca se modificó → usar created_at
            or_(
                and_(Lead.updated_at.isnot(None), Lead.updated_at <= limite),
                and_(Lead.updated_at.is_(None), Lead.created_at <= limite),
            )
        ).all()

        count = 0
        for lead in leads_inactivos:
            nuevo_id = _asignar_diferente(db, lead.asesor_apertura_id)
            if nuevo_id:
                lead.asesor_apertura_id = nuevo_id
                ts = datetime.now().strftime("%d/%m %H:%M")
                lead.notas = (lead.notas or "") + f"\n[{ts}] ⚙ Auto-reasignado por inactividad ({horas}hs)"
                count += 1

        db.commit()
        log.info(f"[ROTACION LEADS] {count} leads reasignados por inactividad >{horas}h")
    except Exception as e:
        db.rollback()
        log.error(f"[ROTACION LEADS ERROR] {e}")
    finally:
        db.close()


MODELOS_PISCINA = [
    "Arco Romano Chico Recto", "Arco Romano Chico Curvo",
    "Arco Romano Mediano Recto", "Arco Romano Mediano Curvo",
    "Arco Romano Grande Recto", "Arco Romano Grande Curvo",
    "Minimalista Chica", "Minimalista Mediana", "Minimalista Grande",
    "Playa y Abanico Chica", "Playa y Abanico Mediana", "Playa y Abanico Grande",
    "Miniportante", "Autoportante", "Minideck Chico", "Minideck Grande"
]

MODELOS_MODULO = [f"Módulo {m}m²" for m in [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72]]


def lead_to_dict(lead: Lead, db: Session) -> dict:
    return {
        "id": lead.id,
        "nombre": lead.nombre,
        "telefono": lead.telefono,
        "localidad": lead.localidad or "",
        "producto_interes": lead.producto_interes or "SIN_DEFINIR",
        "modelo_especifico": lead.modelo_especifico or "",
        "forma_pago": lead.forma_pago or "SIN_DEFINIR",
        "estado": lead.estado or "NUEVO",
        "asesor_apertura_id": lead.asesor_apertura_id,
        "asesor_apertura_nombre": lead.asesor_apertura.nombre if lead.asesor_apertura else "",
        "supervisor_cierre_id": lead.supervisor_cierre_id,
        "supervisor_cierre_nombre": lead.supervisor_cierre.nombre if lead.supervisor_cierre else "",
        "origen": lead.origen or "WHATSAPP",
        "notas": lead.notas or "",
        "proximo_seguimiento": lead.proximo_seguimiento.isoformat() if lead.proximo_seguimiento else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else "",
        "veces_recirculado": lead.veces_recirculado or 0,
        "en_rellamados": bool(lead.en_rellamados),
        # ── Canal Aliados ────────────────────────────────────────────────────
        "aliado_codigo": lead.aliado_codigo or None,
        "estado_verificacion": lead.estado_verificacion or "pendiente",
        "timestamp_comprobante": lead.timestamp_comprobante.isoformat() if lead.timestamp_comprobante else None,
    }


# ─── MODO TRABAJO (FOCUS DIALER) ─────────────────────────────────────────────

@router.get("/trabajar", response_class=HTMLResponse)
async def trabajar_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("trabajar.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.get("/api/leads/cola-trabajo")
async def cola_trabajo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Cola priorizada para el modo trabajo. Devuelve leads o VLs según el rol."""
    from sqlalchemy import case as sa_case
    roles = get_user_roles(current_user)

    es_solo_supervisor = (
        "SUPERVISOR_CIERRE" in roles
        and "ASESOR_APERTURA" not in roles
        and "ADMIN" not in roles
    )

    if es_solo_supervisor:
        from database.models import Videollamada
        # VLs asignadas al supervisor (o sin asignar) con estado AGENDADA
        vls = db.query(Videollamada).filter(
            Videollamada.estado == "AGENDADA",
            or_(
                Videollamada.supervisor_cierre_id == current_user.id,
                Videollamada.supervisor_cierre_id == None
            )
        ).order_by(Videollamada.fecha_hora.asc()).all()
        from routers.videollamadas import vl_to_dict
        return {
            "tipo": "vls",
            "total": len(vls),
            "items": [vl_to_dict(v) for v in vls],
        }

    # ASESOR / ADMIN → cola de leads activos (excluye base RELLAMADOS hasta que se distribuya)
    estados_trabajo = ["NUEVO", "INTENTADO", "CONTACTADO", "EN_SEGUIMIENTO", "CALIFICADO"]
    q = db.query(Lead).filter(
        Lead.estado.in_(estados_trabajo),
        or_(Lead.en_rellamados.is_(None), Lead.en_rellamados == False),
    )
    if "ADMIN" not in roles:
        q = q.filter(Lead.asesor_apertura_id == current_user.id)

    orden_estado = sa_case(
        {"NUEVO": 0, "INTENTADO": 1, "CONTACTADO": 2, "EN_SEGUIMIENTO": 3, "CALIFICADO": 4},
        value=Lead.estado, else_=5
    )
    leads = q.order_by(
        orden_estado,
        Lead.updated_at.asc(),
        Lead.created_at.asc()
    ).all()

    items = []
    for lead in leads:
        d = lead_to_dict(lead, db)
        # Últimas 3 interacciones
        ultimas = sorted(lead.interacciones, key=lambda i: i.created_at or datetime.min, reverse=True)[:3]
        d["interacciones"] = [
            {
                "tipo": i.tipo,
                "resultado": i.resultado,
                "notas": i.notas or "",
                "created_at": i.created_at.isoformat() if i.created_at else "",
            }
            for i in ultimas
        ]
        items.append(d)

    return {"tipo": "leads", "total": len(leads), "items": items}


@router.post("/api/leads/{lead_id}/registrar-contacto")
async def registrar_contacto(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Registra el resultado de un contacto en el modo trabajo y actualiza el estado del lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    resultado = data.get("resultado", "NO_CONTESTO")
    notas = data.get("notas", "")

    # Mapa resultado → nuevo estado del lead
    estado_map = {
        "NO_CONTESTO":   "INTENTADO",
        "INTERESADO":    "CONTACTADO",
        "AGENDA_VL":     "VIDEOLLAMADA_AGENDADA",
        "NO_INTERESA":   "PERDIDO",
        "CERRO_VENTA":   "CERRADO",
    }
    nuevo_estado = estado_map.get(resultado)
    if nuevo_estado:
        lead.estado = nuevo_estado
        lead.updated_at = datetime.now()

    # Registrar interacción
    inter = Interaccion(
        lead_id=lead_id,
        tipo="WHATSAPP",
        resultado=resultado,
        notas=notas,
        asesor_id=current_user.id,
    )
    db.add(inter)
    db.commit()
    return {"ok": True, "nuevo_estado": lead.estado}


# ─── PAGE ─────────────────────────────────────────────────────────────────────

@router.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    return templates.TemplateResponse("leads.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "asesores": [{"id": u.id, "nombre": u.nombre} for u in asesores],
        "modelos_piscina": MODELOS_PISCINA,
        "modelos_modulo": MODELOS_MODULO,
    })


# ─── API ──────────────────────────────────────────────────────────────────────

@router.get("/api/leads/stats")
async def leads_stats(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Estadísticas rápidas de leads por estado."""
    roles = get_user_roles(current_user)
    q = db.query(Lead)
    if "ASESOR_APERTURA" in roles and "ADMIN" not in roles and "SUPERVISOR_CIERRE" not in roles:
        q = q.filter(Lead.asesor_apertura_id == current_user.id)

    estados = ["NUEVO","INTENTADO","CONTACTADO","EN_SEGUIMIENTO","CALIFICADO","COTIZADO",
               "NEGOCIANDO","VIDEOLLAMADA_AGENDADA","ESPERANDO_ADMISION","ADMITIDO",
               "RECHAZADO_ADMISION","CERRADO_GANADO","CERRADO_PERDIDO","INACTIVO"]
    result = {}
    for e in estados:
        result[e] = q.filter(Lead.estado == e).count()
    result["TOTAL"] = q.count()
    return result


@router.get("/api/leads/mis-leads")
async def mis_leads(
    asesor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """
    Panel del asesor: leads priorizados por urgencia.
    Si asesor_id se omite, usa el usuario autenticado.
    Secciones: urgentes (>8h sin actividad), para_hoy (seguimiento), nuevos (<2h), en_proceso.
    """
    uid = asesor_id or current_user.id
    ahora = datetime.now()
    hace_8h  = ahora - timedelta(hours=8)
    hace_2h  = ahora - timedelta(hours=2)
    hoy_ini  = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoy_fin  = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)

    estados_activos = ["NUEVO","INTENTADO","CONTACTADO","EN_SEGUIMIENTO","CALIFICADO",
                       "COTIZADO","NEGOCIANDO","VIDEOLLAMADA_AGENDADA"]

    base = db.query(Lead).filter(
        Lead.asesor_apertura_id == uid,
        Lead.estado.in_(estados_activos),
    )

    def horas_sin_actividad(lead):
        ref = lead.updated_at or lead.created_at
        if not ref:
            return 9999
        delta = ahora - ref.replace(tzinfo=None) if ref.tzinfo else ahora - ref
        return delta.total_seconds() / 3600

    todos = base.all()

    urgentes    = []
    nuevos      = []
    para_hoy    = []
    en_proceso  = []

    for l in todos:
        hsa = horas_sin_actividad(l)
        d = {**lead_to_dict(l, db), "horas_sin_actividad": round(hsa, 1)}
        # Para hoy: tiene seguimiento programado hoy
        if l.proximo_seguimiento and hoy_ini <= l.proximo_seguimiento.replace(tzinfo=None) <= hoy_fin:
            para_hoy.append(d)
        elif hsa >= 8 and l.estado in ["NUEVO", "INTENTADO"]:
            urgentes.append(d)
        elif hsa <= 2:
            nuevos.append(d)
        else:
            en_proceso.append(d)

    return {
        "asesor_id": uid,
        "urgentes":   sorted(urgentes,   key=lambda x: -x["horas_sin_actividad"]),
        "para_hoy":   para_hoy,
        "nuevos":     sorted(nuevos,     key=lambda x: x["created_at"], reverse=True),
        "en_proceso": en_proceso,
        "totales":    len(todos),
    }


@router.get("/api/leads")
async def list_leads(
    request: Request,
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    forma_pago: Optional[str] = None,
    asesor_id: Optional[int] = None,
    asesor_apertura_id: Optional[int] = None,  # alias por compatibilidad
    origen: Optional[str] = None,
    rellamados: Optional[int] = None,  # 1 = solo base RELLAMADOS, 0 = excluir
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    q = db.query(Lead)

    # Asesores solo ven sus leads
    if "ASESOR_APERTURA" in roles and "ADMIN" not in roles and "SUPERVISOR_CIERRE" not in roles:
        q = q.filter(Lead.asesor_apertura_id == current_user.id)

    if estado:
        q = q.filter(Lead.estado == estado)
    if producto:
        q = q.filter(Lead.producto_interes == producto)
    if forma_pago:
        q = q.filter(Lead.forma_pago == forma_pago)
    filtro_asesor = asesor_id or asesor_apertura_id
    if filtro_asesor:
        q = q.filter(Lead.asesor_apertura_id == filtro_asesor)
    if origen:
        q = q.filter(Lead.origen == origen)
    if rellamados == 1:
        q = q.filter(Lead.en_rellamados == True)
    elif rellamados == 0:
        q = q.filter(or_(Lead.en_rellamados.is_(None), Lead.en_rellamados == False))
    if search:
        q = q.filter(or_(
            Lead.nombre.ilike(f"%{search}%"),
            Lead.telefono.ilike(f"%{search}%"),
            Lead.localidad.ilike(f"%{search}%")
        ))

    total = q.count()
    leads = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "leads": [lead_to_dict(l, db) for l in leads]}


@router.post("/api/leads")
async def create_lead(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user)
):
    # Allow API key auth (for external agents) OR session auth (CRM users)
    auth_ok = (x_api_key and x_api_key == API_KEY) or bool(current_user)
    if not auth_ok:
        raise HTTPException(401, "No autorizado")

    data = await request.json()
    user_id = current_user.id if current_user else None

    # Si no viene asesor asignado, distribuir en round-robin
    asesor_id = data.get("asesor_apertura_id") or user_id
    if not asesor_id:
        asesor_id = asignar_asesor_round_robin(db)

    # ── Canal Aliados: validar el código si viene ─────────────────────────────
    aliado_codigo = (data.get("aliado_codigo") or "").strip().upper() or None
    if aliado_codigo:
        from database.models import Aliado
        al = db.query(Aliado).filter(Aliado.codigo == aliado_codigo).first()
        if not al:
            raise HTTPException(400, f"Aliado '{aliado_codigo}' inexistente")
        if al.estado != "activo":
            raise HTTPException(400, f"Aliado '{aliado_codigo}' no está activo (estado: {al.estado})")
        if not al.contrato_firmado:
            raise HTTPException(400, f"Aliado '{aliado_codigo}' no tiene contrato firmado")

    ts_comprobante = None
    if data.get("timestamp_comprobante"):
        try:
            ts_comprobante = datetime.fromisoformat(str(data["timestamp_comprobante"]).replace("Z", "+00:00"))
        except Exception:
            ts_comprobante = None

    lead = Lead(
        aliado_codigo=aliado_codigo,
        timestamp_comprobante=ts_comprobante,
        estado_verificacion=data.get("estado_verificacion", "pendiente"),
        nombre=data.get("nombre", ""),
        telefono=data.get("telefono", ""),
        localidad=data.get("localidad", ""),
        producto_interes=data.get("producto_interes", "SIN_DEFINIR"),
        modelo_especifico=data.get("modelo_especifico", ""),
        forma_pago=data.get("forma_pago", "SIN_DEFINIR"),
        estado=data.get("estado", "NUEVO"),
        asesor_apertura_id=asesor_id,
        origen=data.get("origen", "WEB"),
        notas=data.get("notas", ""),
        session_id=data.get("session_id"),
        agente_asignado=data.get("agente_asignado", ""),
        utm_source=data.get("utm_source"),
        utm_medium=data.get("utm_medium"),
        utm_campaign=data.get("utm_campaign"),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    asesor_nombre = ""
    asesor_telefono = None
    if asesor_id:
        u = db.query(Usuario).filter(Usuario.id == asesor_id).first()
        if u:
            asesor_nombre = u.nombre
            # Buscar teléfono del asesor en su email como fallback (si tienen campo telefono)
            # Por ahora notificamos si hay wa_notif_asesor config
            _notificar_asesor_lead_nuevo(db, u, lead)

    return {"id": lead.id, "ok": True, "asesor_asignado": asesor_nombre}


def _notificar_asesor_lead_nuevo(db: Session, asesor: Usuario, lead: Lead):
    """Envía WA al asesor si tiene número registrado en config, y notificación interna."""
    try:
        # Notificación interna CRM
        from routers.notificaciones import crear_notificacion
        crear_notificacion(
            db,
            usuario_id=asesor.id,
            titulo="📋 Nuevo lead asignado",
            mensaje=f"{lead.nombre} — {lead.producto_interes} — {lead.localidad or 'sin localidad'}",
            tipo="LEAD",
            referencia_id=lead.id,
            referencia_tipo="lead",
        )
        db.commit()

        # Notificación WA — busca teléfono del asesor en config
        from database.models import ConfiguracionSistema
        from utils.whatsapp import notificar_asesor_nuevo_lead
        tel_cfg = db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == f"asesor_tel_{asesor.id}"
        ).first()
        if tel_cfg and tel_cfg.valor:
            notificar_asesor_nuevo_lead(
                db,
                asesor_telefono=tel_cfg.valor,
                lead_nombre=lead.nombre,
                producto=lead.producto_interes or "",
                localidad=lead.localidad or "",
                forma_pago=lead.forma_pago or "",
                lead_id=lead.id,
            )
    except Exception as e:
        log.warning(f"[LEAD] Error notificando al asesor {asesor.nombre}: {e}")


@router.get("/api/leads/rr-config")
async def get_rr_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Devuelve todos los asesores elegibles con flag en_rr."""
    pool_ids = _get_rr_pool_ids(db)
    asesores = db.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.id).all()
    result = []
    for u in asesores:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []
        if "ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles:
            result.append({
                "id": u.id,
                "nombre": u.nombre,
                "en_rr": (pool_ids is None) or (u.id in pool_ids),
            })
    return {
        "asesores": result,
        "pool_configurado": pool_ids is not None,
        "pool_ids": list(pool_ids) if pool_ids else [],
    }


@router.put("/api/leads/rr-config")
async def set_rr_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Actualiza el pool de round-robin. ids=[] desactiva el filtro (usa todos)."""
    data = await request.json()
    ids = data.get("ids", [])

    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "leads_rr_asesores"
    ).first()
    valor = json.dumps(ids)
    if cfg:
        cfg.valor = valor
    else:
        db.add(ConfiguracionSistema(
            clave="leads_rr_asesores",
            valor=valor,
            es_secreto=False,
            categoria="leads",
            estado="activa",
        ))
    db.commit()
    return {"ok": True, "pool_ids": ids}


@router.get("/api/leads/conteo-vendedor")
async def conteo_vendedor(
    asesor_id: int,
    solo_activos: bool = True,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Cuenta cuántos leads tiene un vendedor (para preview antes de transferir)."""
    q = db.query(Lead).filter(Lead.asesor_apertura_id == asesor_id)
    if solo_activos:
        q = q.filter(Lead.estado.notin_(["CERRADO", "PERDIDO"]))
    total = q.count()
    u = db.query(Usuario).filter(Usuario.id == asesor_id).first()
    return {"total": total, "nombre": u.nombre if u else "Desconocido"}


@router.post("/api/leads/reasignar-vendedor")
async def reasignar_vendedor(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Reasigna TODOS los leads de un vendedor a otro (→)."""
    data = await request.json()
    desde_id = data.get("desde_id")
    hacia_id = data.get("hacia_id")
    solo_activos = data.get("solo_activos", True)

    if not desde_id or not hacia_id or int(desde_id) == int(hacia_id):
        raise HTTPException(400, "Seleccioná dos vendedores distintos")

    q = db.query(Lead).filter(Lead.asesor_apertura_id == int(desde_id))
    if solo_activos:
        q = q.filter(Lead.estado.notin_(["CERRADO", "PERDIDO"]))

    ts = datetime.now().strftime("%d/%m %H:%M")
    hacia = db.query(Usuario).filter(Usuario.id == int(hacia_id)).first()
    count = 0
    for lead in q.all():
        lead.asesor_apertura_id = int(hacia_id)
        lead.notas = (lead.notas or "") + f"\n[{ts}] ➡ Reasignado a {hacia.nombre if hacia else hacia_id} por admin"
        count += 1

    db.commit()
    return {"ok": True, "reasignados": count}


@router.post("/api/leads/intercambiar-vendedores")
async def intercambiar_vendedores(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Intercambia (swap) TODOS los leads entre dos vendedores (↔)."""
    data = await request.json()
    id_a = data.get("id_a")
    id_b = data.get("id_b")
    solo_activos = data.get("solo_activos", True)

    if not id_a or not id_b or int(id_a) == int(id_b):
        raise HTTPException(400, "Seleccioná dos vendedores distintos")

    def q_leads(uid):
        q = db.query(Lead).filter(Lead.asesor_apertura_id == int(uid))
        if solo_activos:
            q = q.filter(Lead.estado.notin_(["CERRADO", "PERDIDO"]))
        return q.all()

    leads_a = q_leads(id_a)
    leads_b = q_leads(id_b)
    ts = datetime.now().strftime("%d/%m %H:%M")
    nom_a = db.query(Usuario).filter(Usuario.id == int(id_a)).first()
    nom_b = db.query(Usuario).filter(Usuario.id == int(id_b)).first()

    for lead in leads_a:
        lead.asesor_apertura_id = int(id_b)
        lead.notas = (lead.notas or "") + f"\n[{ts}] ↔ Intercambiado con {nom_b.nombre if nom_b else id_b} por admin"
    for lead in leads_b:
        lead.asesor_apertura_id = int(id_a)
        lead.notas = (lead.notas or "") + f"\n[{ts}] ↔ Intercambiado con {nom_a.nombre if nom_a else id_a} por admin"

    db.commit()
    return {
        "ok": True,
        "intercambiados_a_b": len(leads_a),
        "intercambiados_b_a": len(leads_b),
        "total": len(leads_a) + len(leads_b),
    }


@router.post("/api/leads/reasignar-masivo")
async def reasignar_masivo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """Reasigna un lote de leads. asesor_id=None → round-robin automático."""
    data = await request.json()
    ids = data.get("ids", [])
    asesor_id = data.get("asesor_id")  # None = round-robin

    if not ids:
        raise HTTPException(400, "No hay leads seleccionados")

    # Solo se reparten los NO contactados (NUEVO) y los contactados sin resultado (INTENTADO).
    # Los que ya están en la base RELLAMADOS se reparten desde "DISTRIBUIR RELLAMADOS".
    ESTADOS_REDISTRIBUIBLES = ["NUEVO", "INTENTADO"]

    reasignados = 0
    omitidos = 0
    for lead_id in ids:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            continue
        # Solo redistribuir leads no contactados / sin resultado, fuera de la base RELLAMADOS
        if lead.estado not in ESTADOS_REDISTRIBUIBLES or lead.en_rellamados:
            omitidos += 1
            continue
        nuevo_id = int(asesor_id) if asesor_id else asignar_asesor_round_robin(db)
        if nuevo_id:
            lead.asesor_apertura_id = nuevo_id
            ts = datetime.now().strftime("%d/%m %H:%M")
            lead.notas = (lead.notas or "") + f"\n[{ts}] 👤 Reasignado manualmente por {current_user.nombre}"
        reasignados += 1

    db.commit()
    return {"ok": True, "reasignados": reasignados, "omitidos": omitidos}


@router.post("/api/leads/asignar-a-agentes-ia")
async def asignar_a_agentes_ia(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """
    Transfiere leads sin respuesta a los agentes IA del pool.
    Distribuye en round-robin entre los agentes IA activos.
    Si se pasan ids específicos los usa; si no, toma leads NUEVO/INTENTADO sin actividad reciente.
    """
    data = await request.json()
    ids_especificos = data.get("ids", [])
    limite = int(data.get("limite", 50))
    agente_ia_id = data.get("agente_ia_id")  # agente específico, o None = round-robin entre IAs

    # Buscar agentes IA activos
    agentes_ia = db.query(Usuario).filter(
        Usuario.es_agente_ia == True,
        Usuario.activo == True,
    ).all()
    if not agentes_ia:
        raise HTTPException(400, "No hay agentes IA activos configurados. Creá usuarios con el flag 'es_agente_ia' en Usuarios.")

    if ids_especificos:
        leads_q = db.query(Lead).filter(Lead.id.in_(ids_especificos))
    else:
        leads_q = db.query(Lead).filter(
            Lead.estado.in_(["NUEVO", "INTENTADO"]),
            or_(Lead.en_rellamados.is_(None), Lead.en_rellamados == False),
        ).limit(limite)

    leads = leads_q.all()
    if not leads:
        raise HTTPException(400, "No hay leads disponibles para asignar")

    # Round-robin entre agentes IA
    agentes_pool = [agentes_ia[i % len(agentes_ia)] for i in range(len(leads))]
    if agente_ia_id:
        agente_fijo = next((a for a in agentes_ia if a.id == int(agente_ia_id)), None)
        if agente_fijo:
            agentes_pool = [agente_fijo] * len(leads)

    asignados = 0
    ts = datetime.now().strftime("%d/%m %H:%M")
    for lead, agente in zip(leads, agentes_pool):
        lead.asesor_apertura_id = agente.id
        lead.notas = (lead.notas or "") + f"\n[{ts}] 🤖 Asignado a agente IA {agente.nombre} por {current_user.nombre}"
        asignados += 1

    db.commit()
    agentes_usados = list({a.nombre for a in agentes_pool})
    return {
        "ok": True,
        "asignados": asignados,
        "agentes_usados": agentes_usados,
        "mensaje": f"{asignados} leads asignados a: {', '.join(agentes_usados)}",
    }


@router.get("/api/leads/sin-contactar")
async def leads_sin_contactar(
    horas: int = 24,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Leads no contactados (NUEVO/INTENTADO) sin actividad en las últimas N horas (para el dashboard admin). Excluye la base RELLAMADOS."""
    roles = get_user_roles(current_user)
    limite = datetime.now() - timedelta(hours=horas)
    q = db.query(Lead).filter(
        Lead.estado.in_(["NUEVO", "INTENTADO"]),
        or_(Lead.en_rellamados.is_(None), Lead.en_rellamados == False),
        or_(
            and_(Lead.updated_at.isnot(None), Lead.updated_at <= limite),
            and_(Lead.updated_at.is_(None), Lead.created_at <= limite),
        )
    )
    if "ASESOR_APERTURA" in roles and "ADMIN" not in roles:
        q = q.filter(Lead.asesor_apertura_id == current_user.id)
    leads = q.order_by(Lead.created_at.asc()).limit(50).all()
    return [lead_to_dict(l, db) for l in leads]


@router.post("/api/leads/{lead_id}/incrementar-seguimiento")
async def incrementar_seguimiento(
    lead_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user)
):
    """Incrementa intentos_seguimiento del lead. Usado por el scheduler de agentes IA."""
    auth_ok = (x_api_key and x_api_key == API_KEY) or bool(current_user)
    if not auth_ok:
        raise HTTPException(401, "No autorizado")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    lead.intentos_seguimiento = (lead.intentos_seguimiento or 0) + 1
    if lead.intentos_seguimiento >= 3:
        lead.estado = "FRIO"
    db.commit()
    return {"ok": True, "intentos": lead.intentos_seguimiento, "estado": lead.estado}


@router.get("/api/leads/{lead_id}")
async def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    return lead_to_dict(lead, db)


@router.put("/api/leads/{lead_id}")
async def update_lead(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    old_estado = lead.estado

    for field in ["nombre", "telefono", "localidad", "producto_interes", "modelo_especifico",
                  "forma_pago", "estado", "asesor_apertura_id", "supervisor_cierre_id",
                  "origen", "notas"]:
        if field in data:
            setattr(lead, field, data[field])

    if "proximo_seguimiento" in data:
        try:
            lead.proximo_seguimiento = datetime.fromisoformat(data["proximo_seguimiento"]) if data["proximo_seguimiento"] else None
        except Exception:
            pass

    # Auto-create videollamada when status changes to VIDEOLLAMADA_AGENDADA
    if data.get("estado") == "VIDEOLLAMADA_AGENDADA" and old_estado != "VIDEOLLAMADA_AGENDADA":
        vl = Videollamada(
            lead_id=lead.id,
            cliente_nombre=lead.nombre,
            cliente_telefono=lead.telefono,
            producto_interes=lead.producto_interes,
            forma_pago=lead.forma_pago,
            asesor_apertura_id=lead.asesor_apertura_id,
            supervisor_cierre_id=lead.supervisor_cierre_id,
            estado="AGENDADA",
        )
        db.add(vl)

    db.commit()
    return {"ok": True}


@router.put("/api/leads/{lead_id}/estado")
async def update_lead_estado(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    data = await request.json()
    old_estado = lead.estado
    lead.estado = data["estado"]

    if data["estado"] == "VIDEOLLAMADA_AGENDADA" and old_estado != "VIDEOLLAMADA_AGENDADA":
        vl = Videollamada(
            lead_id=lead.id,
            cliente_nombre=lead.nombre,
            cliente_telefono=lead.telefono,
            producto_interes=lead.producto_interes,
            forma_pago=lead.forma_pago,
            asesor_apertura_id=lead.asesor_apertura_id,
            estado="AGENDADA",
        )
        db.add(vl)

    db.commit()
    return {"ok": True}


@router.delete("/api/leads/{lead_id}")
async def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    db.delete(lead)
    db.commit()
    return {"ok": True}


@router.get("/api/leads/{lead_id}/interacciones")
async def get_interacciones(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Historial de interacciones de un lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    items = db.query(Interaccion).filter(
        Interaccion.lead_id == lead_id
    ).order_by(Interaccion.created_at.asc()).all()
    return [
        {
            "id": i.id,
            "tipo": i.tipo,
            "resultado": i.resultado,
            "notas": i.notas or "",
            "asesor_id": i.asesor_id,
            "asesor_nombre": i.asesor.nombre if i.asesor else "",
            "created_at": i.created_at.isoformat() if i.created_at else "",
        }
        for i in items
    ]


@router.post("/api/leads/{lead_id}/interacciones")
async def create_interaccion(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """
    Registra una interacción con el lead.
    tipo: WHATSAPP|LLAMADA|EMAIL|NOTA|VISITA|VENTA
    resultado: ENVIADO|RESPONDIO|ATENDIO|NO_ATENDIO|NO_CONTESTA|NUMERO_INVALIDO|NO_INTERESA|INTERESADO|VENTA_CONCRETADA
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    tipo = data.get("tipo", "NOTA").upper()
    resultado = data.get("resultado", "ENVIADO").upper()
    notas = data.get("notas", "")

    interaccion = Interaccion(
        lead_id=lead_id,
        tipo=tipo,
        resultado=resultado,
        notas=notas,
        asesor_id=current_user.id,
    )
    db.add(interaccion)

    # Actualizar estado del lead según resultado
    if resultado == "NO_CONTESTA" and lead.estado == "NUEVO":
        lead.estado = "INTENTADO"
    elif resultado in ("RESPONDIO", "ATENDIO", "INTERESADO") and lead.estado in ("NUEVO", "INTENTADO"):
        lead.estado = "CONTACTADO"
    elif resultado == "INTERESADO":
        lead.estado = "EN_SEGUIMIENTO"
    elif resultado == "VENTA_CONCRETADA":
        lead.estado = "CERRADO_GANADO"
    elif resultado == "NO_INTERESA":
        pass  # solo sugiere cerrar, no lo cierra automáticamente

    # Programar próximo intento si no contestó
    if resultado == "NO_CONTESTA" and "proximo_seguimiento" not in data:
        lead.proximo_seguimiento = datetime.now() + timedelta(hours=4)
    elif "proximo_seguimiento" in data and data["proximo_seguimiento"]:
        try:
            lead.proximo_seguimiento = datetime.fromisoformat(data["proximo_seguimiento"])
        except Exception:
            pass

    db.commit()
    db.refresh(interaccion)

    # Notificar si el lead está interesado
    if resultado == "INTERESADO":
        try:
            from routers.notificaciones import notificar_todos
            notificar_todos(
                db,
                titulo="🔥 Lead interesado",
                mensaje=f"{lead.nombre} mostró interés — {lead.producto_interes}",
                tipo="LEAD",
                referencia_id=lead_id,
                referencia_tipo="lead",
            )
            db.commit()
        except Exception as e:
            log.warning(f"Error notificando lead interesado: {e}")

    return {
        "ok": True,
        "id": interaccion.id,
        "lead_estado": lead.estado,
        "proximo_seguimiento": lead.proximo_seguimiento.isoformat() if lead.proximo_seguimiento else None,
    }


@router.post("/api/leads/redistribuir")
async def redistribuir_todos_los_leads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN"))
):
    """
    Redistribuye automáticamente leads NUEVO/INTENTADO entre los asesores del pool.
    Solo toca leads NO contactados. Los contactados quedan con su asesor.
    Opcional: desde_asesor_id para redistribuir solo de un asesor específico.
    """
    data = await request.json()
    desde_asesor_id = data.get("desde_asesor_id")

    # Solo se reparten NUEVO (no contactado) e INTENTADO (contactado sin resultado),
    # excluyendo los que ya pasaron a la base RELLAMADOS.
    ESTADOS_REDISTRIBUIBLES = ["NUEVO", "INTENTADO"]
    MAX_RECIRCULACIONES = 3

    q = db.query(Lead).filter(
        Lead.estado.in_(ESTADOS_REDISTRIBUIBLES),
        or_(Lead.en_rellamados.is_(None), Lead.en_rellamados == False),
    )
    if desde_asesor_id:
        q = q.filter(Lead.asesor_apertura_id == int(desde_asesor_id))
    leads = q.all()

    if not leads:
        return {"ok": True, "reasignados": 0, "total": 0, "movidos_rellamados": 0,
                "mensaje": "No hay leads para redistribuir"}

    reasignados = 0
    movidos_rellamados = 0
    ts = datetime.now().strftime("%d/%m %H:%M")

    for lead in leads:
        # Los INTENTADO (ya contactados sin resultado) se recirculan un máximo de 3 veces.
        # Al agotarlas pasan a la base RELLAMADOS y dejan de redistribuirse aquí.
        if lead.estado == "INTENTADO":
            nuevo_recirc = (lead.veces_recirculado or 0) + 1
            if nuevo_recirc > MAX_RECIRCULACIONES:
                lead.en_rellamados = True
                lead.asesor_apertura_id = None
                lead.notas = (lead.notas or "") + f"\n[{ts}] 📥 Pasó a base RELLAMADOS (agotó {MAX_RECIRCULACIONES} recirculaciones)"
                movidos_rellamados += 1
                continue
            lead.veces_recirculado = nuevo_recirc

        nuevo_id = asignar_asesor_round_robin(db)
        if not nuevo_id:
            continue
        if nuevo_id == lead.asesor_apertura_id:
            continue
        u = db.query(Usuario).filter(Usuario.id == nuevo_id).first()
        lead.asesor_apertura_id = nuevo_id
        lead.notas = (lead.notas or "") + f"\n[{ts}] 🔀 Redistribuido a {u.nombre if u else nuevo_id} por {current_user.nombre}"
        reasignados += 1

    db.commit()
    return {"ok": True, "reasignados": reasignados, "total": len(leads),
            "movidos_rellamados": movidos_rellamados}


@router.get("/api/leads/rellamados/resumen")
async def rellamados_resumen(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN", "SUPERVISOR_CIERRE"))
):
    """Resumen de la base RELLAMADOS: total disponible + lista de asesores destino."""
    total = db.query(Lead).filter(Lead.en_rellamados == True).count()

    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    destinos = []
    for u in asesores:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []
        if "ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles:
            destinos.append({"id": u.id, "nombre": u.nombre})
    destinos.sort(key=lambda d: d["nombre"].lower())
    return {"ok": True, "total": total, "asesores": destinos}


@router.post("/api/leads/rellamados/distribuir")
async def distribuir_rellamados(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("ADMIN", "SUPERVISOR_CIERRE"))
):
    """
    Distribuye leads de la base RELLAMADOS a un asesor.
    Body: { asesor_id: int, cantidad: int }
    Los leads salen de la base RELLAMADOS, se reinicia su contador de recirculación
    y quedan asignados al asesor elegido para volver a llamarlos.
    """
    data = await request.json()
    asesor_id = data.get("asesor_id")
    cantidad = int(data.get("cantidad") or 0)

    if not asesor_id:
        raise HTTPException(400, "Seleccioná un asesor destino")
    if cantidad <= 0:
        raise HTTPException(400, "Indicá una cantidad mayor a cero")

    asesor = db.query(Usuario).filter(Usuario.id == int(asesor_id)).first()
    if not asesor:
        raise HTTPException(404, "Asesor no encontrado")

    leads = (
        db.query(Lead)
        .filter(Lead.en_rellamados == True)
        .order_by(Lead.created_at.asc())
        .limit(cantidad)
        .all()
    )

    if not leads:
        return {"ok": True, "distribuidos": 0, "mensaje": "No hay datos en la base RELLAMADOS"}

    ts = datetime.now().strftime("%d/%m %H:%M")
    distribuidos = 0
    for lead in leads:
        lead.en_rellamados = False
        lead.veces_recirculado = 0
        lead.estado = "INTENTADO"
        lead.asesor_apertura_id = asesor.id
        lead.notas = (lead.notas or "") + f"\n[{ts}] ♻️ Distribuido desde RELLAMADOS a {asesor.nombre} por {current_user.nombre}"
        distribuidos += 1

    db.commit()
    restantes = db.query(Lead).filter(Lead.en_rellamados == True).count()
    return {
        "ok": True,
        "distribuidos": distribuidos,
        "asesor": asesor.nombre,
        "restantes": restantes,
        "mensaje": f"{distribuidos} datos enviados a {asesor.nombre}",
    }


@router.post("/api/leads/importar")
async def importar_leads(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    import pandas as pd

    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Error leyendo archivo: {e}")

    col_map = {
        "nombre": ["nombre", "name", "cliente"],
        "telefono": ["telefono", "teléfono", "phone", "tel"],
        "localidad": ["localidad", "ciudad", "city", "ubicacion"],
        "producto_interes": ["producto", "product", "producto_interes"],
        "forma_pago": ["forma_pago", "pago", "payment"],
        "notas": ["notas", "notes", "observaciones"],
    }

    def find_col(df, keys):
        for k in keys:
            for col in df.columns:
                if col.lower().strip() == k.lower():
                    return col
        return None

    created = 0
    errors = []

    for _, row in df.iterrows():
        try:
            nombre_col = find_col(df, col_map["nombre"])
            tel_col = find_col(df, col_map["telefono"])
            if not nombre_col or not tel_col:
                errors.append("Columnas 'nombre' y 'telefono' son requeridas")
                break
            nombre = str(row[nombre_col]).strip()
            telefono = str(row[tel_col]).strip()
            if not nombre or nombre == "nan":
                continue

            loc_col = find_col(df, col_map["localidad"])
            prod_col = find_col(df, col_map["producto_interes"])
            pago_col = find_col(df, col_map["forma_pago"])
            notas_col = find_col(df, col_map["notas"])

            lead = Lead(
                nombre=nombre,
                telefono=telefono,
                localidad=str(row[loc_col]).strip() if loc_col else "",
                producto_interes=str(row[prod_col]).strip().upper() if prod_col else "SIN_DEFINIR",
                forma_pago=str(row[pago_col]).strip().upper() if pago_col else "SIN_DEFINIR",
                notas=str(row[notas_col]).strip() if notas_col else "",
                asesor_apertura_id=current_user.id,
                origen="IMPORTADO",
                estado="NUEVO",
            )
            db.add(lead)
            created += 1
        except Exception as e:
            errors.append(str(e))

    db.commit()
    return {"importados": created, "errores": errors[:10]}
