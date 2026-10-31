"""
Plantillas de WhatsApp aprobadas por Meta, para mensajes fuera de la ventana de 24 h.

Los nombres y textos deben coincidir EXACTAMENTE con los cargados en WhatsApp Manager
(docs/ai-company/PLAN_COWORK_PLANTILLAS_WA.md). El CRM decide si se puede usar una
plantilla (baja, deduplicación, activación por el propietario y tope diario).
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)
IDIOMA = "es_AR"

# clave → (nombre en Meta, texto con {{n}} para registrar en el inbox)
PLANTILLAS = {
    "primer_contacto": ("ecofiver_primer_contacto",
                        "Hola {{1}}, soy Valentina de EcoFiver. Recibimos tu consulta por {{2}}. "
                        "¿Querés que te pase precios y opciones? Respondé este mensaje y te asesoro."),
    "seguimiento": ("ecofiver_seguimiento",
                    "Hola {{1}}, ¿pudiste ver la información sobre {{2}}? Si tenés dudas sobre modelos, precios "
                    "o financiación, respondé este mensaje y lo vemos juntos."),
    "reactivacion": ("ecofiver_reactivacion",
                     "Hola {{1}}, hace un tiempo nos consultaste por {{2}}. Tenemos novedades de temporada. "
                     "¿Querés que te cuente? Respondé este mensaje y te paso la información actualizada."),
    "recordatorio_videollamada": ("ecofiver_recordatorio_videollamada",
                                  "Hola {{1}}, te recordamos tu videollamada con EcoFiver hoy a las {{2}}. "
                                  "¿Confirmás que vas a poder estar? Respondé este mensaje para confirmar o reprogramar."),
    "recordatorio_cuota": ("ecofiver_recordatorio_cuota",
                           "Hola {{1}}, te recordamos que la cuota de {{2}} de tu plan EcoFiver está pendiente de pago. "
                           "Si ya la abonaste, ignorá este mensaje. Ante cualquier consulta, respondé este mensaje."),
}


def _param(v) -> str:
    """Meta rechaza parámetros con saltos de línea, tabs o 4+ espacios seguidos, y vacíos."""
    t = re.sub(r"\s+", " ", str(v or "")).strip()[:60]
    return t or "-"


def texto(clave: str, params: list) -> str:
    t = PLANTILLAS[clave][1]
    for i, p in enumerate(params, 1):
        t = t.replace("{{%d}}" % i, _param(p))
    return t


async def enviar(telefono: str, clave: str, params: list, remitente: str = "plantilla") -> bool:
    from channels.whatsapp import META_API_BASE, _crm_push_mensaje, _get_wa_phone_id, _get_wa_token
    nombre = PLANTILLAS[clave][0]
    token, pid = _get_wa_token(), _get_wa_phone_id()
    if not token or not pid:
        logger.warning("[WA-Plantilla] token o phone_id no configurados")
        return False
    payload = {"messaging_product": "whatsapp", "to": telefono, "type": "template",
               "template": {"name": nombre, "language": {"code": IDIOMA},
                            "components": [{"type": "body",
                                            "parameters": [{"type": "text", "text": _param(p)} for p in params]}]}}
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{META_API_BASE}/{pid}/messages", json=payload,
                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        if r.status_code != 200:
            logger.error(f"[WA-Plantilla] {nombre} HTTP {r.status_code}: {r.text[:300]}")
            return False
        wamid = (r.json().get("messages") or [{}])[0].get("id")
        await _crm_push_mensaje(phone=telefono, direccion="OUT", contenido=f"[Plantilla {nombre}] " + texto(clave, params),
                                remitente=remitente, wa_message_id=wamid, wa_linea=pid)
        logger.info(f"[WA-Plantilla] {nombre} → {telefono}")
        return True
    except Exception as e:
        logger.error(f"[WA-Plantilla] {nombre} error: {e}")
        return False
