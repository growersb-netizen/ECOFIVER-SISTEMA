"""
Handler de WhatsApp Business API Meta para EcoFiver.
Incluye debounce: acumula mensajes por 3.5 seg y responde una sola vez.
"""

import asyncio
import os
import logging
from collections import defaultdict
import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from orchestrator.router import route_message
from tools.audio_transcriber import transcribir_bytes

load_dotenv()

logger = logging.getLogger(__name__)

WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "eco_modules_verify_2026")

# IDs de los números de negocio registrados en la WABA
WA_PHONE_ID_AGENTES = os.getenv("WA_PHONE_ID_AGENTES", "")   # 1168733406
WA_PHONE_ID_MELANIE = os.getenv("WA_PHONE_ID_MELANIE", "")   # 1126036495

# ── Número admin de Rodrigo — canal privado con Máximo ───────────────────────
ADMIN_WA_PHONES: set[str] = {"5491135164644"}

# ── CRM Inbox integration ─────────────────────────────────────────────────────
CRM_BASE_URL = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app")
CRM_API_KEY  = os.getenv("CRM_API_KEY", "eco-crm-api-key-2024")
_CRM_HEADERS = {"X-API-Key": CRM_API_KEY, "Content-Type": "application/json"}


async def _crm_get_modo(phone: str) -> str:
    """Consulta al CRM si la conversación está en modo bot o humano."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{CRM_BASE_URL}/api/inbox/modo/{phone}")
        if r.status_code == 200:
            return r.json().get("modo", "bot")
    except Exception as e:
        logger.warning(f"[WA] No se pudo consultar modo CRM: {e}")
    return "bot"


async def _crm_push_mensaje(phone: str, direccion: str, contenido: str,
                             remitente: str = "", nombre: str = "",
                             lead_id: int | None = None,
                             wa_message_id: str | None = None):
    """Envía un mensaje al inbox del CRM (fire-and-forget)."""
    try:
        payload = {
            "phone": phone,
            "nombre": nombre,
            "direccion": direccion,
            "contenido": contenido,
            "remitente": remitente,
            "lead_id": lead_id,
            "wa_message_id": wa_message_id,
        }
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(f"{CRM_BASE_URL}/api/inbox/entrante",
                         json=payload, headers=_CRM_HEADERS)
    except Exception as e:
        logger.warning(f"[WA] No se pudo notificar al CRM inbox: {e}")

def _get_wa_token() -> str:
    # META_PAGE_ACCESS_TOKEN = System User (never-expiry, todas las WABAs del portfolio)
    return os.getenv("META_PAGE_ACCESS_TOKEN") or os.getenv("WA_TOKEN", "")

def _get_wa_phone_id() -> str:
    return os.getenv("WA_PHONE_ID", "")

META_API_BASE = "https://graph.facebook.com/v19.0"

router = APIRouter()

# ─────────────────────────────────────────────
# DEBOUNCE — acumula mensajes, responde una vez
# ─────────────────────────────────────────────

DEBOUNCE_SECS = 3.5  # espera esta cantidad de segundos tras el último mensaje

_pending_msgs: dict[str, list[dict]] = defaultdict(list)
_pending_tasks: dict[str, asyncio.Task] = {}


async def _enqueue_message(phone_number: str, msg_type: str, message: dict, phone_number_id: str = "") -> None:
    """Agrega el mensaje a la cola y reinicia el timer de debounce."""
    _pending_msgs[phone_number].append({"msg_type": msg_type, "message": message, "phone_number_id": phone_number_id})

    old = _pending_tasks.get(phone_number)
    if old and not old.done():
        old.cancel()

    _pending_tasks[phone_number] = asyncio.create_task(
        _fire_when_idle(phone_number)
    )


async def _fire_when_idle(phone_number: str) -> None:
    """Espera el periodo de debounce y procesa el lote acumulado."""
    try:
        await asyncio.sleep(DEBOUNCE_SECS)
    except asyncio.CancelledError:
        return  # Llegó otro mensaje — no procesar todavía

    batch = _pending_msgs.pop(phone_number, [])
    _pending_tasks.pop(phone_number, None)
    if batch:
        await _process_batch(phone_number, batch)


async def _process_batch(phone_number: str, batch: list[dict]) -> None:
    """
    Procesa todos los mensajes acumulados como una sola interacción.
    Transcribe audios, combina todos los textos y llama al agente una vez.
    """
    wa_msg_id = None
    textos: list[str] = []
    tiene_audio = False

    for item in batch:
        msg_type = item["msg_type"]
        message  = item["message"]
        wa_msg_id = wa_msg_id or message.get("id")

        if msg_type == "text":
            textos.append(message["text"]["body"])

        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            t = await _transcribir_audio(audio_id)
            if t and not any(t.startswith(p) for p in (
                "(Audio recibido", "(Audio vacio", "(sin metodo", "(inaudible"
            )):
                textos.append(t)
                tiene_audio = True

        elif msg_type == "image":
            cap = message["image"].get("caption", "")
            textos.append(f"[IMAGEN] {cap}" if cap else "[IMAGEN RECIBIDA]")

    if not textos:
        return

    texto      = "\n".join(textos)
    tipo_final = "audio_transcripto" if tiene_audio else "text"

    # Determinar qué número de negocio recibió el mensaje (para responder desde el mismo)
    incoming_phone_id = batch[0].get("phone_number_id", "") if batch else ""
    if WA_PHONE_ID_MELANIE and incoming_phone_id == WA_PHONE_ID_MELANIE:
        send_phone_id = WA_PHONE_ID_MELANIE
        canal_base    = "whatsapp_melanie"
    else:
        send_phone_id = incoming_phone_id or WA_PHONE_ID_AGENTES or _get_wa_phone_id()
        canal_base    = "whatsapp"

    is_admin = phone_number in ADMIN_WA_PHONES
    canal    = "whatsapp_admin" if is_admin else canal_base

    try:
        if not is_admin:
            await _crm_push_mensaje(
                phone=phone_number,
                direccion="IN",
                contenido=texto,
                remitente="cliente",
                wa_message_id=wa_msg_id,
            )
            modo = await _crm_get_modo(phone_number)
            if modo == "humano":
                logger.info(f"[WA] {phone_number} en modo HUMANO — bot silenciado")
                return
            if modo == "pausado":
                logger.info(f"[WA] {phone_number} PAUSADA — sin respuesta")
                return
        else:
            n = len(batch)
            logger.info(f"[WA] ADMIN ({phone_number}) → Máximo ({n} mensaje{'s' if n > 1 else ''})")

        # Melanie: la IA de Meta atiende ese número; solo registramos el contacto en CRM
        if canal_base == "whatsapp_melanie":
            logger.info(f"[WA/Melanie] {phone_number} registrado en CRM — sin respuesta del bot")
            return

        result = await route_message(canal, phone_number, texto, tipo_final)
        await enviar_mensaje_wa(phone_number, result["reply"], phone_id=send_phone_id)
        await _crm_push_mensaje(
            phone=phone_number,
            direccion="OUT",
            contenido=result["reply"],
            remitente=result.get("agent", "agente"),
        )

    except Exception as e:
        logger.error(f"[WA] Error procesando batch de {phone_number}: {e}")
        try:
            await enviar_mensaje_wa(
                phone_number,
                "Disculpá, tuve un problema técnico. En un momento te respondo. 🙏",
                phone_id=send_phone_id,
            )
        except Exception:
            pass


# ─────────────────────────────────────────────
# VERIFICACIÓN DEL WEBHOOK (GET)
# ─────────────────────────────────────────────

@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        logger.info("[WA] Webhook verificado correctamente.")
        return PlainTextResponse(content=challenge)

    logger.warning("[WA] Verificación fallida — token incorrecto.")
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


# ─────────────────────────────────────────────
# RECEPCIÓN DE MENSAJES (POST)
# ─────────────────────────────────────────────

@router.post("/webhook/whatsapp")
async def receive_message(request: Request, background: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    # Meta envuelve todo en entry[0].changes[0].value
    try:
        entry   = body["entry"][0]
        change  = entry["changes"][0]["value"]
        message = change["messages"][0]
    except (KeyError, IndexError):
        # Puede ser un status update u otro evento — logear para diagnóstico
        try:
            change_val = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
            statuses   = change_val.get("statuses", [])
            field      = body.get("entry", [{}])[0].get("changes", [{}])[0].get("field", "?")
            if statuses:
                st = statuses[0]
                logger.info(f"[WA] STATUS UPDATE recibido: status={st.get('status')} id={st.get('id')} phone={st.get('recipient_id')}")
            else:
                logger.info(f"[WA] WEBHOOK recibido (no-mensaje): field={field} body_keys={list(change_val.keys())}")
        except Exception:
            logger.info(f"[WA] WEBHOOK recibido (formato desconocido): {str(body)[:200]}")
        return {"status": "ignored"}

    phone_number    = message["from"]
    msg_type        = message.get("type", "text")
    phone_number_id = change.get("metadata", {}).get("phone_number_id", "")

    # Encolar con debounce — si llegan más mensajes en los próximos 3.5 seg
    # se procesan todos juntos como una sola interacción
    background.add_task(_enqueue_message, phone_number, msg_type, message, phone_number_id)
    return {"status": "accepted"}


async def _process_message(phone_number: str, msg_type: str, message: dict):
    """Procesa el mensaje en segundo plano para responder rápidamente a Meta."""
    wa_msg_id = message.get("id")
    texto = ""

    try:
        # ── Extraer texto del mensaje ────────────────────────────────────────
        if msg_type == "text":
            texto = message["text"]["body"]

        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            texto = await _transcribir_audio(audio_id)

            # Si la transcripción falló completamente, respondemos directo sin pasar al agente
            if not texto or texto.startswith("(Audio recibido") or texto.startswith("(Audio vacio") or texto.startswith("(sin metodo"):
                logger.warning(f"[WA] Transcripcion fallo para {phone_number} — respondiendo directo")
                await send_whatsapp_message(
                    phone_number,
                    "Recibí tu mensaje de voz 🎙️, pero en este momento tuve un problema técnico para procesarlo. "
                    "¿Podés escribirme lo que necesitás? Te respondo enseguida. 🙏"
                )
                return

        elif msg_type == "image":
            caption = message["image"].get("caption", "")
            texto = f"[IMAGEN] {caption}" if caption else "[IMAGEN RECIBIDA]"

        else:
            texto = f"[Mensaje tipo {msg_type}]"

        # ── Canal admin: Rodrigo → Máximo directo (sin verificar modo CRM) ──
        is_admin = phone_number in ADMIN_WA_PHONES
        canal = "whatsapp_admin" if is_admin else "whatsapp"

        if not is_admin:
            # ── Notificar mensaje entrante al CRM (solo clientes normales) ───
            await _crm_push_mensaje(
                phone=phone_number,
                direccion="IN",
                contenido=texto,
                remitente="cliente",
                wa_message_id=wa_msg_id,
            )

            # ── Verificar modo de atención ───────────────────────────────────
            modo = await _crm_get_modo(phone_number)

            if modo == "humano":
                logger.info(f"[WA] Conversación {phone_number} en modo HUMANO — bot silenciado")
                return

            if modo == "pausado":
                logger.info(f"[WA] Conversación {phone_number} PAUSADA — sin respuesta")
                return
        else:
            logger.info(f"[WA] Mensaje de ADMIN ({phone_number}) → Máximo")

        # ── Procesar con agentes ─────────────────────────────────────────────
        if msg_type == "text":
            result = await route_message(canal, phone_number, texto, "text")
        elif msg_type == "audio":
            result = await route_message(canal, phone_number, texto, "audio_transcripto")
        elif msg_type == "image":
            result = await route_message(canal, phone_number,
                                         f"[IMAGEN RECIBIDA] {texto}", "image")
        else:
            result = {
                "reply": "Recibí tu mensaje, en breve te respondo. 👋",
                "agent": "sistema",
            }

        # ── Enviar respuesta al cliente ──────────────────────────────────────
        await send_whatsapp_message(phone_number, result["reply"])

        # ── Notificar respuesta saliente al CRM ──────────────────────────────
        await _crm_push_mensaje(
            phone=phone_number,
            direccion="OUT",
            contenido=result["reply"],
            remitente=result.get("agent", "agente"),
        )

    except Exception as e:
        logger.error(f"[WA] Error procesando mensaje de {phone_number}: {e}")
        try:
            await send_whatsapp_message(
                phone_number,
                "Disculpá, tuve un problema técnico. En un momento te respondo. 🙏",
            )
        except Exception:
            pass


# ─────────────────────────────────────────────
# TRANSCRIPCIÓN DE AUDIO (WhatsApp)
# ─────────────────────────────────────────────

async def _transcribir_audio(audio_id: str) -> str:
    """
    Descarga el OGG desde Meta API y lo transcribe via módulo compartido.
    1. Obtiene media_url usando WA_TOKEN
    2. Descarga los bytes del OGG
    3. Transcribe con Gemini via tools.audio_transcriber
    """
    headers_meta = {"Authorization": f"Bearer {_get_wa_token()}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{META_API_BASE}/{audio_id}", headers=headers_meta)
            r.raise_for_status()
            media_url = r.json().get("url", "")
            if not media_url:
                logger.warning("[WA] No se pudo obtener media_url del audio")
                return "(No se pudo obtener el audio)"

            r2 = await client.get(media_url, headers=headers_meta)
            r2.raise_for_status()
            audio_bytes = r2.content

        return await transcribir_bytes(audio_bytes, mime_type="audio/ogg")

    except Exception as e:
        logger.error(f"[WA] Error descargando audio {audio_id}: {e}")
        return "(Audio recibido — no se pudo descargar)"


# ─────────────────────────────────────────────
# ENVÍO DE MENSAJES SALIENTES
# ─────────────────────────────────────────────

async def enviar_mensaje_wa(phone_number: str, text: str, phone_id: str | None = None) -> bool:
    """
    Envía un mensaje via Meta Graph API usando un phone_id específico.
    Usado por Franco (canal aliados) que tiene un número distinto al principal.
    Si phone_id es None, usa WA_PHONE_ID del entorno.
    """
    wa_token = _get_wa_token()
    wa_pid = phone_id or _get_wa_phone_id()
    if not wa_token or not wa_pid:
        logger.warning("[WA] enviar_mensaje_wa: token o phone_id no configurados")
        return False
    if len(text) > 4096:
        text = text[:4090] + "..."
    url = f"{META_API_BASE}/{wa_pid}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                logger.error(f"[WA] enviar_mensaje_wa HTTP {r.status_code} → {phone_number}")
                return False
            logger.info(f"[WA] enviar_mensaje_wa → {phone_number} (phone_id={wa_pid[:8]}…)")
            return True
    except Exception as e:
        logger.error(f"[WA] enviar_mensaje_wa error: {e}")
        return False


async def send_whatsapp_message(phone_number: str, text: str) -> bool:
    """
    Envía un mensaje de texto via Meta Graph API.

    Args:
        phone_number: número en formato internacional (ej: 5491112345678)
        text: texto del mensaje (máx 4096 chars)

    Returns:
        True si se envió correctamente
    """
    wa_token = _get_wa_token()
    wa_phone_id = _get_wa_phone_id()
    if not wa_token or not wa_phone_id:
        logger.warning("[WA] WA_TOKEN o WA_PHONE_ID no configurados")
        return False

    # Meta limita a 4096 chars por mensaje
    if len(text) > 4096:
        text = text[:4090] + "..."

    url = f"{META_API_BASE}/{wa_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {wa_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                try:
                    err_body = r.json()
                except Exception:
                    err_body = r.text[:500]
                logger.error(
                    f"[WA] Error HTTP {r.status_code} enviando a {phone_number}. "
                    f"Respuesta Meta: {err_body}"
                )
                return False
            logger.info(f"[WA] Mensaje enviado a {phone_number}")
            return True
    except Exception as e:
        logger.error(f"[WA] Error enviando mensaje a {phone_number}: {e}")
        return False


# ─────────────────────────────────────────────
# ENDPOINT PARA MENSAJES PROACTIVOS
# ─────────────────────────────────────────────

@router.post("/send/whatsapp")
async def proactive_send(request: Request):
    """
    Endpoint para que los agentes envíen mensajes proactivos.
    Usado por el scheduler (cobros, recordatorios, etc.)
    """
    try:
        body = await request.json()
        phone = body.get("phone_number")
        text  = body.get("text")
        if not phone or not text:
            raise HTTPException(status_code=400, detail="Faltan phone_number o text")
        ok = await send_whatsapp_message(phone, text)
        return {"status": "sent" if ok else "failed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WA] Error en proactive_send: {e}")
        raise HTTPException(status_code=500, detail=str(e))
