"""
Bandeja de entrada WhatsApp — CRM EcoFiver

Permite al admin:
- Ver todas las conversaciones en tiempo real
- Responder manualmente (modo humano)
- Delegar a los agentes IA (modo bot)
- Asignar / cambiar agente durante la conversación
- Pausar la conversación

API usada por el multiagente para notificar mensajes entrantes y salientes.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.database import get_db
from database.models import Lead, InboxMensaje, MetaPagina
from routers.auth import require_auth, get_user_roles
from utils.whatsapp import send_whatsapp_text

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Clave API compartida con el multiagente
MULTIAGENTE_API_KEY = os.getenv("CRM_API_KEY", "eco-crm-api-key-2024")

# Agentes IA disponibles en el multiagente (excluyendo líneas de vendedores)
AGENTES = ["valentina", "pablo", "laura", "sabrina", "claudio"]
AGENTES_IA_REDISTRIBUCION = AGENTES  # alias para redistribución de leads

# Línea WhatsApp de agentes IA
WA_PHONE_ID_AGENTES = "1037947576071396"   # 1168733406 — línea agentes IA

_META_API_BASE = "https://graph.facebook.com/v22.0"


async def _get_vendor_line(db: Session, wa_phone_id: str | None) -> MetaPagina | None:
    """Devuelve la MetaPagina si el wa_phone_id corresponde a una línea de vendedor.
    Si no encuentra por ID pero hay una entrada pendiente (wa_phone_id=NULL), intenta
    auto-descubrir usando la API de Meta para obtener el número de display.
    """
    if not wa_phone_id:
        return None

    # Búsqueda directa por phone_number_id
    linea = db.query(MetaPagina).filter(
        MetaPagina.wa_phone_id == wa_phone_id,
        MetaPagina.vendedor_slug.isnot(None),
        MetaPagina.activa == True,
    ).first()
    if linea:
        return linea

    # Auto-descubrimiento: ¿hay entradas pendientes sin wa_phone_id?
    pendientes = db.query(MetaPagina).filter(
        MetaPagina.wa_phone_id.is_(None),
        MetaPagina.vendedor_slug.isnot(None),
        MetaPagina.activa == True,
    ).all()
    if not pendientes:
        return None

    # Consultar Meta API para obtener display_phone_number de esta línea desconocida
    try:
        token = os.getenv("WA_TOKEN", "")
        if not token:
            return None
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(
                f"{_META_API_BASE}/{wa_phone_id}",
                params={"fields": "display_phone_number"},
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            return None
        display = r.json().get("display_phone_number", "")
        if not display:
            return None

        digits = "".join(ch for ch in display if ch.isdigit())
        for p in pendientes:
            if not p.numero_whatsapp:
                continue
            p_digits = "".join(ch for ch in p.numero_whatsapp if ch.isdigit())
            if digits[-9:] == p_digits[-9:]:
                p.wa_phone_id = wa_phone_id
                db.commit()
                log.info(f"[inbox] Auto-descubierto phone_id {wa_phone_id} → {p.vendedor_slug} ({display})")
                return p
    except Exception as exc:
        log.warning(f"[inbox] Auto-descubrimiento falló para {wa_phone_id}: {exc}")

    return None

# SSE: set de colas activas por sesión
_sse_queues: list[asyncio.Queue] = []


def _push_sse(event: dict):
    """Envía un evento SSE a todos los clientes conectados."""
    for q in list(_sse_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ─── AUTENTICACIÓN MULTIAGENTE ────────────────────────────────────────────────

def _check_api_key(request: Request):
    key = request.headers.get("X-API-Key", "")
    if key != MULTIAGENTE_API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida")


# ─── PÁGINA PRINCIPAL ─────────────────────────────────────────────────────────

@router.get("/inbox", response_class=HTMLResponse, include_in_schema=False)
async def inbox_page(request: Request, current_user=Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("inbox.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "agentes": AGENTES,
    })


# ─── API — CONVERSACIONES ─────────────────────────────────────────────────────

@router.get("/api/inbox/lineas")
async def listar_lineas(
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Devuelve las líneas WA configuradas como bandejas.

    Incluye líneas con wa_phone_id conocido Y líneas de vendedores pendientes
    de auto-descubrimiento (wa_phone_id=NULL con vendedor_slug asignado).
    """
    from sqlalchemy import or_
    paginas = (
        db.query(MetaPagina)
        .filter(
            MetaPagina.activa == True,
            or_(
                MetaPagina.wa_phone_id.isnot(None),
                MetaPagina.vendedor_slug.isnot(None),
            ),
        )
        .order_by(MetaPagina.nombre)
        .all()
    )
    # Deduplicar por wa_phone_id cuando está disponible
    seen: set = set()
    result = []
    for p in paginas:
        key = p.wa_phone_id or f"pendiente:{p.page_id}"
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "page_id": p.page_id,
            "nombre": p.nombre,
            "vendedor": p.vendedor or p.nombre,
            "numero_whatsapp": p.numero_whatsapp,
            "wa_phone_id": p.wa_phone_id,
            "portafolio": p.portafolio,
            "pendiente": p.wa_phone_id is None,
        })
    return result


@router.get("/api/inbox/conversaciones")
async def listar_conversaciones(
    linea: str = "",   # page_id de MetaPagina para filtrar (vacío = todas)
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Lista de conversaciones activas ordenadas por último mensaje."""
    from sqlalchemy import func as sqlfunc

    # Resolver wa_phone_id de la línea pedida
    wa_phone_id_filter: str | None = None
    if linea:
        pag = db.query(MetaPagina).filter(MetaPagina.page_id == linea).first()
        if pag:
            wa_phone_id_filter = pag.wa_phone_id or None

    # Subquery: último mensaje por phone
    sub_q = db.query(
        InboxMensaje.phone,
        sqlfunc.max(InboxMensaje.created_at).label("ultimo_at"),
    )
    if wa_phone_id_filter:
        sub_q = sub_q.filter(InboxMensaje.wa_linea == wa_phone_id_filter)

    sub = sub_q.group_by(InboxMensaje.phone).subquery()
    rows = (
        db.query(InboxMensaje, sub.c.ultimo_at)
        .join(sub, InboxMensaje.phone == sub.c.phone)
        .filter(InboxMensaje.created_at == sub.c.ultimo_at)
        .order_by(sub.c.ultimo_at.desc())
        .limit(100)
        .all()
    )

    result = []
    for msg, ultimo_at in rows:
        no_leidos = (
            db.query(InboxMensaje)
            .filter(
                InboxMensaje.phone == msg.phone,
                InboxMensaje.direccion == "IN",
                InboxMensaje.leido == False,
            )
            .count()
        )

        # Default según la línea: vendedor → humano, agentes IA → bot
        linea_db = (
            db.query(MetaPagina).filter(
                MetaPagina.wa_phone_id == msg.wa_linea,
                MetaPagina.vendedor_slug.isnot(None),
                MetaPagina.activa == True,
            ).first()
            if msg.wa_linea else None
        )
        modo_default   = "humano" if linea_db else "bot"
        agente_default = linea_db.vendedor_slug if linea_db else "valentina"
        modo = modo_default
        agente = agente_default
        lead_id = None
        nombre = msg.nombre_contacto or msg.phone
        if msg.lead_id:
            lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
            if lead:
                modo = lead.modo_atencion or modo_default
                agente = lead.agente_asignado or agente_default
                lead_id = lead.id
                nombre = lead.nombre or msg.nombre_contacto or msg.phone

        result.append({
            "phone": msg.phone,
            "nombre": nombre,
            "lead_id": lead_id,
            "ultimo_mensaje": msg.contenido[:80] if msg.contenido else "",
            "ultimo_at": ultimo_at.isoformat() if ultimo_at else None,
            "no_leidos": no_leidos,
            "modo": modo,
            "agente": agente,
            "direccion": msg.direccion,
            "wa_linea": msg.wa_linea or "",
        })

    return result


@router.get("/api/inbox/conversaciones/{phone}/mensajes")
async def get_mensajes(
    phone: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Mensajes de una conversación. Marca todos como leídos."""
    mensajes = (
        db.query(InboxMensaje)
        .filter(InboxMensaje.phone == phone)
        .order_by(InboxMensaje.created_at.asc())
        .limit(200)
        .all()
    )

    # Marcar como leídos
    db.query(InboxMensaje).filter(
        InboxMensaje.phone == phone,
        InboxMensaje.direccion == "IN",
        InboxMensaje.leido == False,
    ).update({"leido": True})
    db.commit()

    # Info del lead
    lead_info = None
    if mensajes and mensajes[0].lead_id:
        lead = db.query(Lead).filter(Lead.id == mensajes[0].lead_id).first()
        if lead:
            lead_info = {
                "id": lead.id,
                "nombre": lead.nombre,
                "modo": lead.modo_atencion or "bot",
                "agente": lead.agente_asignado or "valentina",
                "estado": lead.estado,
            }

    return {
        "lead": lead_info,
        "mensajes": [
            {
                "id": m.id,
                "direccion": m.direccion,
                "contenido": m.contenido,
                "remitente": m.remitente,
                "leido": m.leido,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mensajes
        ],
    }


@router.get("/api/inbox/modo/{phone}")
async def get_modo(phone: str, db: Session = Depends(get_db)):
    """El multiagente consulta el modo antes de responder. Sin auth (interna)."""
    # Buscar lead por teléfono
    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    lead = db.query(Lead).filter(Lead.telefono.contains(phone_clean[-9:])).first()
    if not lead:
        return {"modo": "bot", "agente": "valentina", "lead_id": None}
    return {
        "modo": lead.modo_atencion or "bot",
        "agente": lead.agente_asignado or "valentina",
        "lead_id": lead.id,
    }


# ─── API — CAMBIAR MODO / AGENTE ──────────────────────────────────────────────

class ModoPayload(BaseModel):
    modo: str  # bot | humano | pausado

class AgentePayload(BaseModel):
    agente: str

@router.post("/api/inbox/conversaciones/{lead_id}/modo")
async def cambiar_modo(
    lead_id: int,
    payload: ModoPayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    if payload.modo not in ("bot", "humano", "pausado"):
        raise HTTPException(400, "Modo inválido")
    lead.modo_atencion = payload.modo
    db.commit()
    _push_sse({"type": "modo_cambiado", "lead_id": lead_id, "modo": payload.modo, "phone": lead.telefono})
    return {"ok": True, "modo": payload.modo}


@router.post("/api/inbox/conversaciones/{lead_id}/agente")
async def cambiar_agente(
    lead_id: int,
    payload: AgentePayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    if payload.agente not in AGENTES:
        raise HTTPException(400, "Agente inválido")
    lead.agente_asignado = payload.agente
    db.commit()
    _push_sse({"type": "agente_cambiado", "lead_id": lead_id, "agente": payload.agente, "phone": lead.telefono})
    return {"ok": True, "agente": payload.agente}


# ─── API — RESPONDER MANUALMENTE ─────────────────────────────────────────────

class RespuestaPayload(BaseModel):
    phone: str
    texto: str
    lead_id: int | None = None

@router.post("/api/inbox/conversaciones/responder")
async def responder_manualmente(
    payload: RespuestaPayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Admin responde manualmente a un número via WhatsApp."""
    ok = send_whatsapp_text(db, payload.phone, payload.texto)
    if not ok:
        raise HTTPException(500, "No se pudo enviar el mensaje por WhatsApp")

    # Guardar en inbox
    msg = InboxMensaje(
        lead_id=payload.lead_id,
        phone=payload.phone.replace("+", "").replace(" ", ""),
        direccion="OUT",
        contenido=payload.texto,
        remitente=f"admin:{current_user.nombre}",
        leido=True,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    evento = {
        "type": "nuevo_mensaje",
        "phone": payload.phone,
        "id": msg.id,
        "direccion": "OUT",
        "contenido": payload.texto,
        "remitente": f"admin:{current_user.nombre}",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
    _push_sse(evento)
    return {"ok": True, "id": msg.id}


# ─── API — ENTRANTE DESDE MULTIAGENTE ────────────────────────────────────────

class MensajeEntrante(BaseModel):
    phone: str
    nombre: str | None = None
    direccion: str       # IN | OUT
    contenido: str
    remitente: str | None = None   # "cliente" | agente_name
    lead_id: int | None = None
    wa_message_id: str | None = None
    wa_linea: str | None = None    # número del vendedor que recibió/envió (display number)

@router.post("/api/inbox/entrante")
async def recibir_entrante(
    payload: MensajeEntrante,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    El multiagente llama este endpoint cada vez que llega o sale un mensaje WA.
    Autenticado por X-API-Key.
    """
    _check_api_key(request)

    phone = payload.phone.replace("+", "").replace(" ", "").replace("-", "")
    wa_linea_clean = (payload.wa_linea or "").replace("+", "").replace(" ", "") or None

    # Determinar si es una línea de vendedor vía MetaPagina (DB-driven, con auto-descubrimiento)
    linea_vendedor = await _get_vendor_line(db, wa_linea_clean)
    es_linea_vendedor = linea_vendedor is not None

    # Asociar o crear lead
    _nombre_raw = (payload.nombre or "").strip()
    _nombre_negocio = {"melanie", "melanie eco", "ecomodulos", "eco modulos", "ecofiver"}
    lead_id = payload.lead_id
    nombre = _nombre_raw if _nombre_raw and _nombre_raw.lower() not in _nombre_negocio else phone
    if not lead_id:
        lead = db.query(Lead).filter(Lead.telefono.contains(phone[-9:])).first()
        if lead:
            lead_id = lead.id
            nombre = lead.nombre or nombre
            # Si la línea es de la vendedora, asegurar modo humano
            if es_linea_vendedor and lead.modo_atencion != "humano":
                lead.modo_atencion = "humano"
                db.commit()
        elif es_linea_vendedor and payload.direccion == "IN":
            # Auto-crear lead para mensajes entrantes de la línea vendedora
            new_lead = Lead(
                nombre=nombre,
                telefono=phone,
                origen="WHATSAPP",
                utm_source="meta",
                utm_medium="ads",
                modo_atencion="humano",
                agente_asignado=linea_vendedor.vendedor_slug,
                estado="NUEVO",
                aliado_codigo=linea_vendedor.aliado_codigo or "",
            )
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)
            lead_id = new_lead.id

    msg = InboxMensaje(
        lead_id=lead_id,
        phone=phone,
        nombre_contacto=nombre,
        direccion=payload.direccion,
        contenido=payload.contenido,
        remitente=payload.remitente or ("cliente" if payload.direccion == "IN" else "agente"),
        leido=(payload.direccion == "OUT"),  # los salientes ya están "leídos"
        wa_message_id=payload.wa_message_id,
        wa_linea=(payload.wa_linea or "").replace("+", "").replace(" ", "") or None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    evento = {
        "type": "nuevo_mensaje",
        "phone": phone,
        "nombre": nombre,
        "lead_id": lead_id,
        "id": msg.id,
        "direccion": payload.direccion,
        "contenido": payload.contenido,
        "remitente": msg.remitente,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
    _push_sse(evento)
    return {"ok": True, "id": msg.id}


# ─── SSE — TIEMPO REAL ───────────────────────────────────────────────────────

@router.get("/api/inbox/stream")
async def inbox_stream(request: Request, current_user=Depends(require_auth)):
    """Server-Sent Events — el admin recibe actualizaciones en tiempo real."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            try:
                _sse_queues.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
