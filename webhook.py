"""
Webhook de WhatsApp — recibe y procesa mensajes entrantes.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
import asyncio

from config import WHATSAPP_VERIFY_TOKEN
from rate_limit import limiter
from logger import get_logger

log = get_logger(__name__)
from database import (
    get_or_create_conversation, update_conversation,
    save_message, get_conversation_messages, save_lead, mark_lead_notified
)
from router import get_agent_for_conversation, get_router_response
from audio import process_whatsapp_audio
from notifications import notify_qualified_lead, send_whatsapp_message
from agents import PabloAgent, LauraAgent, SabrinaAgent, ClaudioAgent

router = APIRouter()

AGENTS = {
    "pablo": PabloAgent(),
    "laura": LauraAgent(),
    "sabrina": SabrinaAgent(),
    "claudio": ClaudioAgent(),
}

LEAD_SCORE_THRESHOLD = {
    "caliente": True,
    "tibio": True,
}


async def get_agent_response(agent_name: str, history: list, message: str) -> str:
    """Obtiene respuesta del agente correspondiente."""
    agent = AGENTS.get(agent_name)
    if not agent:
        return get_router_response(history, message)
    return agent.generate_response(history, message)


async def check_and_notify_lead(
    conversation: dict,
    history: list,
    phone_number: str
):
    """Analiza si el lead califica para notificación y la envía."""
    if len(history) < 4:  # Esperamos al menos 4 mensajes
        return

    agent_name = conversation.get("agent")
    agent = AGENTS.get(agent_name)
    if not agent:
        return

    # Solo verificamos cada cierto número de mensajes
    if len(history) % 3 != 0:
        return

    score = agent.analyze_lead_score(history)
    info = agent.extract_lead_info(history, phone_number)

    # Actualizamos la conversación
    update_data = {"lead_score": score}
    if info.get("client_name"):
        update_data["client_name"] = info["client_name"]
    if info.get("product"):
        update_data["product"] = info["product"]
    if info.get("modality"):
        update_data["modality"] = info["modality"]
    if info.get("locality"):
        update_data["locality"] = info["locality"]

    update_conversation(conversation["id"], **update_data)

    # Guardamos el lead si califica
    if score in LEAD_SCORE_THRESHOLD:
        lead_id = save_lead(
            conversation_id=conversation["id"],
            phone_number=phone_number,
            agent=agent_name,
            client_name=info.get("client_name"),
            product=info.get("product", "no especificado"),
            modality=info.get("modality"),
            locality=info.get("locality"),
            lead_score=score,
            summary=info.get("summary", "")
        )
        # Notificamos solo si no fue notificado antes
        from database import get_lead_notified_status
        if lead_id and not get_lead_notified_status(lead_id):
            await notify_qualified_lead(
                agent=agent_name,
                client_name=info.get("client_name"),
                locality=info.get("locality"),
                product=info.get("product", "no especificado"),
                modality=info.get("modality"),
                lead_score=score,
                summary=info.get("summary", ""),
                phone_number=phone_number
            )
            mark_lead_notified(lead_id)


async def process_incoming_message(phone_number: str, message_text: str, message_type: str = "text"):
    """Procesa un mensaje entrante y genera respuesta."""
    # Obtenemos o creamos conversación
    conversation = get_or_create_conversation(phone_number)
    conv_id = conversation["id"]

    # Guardamos el mensaje del usuario
    save_message(conv_id, "user", message_text, message_type)

    # Obtenemos historial
    history = get_conversation_messages(conv_id)
    # Excluimos el último mensaje del historial (ya lo tenemos como new_message)
    history_for_agent = history[:-1]

    # Determinamos el agente
    current_agent = conversation.get("agent")
    agent_name = get_agent_for_conversation(history_for_agent, message_text, current_agent)

    # Si cambió el agente, lo actualizamos
    if agent_name != current_agent:
        update_conversation(conv_id, agent=agent_name)
        conversation["agent"] = agent_name

    # Generamos respuesta
    if agent_name == "router":
        response = get_router_response(history_for_agent, message_text)
    else:
        response = await get_agent_response(agent_name, history_for_agent, message_text)

    # Guardamos la respuesta
    save_message(conv_id, "assistant", response, "text")

    # Análisis de lead en background (no bloquea la respuesta)
    asyncio.create_task(
        check_and_notify_lead(conversation, get_conversation_messages(conv_id), phone_number)
    )

    return response


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """Verificación del webhook de Meta."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook")
@limiter.limit("60/minute")
async def receive_message(request: Request):
    """Recibe mensajes de WhatsApp."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Verificamos que sea un mensaje de WhatsApp
    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "no_messages"}

        message = value["messages"][0]
        phone_number = message["from"]
        message_type = message["type"]

        message_text = None

        if message_type == "text":
            message_text = message["text"]["body"]

        elif message_type == "audio":
            media_id = message["audio"]["id"]
            mime_type = message["audio"].get("mime_type", "audio/ogg")
            # Transcribimos el audio con Gemini
            message_text = await process_whatsapp_audio(media_id, mime_type)

        elif message_type in ["image", "video", "document"]:
            message_text = f"[El cliente envió un archivo de tipo {message_type}]"

        elif message_type == "location":
            lat = message["location"]["latitude"]
            lon = message["location"]["longitude"]
            message_text = f"[El cliente compartió su ubicación: {lat}, {lon}]"

        else:
            message_text = f"[Mensaje de tipo {message_type} recibido]"

        if message_text:
            # Procesamos el mensaje y obtenemos respuesta
            response_text = await process_incoming_message(phone_number, message_text, message_type)

            # Enviamos la respuesta por WhatsApp
            await send_whatsapp_message(phone_number, response_text)

        return {"status": "ok"}

    except (KeyError, IndexError) as e:
        # Estructura de mensaje inesperada — no es un error fatal
        return {"status": "ignored", "reason": str(e)}
    except Exception as e:
        log.error("Error procesando mensaje: %s", e)
        return {"status": "error"}
