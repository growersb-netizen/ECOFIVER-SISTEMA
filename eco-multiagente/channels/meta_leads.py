"""
Canal Meta — EcoFiver IA
Maneja dos flujos de captación automática:

1. Meta Lead Ads — cuando alguien completa un formulario en una campaña
   de Facebook o Instagram, Meta envía el lead_id a este webhook.
   El sistema lo captura, lo registra en el CRM y contacta al lead
   por WhatsApp en menos de 5 minutos.

2. Instagram DM — mensajes directos de Instagram Business se reciben
   por el mismo webhook de Meta (mismo número de App). Se procesan
   como si fueran WhatsApp (mismo agente Valentina, mismo CRM).

Requiere env vars:
  META_PAGE_ACCESS_TOKEN  — token de página con permisos leads_retrieval + instagram_manage_messages
  META_APP_SECRET         — para verificar firma X-Hub-Signature-256
  WA_VERIFY_TOKEN         — compartido con whatsapp.py (eco_modules_verify_2026)
"""

import os
import hmac
import hashlib
import logging
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

logger   = logging.getLogger(__name__)
router   = APIRouter()

META_PAGE_TOKEN  = os.getenv("META_PAGE_ACCESS_TOKEN", "")
META_APP_SECRET  = os.getenv("META_APP_SECRET", "")
WA_VERIFY_TOKEN  = os.getenv("WA_VERIFY_TOKEN", "eco_modules_verify_2026")
META_API_BASE    = "https://graph.facebook.com/v19.0"

# Productos de interés inferidos del nombre del formulario o campaña
_PRODUCTO_KEYWORDS = {
    "piscina":  ["piscina", "pileta", "pool", "fibra"],
    "modulo":   ["modulo", "módulo", "vivienda", "casa", "nce", "prefab"],
    "combo":    ["combo", "pack", "piscina y modulo", "modulo y piscina"],
}


def _inferir_producto(texto: str) -> str:
    texto = texto.lower()
    for prod, kw in _PRODUCTO_KEYWORDS.items():
        if any(k in texto for k in kw):
            return prod
    return "general"


def _verificar_firma(body_bytes: bytes, signature_header: str) -> bool:
    """Verifica X-Hub-Signature-256 de Meta para confirmar que el webhook es legítimo."""
    if not META_APP_SECRET:
        return True  # En desarrollo sin secret, aceptar todo
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _obtener_datos_lead(leadgen_id: str) -> dict:
    """
    Llama a Meta Graph API para obtener los datos del formulario completo.
    Retorna dict con nombre, telefono, email, etc.
    """
    if not META_PAGE_TOKEN:
        logger.warning("[META] META_PAGE_ACCESS_TOKEN no configurado")
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{META_API_BASE}/{leadgen_id}",
                params={
                    "fields":       "field_data,created_time,ad_id,ad_name,form_id",
                    "access_token": META_PAGE_TOKEN,
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.error(f"[META] Error obteniendo lead {leadgen_id}: {e}")
        return {}

    resultado = {"meta_lead_id": leadgen_id}
    campo_map = {
        "full_name":    "nombre",
        "first_name":   "nombre",
        "last_name":    "apellido",
        "phone_number": "telefono",
        "phone":        "telefono",
        "email":        "email",
        "city":         "ciudad",
        "zip_code":     "cp",
    }
    for campo in data.get("field_data", []):
        key   = campo.get("name", "").lower()
        valor = campo.get("values", [""])[0]
        mapped = campo_map.get(key)
        if mapped:
            resultado[mapped] = valor
        else:
            resultado[key] = valor

    resultado["ad_name"]  = data.get("ad_name", "")
    resultado["forma_id"] = data.get("form_id", "")
    resultado["producto_interes"] = _inferir_producto(
        data.get("ad_name", "") + " " + resultado.get("ciudad", "")
    )
    return resultado


async def _contactar_lead_wa(lead: dict) -> None:
    """
    Crea el lead en CRM y le envía el primer mensaje de Valentina por WhatsApp
    dentro de los 5 minutos de haber completado el formulario.
    """
    from tools import crm_client
    from channels.whatsapp import send_whatsapp_message
    from orchestrator.router import route_message

    telefono = lead.get("telefono", "").strip()
    nombre   = lead.get("nombre", "")
    producto = lead.get("producto_interes", "general")

    if not telefono:
        logger.warning(f"[META] Lead {lead.get('meta_lead_id')} sin teléfono — sin contacto WA")
        return

    # Normalizar teléfono argentino al formato Meta (549XXXXXXXXXX)
    telefono = telefono.replace("+", "").replace(" ", "").replace("-", "")
    if telefono.startswith("0"):
        telefono = "549" + telefono[1:]
    elif telefono.startswith("15") and len(telefono) == 10:
        telefono = "549" + telefono
    elif not telefono.startswith("549") and len(telefono) == 10:
        telefono = "549" + telefono

    # Registrar en CRM
    lead_crm = await crm_client.registrar_lead_meta({
        **lead,
        "telefono":     telefono,
        "canal_origen": "meta_ads",
        "session_id":   telefono,
    })
    logger.info(f"[META] Lead registrado en CRM: {lead_crm.get('id', '?')} — {nombre} ({telefono})")

    # Primer mensaje: Valentina toma el hilo con contexto del formulario
    contexto = (
        f"LEAD ENTRANTE DESDE META ADS.\n"
        f"Nombre: {nombre}\n"
        f"Producto de interés: {producto}\n"
        f"Ciudad: {lead.get('ciudad', 'no indicada')}\n"
        f"Email: {lead.get('email', 'no indicado')}\n"
        f"Anuncio: {lead.get('ad_name', 'desconocido')}\n\n"
        f"El lead acaba de completar un formulario en Meta Ads. "
        f"Contactalo de forma cálida y natural como si fuera un cliente que llegó por WhatsApp. "
        f"Ya sabés que se interesó en {producto}. No menciones que fue por un formulario."
    )
    result = await route_message(
        canal="whatsapp",
        session_id=telefono,
        mensaje=f"Hola, completé un formulario sobre {producto}",
        msg_type="text",
    )
    # Inyectamos el contexto real en la primera respuesta que Valentina genera
    from agents.valentina import get_agent as get_valentina
    valentina = get_valentina()
    primer_msg = await valentina.respond(
        f"Hola {nombre}, vi que te interesaste en nuestros productos. ¿Puedo ayudarte?",
        contexto,
    )
    # Limpiar derivaciones internas
    import re
    primer_msg = re.sub(r"\[DERIVAR:\w+\]", "", primer_msg).strip()

    await send_whatsapp_message(telefono, primer_msg)
    logger.info(f"[META] Primer contacto enviado a {telefono} ({nombre})")


# ── WEBHOOK VERIFICACIÓN (GET) ──────────────────────────────────────────────

@router.get("/webhook/meta")
async def meta_verify(request: Request):
    """Verificación del webhook — compartida con Lead Ads e Instagram."""
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        logger.info("[META] Webhook Meta verificado.")
        return PlainTextResponse(content=challenge)

    logger.warning("[META] Verificación fallida.")
    raise HTTPException(status_code=403, detail="Token inválido")


# ── WEBHOOK RECEPCIÓN (POST) ────────────────────────────────────────────────

@router.post("/webhook/meta")
async def meta_webhook(request: Request):
    """
    Recibe eventos de Meta:
    - Lead Ads: nuevos leads de formularios
    - Instagram DM: mensajes directos de Instagram Business
    """
    body_bytes = await request.body()

    # Verificar firma si tenemos APP_SECRET
    sig = request.headers.get("X-Hub-Signature-256", "")
    if META_APP_SECRET and not _verificar_firma(body_bytes, sig):
        logger.warning("[META] Firma inválida en webhook")
        raise HTTPException(status_code=403, detail="Firma inválida")

    try:
        import json
        body = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    import asyncio
    obj_type = body.get("object", "")

    # ── Facebook Page: Lead Ads + Messenger DMs ──────────────────────────────
    if obj_type == "page":
        for entry in body.get("entry", []):
            # Lead Ads
            for change in entry.get("changes", []):
                if change.get("field") == "leadgen":
                    leadgen_id = change["value"].get("leadgen_id", "")
                    if leadgen_id:
                        logger.info(f"[META] Nuevo lead ads: {leadgen_id}")
                        asyncio.create_task(_procesar_lead_ads(leadgen_id))
            # Messenger DMs
            for msg_event in entry.get("messaging", []):
                if "message" in msg_event and not msg_event["message"].get("is_echo"):
                    asyncio.create_task(_procesar_messenger_dm(msg_event))

    # ── Instagram: DMs + Comentarios ────────────────────────────────────────
    elif obj_type == "instagram":
        for entry in body.get("entry", []):
            # Mensajes directos
            for msg_event in entry.get("messaging", []):
                if "message" in msg_event and not msg_event["message"].get("is_echo"):
                    asyncio.create_task(_procesar_instagram_dm(msg_event))
            # Comentarios en posts propios
            for change in entry.get("changes", []):
                if change.get("field") == "comments":
                    asyncio.create_task(_procesar_comentario_ig(change.get("value", {})))

    return {"status": "ok"}


async def _procesar_lead_ads(leadgen_id: str) -> None:
    """Obtiene datos del lead y lo contacta por WhatsApp en background."""
    try:
        lead = await _obtener_datos_lead(leadgen_id)
        if lead:
            await _contactar_lead_wa(lead)
        else:
            logger.warning(f"[META] No se obtuvieron datos del lead {leadgen_id}")
    except Exception as e:
        logger.error(f"[META] Error procesando lead {leadgen_id}: {e}")


async def _procesar_instagram_dm(msg_event: dict) -> None:
    """
    Procesa un DM de Instagram. Lo enruta como canal 'instagram'
    al mismo pipeline de agentes (Valentina atiende).
    """
    try:
        from orchestrator.router import route_message
        from tools import crm_client

        sender_id = msg_event.get("sender", {}).get("id", "")
        texto     = msg_event.get("message", {}).get("text", "")
        attach    = msg_event.get("message", {}).get("attachments", [])

        if not sender_id:
            return

        # Si no hay texto pero hay attachment, informar
        if not texto and attach:
            texto = "[El cliente envió un archivo o imagen desde Instagram]"

        if not texto:
            return

        # Crear/actualizar lead en CRM con canal instagram
        lead = await crm_client.get_lead(f"ig_{sender_id}")
        if not lead:
            await crm_client.create_lead({
                "session_id":    f"ig_{sender_id}",
                "canal_origen":  "instagram",
                "agente_asignado": "valentina",
                "estado":        "nuevo",
            })

        result = await route_message(
            canal="instagram",
            session_id=f"ig_{sender_id}",
            mensaje=texto,
            msg_type="text",
        )

        # Enviar respuesta por Instagram DM via Meta Graph API
        await _enviar_instagram_dm(sender_id, result["reply"])

    except Exception as e:
        logger.error(f"[META] Error procesando Instagram DM: {e}")


async def _enviar_instagram_dm(recipient_id: str, texto: str) -> bool:
    """Envía un mensaje directo por Instagram Business."""
    if not META_PAGE_TOKEN:
        logger.warning("[META] META_PAGE_ACCESS_TOKEN no configurado para Instagram DM")
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{META_API_BASE}/me/messages",
                params={"access_token": META_PAGE_TOKEN},
                json={
                    "recipient": {"id": recipient_id},
                    "message":   {"text": texto[:2000]},
                    "messaging_type": "RESPONSE",
                },
            )
            if r.status_code != 200:
                logger.error(f"[META] Error Instagram DM {r.status_code}: {r.text[:200]}")
                return False
            return True
    except Exception as e:
        logger.error(f"[META] Error enviando Instagram DM a {recipient_id}: {e}")
        return False


async def _procesar_comentario_ig(value: dict) -> None:
    """
    Procesa un comentario en un post de Instagram.
    Si el comentario expresa interés en productos → responde en el comentario
    e invita al usuario a enviar un DM.
    """
    try:
        from agents.valentina import get_agent

        texto      = value.get("text", "")
        sender_id  = value.get("from", {}).get("id", "")
        sender_ig  = value.get("from", {}).get("username", "")
        media_id   = value.get("media_id", "")
        comment_id = value.get("id", "")

        if not texto or not comment_id:
            return

        # Solo responder si el comentario es una pregunta o expresa interés
        palabras_interes = [
            "precio", "cuánto", "cuanto", "costo", "valor", "info",
            "información", "consulta", "financiación", "financiacion",
            "cuotas", "contado", "instalan", "instalación", "donde",
            "dónde", "disponible", "disponibilidad", "quiero", "me interesa",
            "interesado", "interesada", "cómo", "como funciona",
        ]
        texto_lower = texto.lower()
        es_consulta = any(p in texto_lower for p in palabras_interes) or "?" in texto

        if not es_consulta:
            return

        # Generar respuesta corta para comentario público (invita al DM)
        valentina = get_agent()
        nombre = f"@{sender_ig}" if sender_ig else "Hola"
        respuesta = await valentina.respond(
            f"Respuesta corta (máx 2 oraciones) para comentario de Instagram. "
            f"El usuario {nombre} preguntó: '{texto}'. "
            "Contestá amablemente, decí que con gusto le mandás info por privado, "
            "invitalo a enviar un DM o WhatsApp. NO des precios ni detalles acá. "
            "Sin hashtags ni emojis exagerados. Firmá como EcoFiver.",
        )
        # Limpiar señales internas
        import re
        respuesta = re.sub(r"\[DERIVAR:\w+\]|\[AGENDA_VV:[^\]]+\]|\[LLAMADA_SUP:[^\]]+\]", "", respuesta).strip()

        # Publicar respuesta en el comentario
        if respuesta and META_PAGE_TOKEN:
            from tools.content_poster import responder_comentario_ig
            await responder_comentario_ig(media_id, comment_id, respuesta)
            logger.info(f"[META] Respondido comentario IG de {sender_ig}: {texto[:50]}")

        # Crear lead en CRM si hay sender_id (para tracking)
        if sender_id:
            from tools import crm_client
            session = f"ig_{sender_id}"
            lead = await crm_client.get_lead(session)
            if not lead:
                await crm_client.create_lead({
                    "session_id":      session,
                    "canal_origen":    "instagram_comentario",
                    "agente_asignado": "valentina",
                    "estado":          "nuevo",
                    "nombre":          sender_ig or "",
                    "notas":           f"Comentó en post IG: '{texto[:100]}'",
                })

    except Exception as e:
        logger.error(f"[META] Error procesando comentario IG: {e}")


async def _procesar_messenger_dm(msg_event: dict) -> None:
    """
    Procesa un mensaje directo recibido por Facebook Messenger.
    Ruta al mismo pipeline de Valentina que WhatsApp/Instagram.
    """
    try:
        from orchestrator.router import route_message
        from tools import crm_client

        sender_id = msg_event.get("sender", {}).get("id", "")
        texto     = msg_event.get("message", {}).get("text", "")
        attach    = msg_event.get("message", {}).get("attachments", [])

        if not sender_id:
            return

        if not texto and attach:
            texto = "[El cliente envió un archivo o imagen por Messenger]"
        if not texto:
            return

        # Crear lead en CRM con canal messenger
        session = f"msn_{sender_id}"
        lead = await crm_client.get_lead(session)
        if not lead:
            await crm_client.create_lead({
                "session_id":      session,
                "canal_origen":    "messenger",
                "agente_asignado": "valentina",
                "estado":          "nuevo",
            })

        result = await route_message(
            canal="messenger",
            session_id=session,
            mensaje=texto,
            msg_type="text",
        )

        # Responder por Messenger via Graph API
        await _enviar_messenger_reply(sender_id, result["reply"])

    except Exception as e:
        logger.error(f"[META] Error procesando Messenger DM: {e}")


async def _enviar_messenger_reply(recipient_id: str, texto: str) -> bool:
    """Envía un mensaje por Facebook Messenger."""
    if not META_PAGE_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{META_API_BASE}/me/messages",
                params={"access_token": META_PAGE_TOKEN},
                json={
                    "recipient":      {"id": recipient_id},
                    "message":        {"text": texto[:2000]},
                    "messaging_type": "RESPONSE",
                },
            )
            if r.status_code != 200:
                logger.error(f"[META] Error Messenger {r.status_code}: {r.text[:200]}")
                return False
            return True
    except Exception as e:
        logger.error(f"[META] Error enviando Messenger a {recipient_id}: {e}")
        return False
