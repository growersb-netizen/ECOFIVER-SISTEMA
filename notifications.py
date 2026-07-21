"""
Notificaciones por Telegram a Rodo + envío de respuestas por WhatsApp a clientes.
"""
import httpx
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

from config import (
    WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_API_URL,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)
from logger import get_logger

log = get_logger(__name__)


# ─── WhatsApp (solo para responder a clientes) ────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
async def _post_whatsapp(payload: dict, headers: dict) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()


async def send_whatsapp_message(to: str, text: str) -> bool:
    """Envía un mensaje de WhatsApp al cliente."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        log.info("[WA SIMULADO] Para %s:\n%s", to, text)
        return True

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        await _post_whatsapp(payload, headers)
        return True
    except Exception as e:
        log.error("Error enviando WhatsApp a %s: %s", to, e)
        return False


# ─── Telegram (notificaciones internas a Rodo) ───────────────────────────────

async def send_telegram(text: str) -> bool:
    """Envía un mensaje por Telegram al chat de Rodo."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.info("[TELEGRAM SIMULADO]:\n%s", text)
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
        return True
    except Exception as e:
        log.error("Error enviando Telegram: %s", e)
        return False


# ─── Notificaciones ───────────────────────────────────────────────────────────

async def notify_qualified_lead(
    agent: str,
    client_name: str,
    locality: str,
    product: str,
    modality: str,
    lead_score: str,
    summary: str,
    phone_number: str,
) -> bool:
    """Notifica a Rodo por Telegram cuando un lead califica."""
    hora = datetime.now().strftime("%H:%M")
    score_emoji = "🔥" if lead_score == "caliente" else "🌡️"
    agent_display = agent.capitalize() if agent else "Desconocido"

    message = (
        f"{score_emoji} <b>LEAD CALIFICADO</b>\n\n"
        f"👤 <b>Agente:</b> {agent_display}\n"
        f"📋 <b>Cliente:</b> {client_name or 'Sin nombre'}\n"
        f"📍 <b>Localidad:</b> {locality or 'No indicada'}\n"
        f"📦 <b>Producto:</b> {product or 'No especificado'}\n"
        f"💰 <b>Modalidad:</b> {modality.capitalize() if modality else 'No indicada'}\n"
        f"{score_emoji} <b>Score:</b> {lead_score.capitalize()}\n"
        f"💬 <b>Resumen:</b> {summary}\n"
        f"📱 <b>Número:</b> +{phone_number}\n"
        f"⏰ <b>Hora:</b> {hora}"
    )
    return await send_telegram(message)


async def send_daily_summary(stats: dict) -> bool:
    """Envía resumen diario a Rodo por Telegram a las 20:00hs."""
    agents = stats.get("agents", {})
    total = stats.get("total_conversations", 0)
    total_leads = stats.get("total_leads", 0)
    conversion = stats.get("conversion_rate", 0)

    def agent_line(name, display):
        a = agents.get(name, {})
        return f"• {display}: {a.get('conversations', 0)} conv / {a.get('leads', 0)} leads"

    message = (
        f"📊 <b>RESUMEN DEL DÍA — Eco Módulos &amp; Piscinas</b>\n\n"
        f"💬 Conversaciones totales: {total}\n"
        f"🎯 Leads calificados: {total_leads}\n"
        f"🔥 Leads calientes: {stats.get('hot_leads', 0)}\n\n"
        f"📊 <b>Por agente:</b>\n"
        f"{agent_line('pablo', 'Pablo')}\n"
        f"{agent_line('laura', 'Laura')}\n"
        f"{agent_line('sabrina', 'Sabrina')}\n"
        f"{agent_line('claudio', 'Claudio')}\n\n"
        f"📈 Tasa conversión: {conversion}%"
    )
    return await send_telegram(message)


async def send_welcome_test() -> bool:
    """Mensaje de prueba al iniciar el servidor."""
    message = "✅ <b>Sistema Eco Módulos &amp; Piscinas iniciado.</b>\nLos agentes están activos y escuchando."
    return await send_telegram(message)
