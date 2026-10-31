"""
Línea de WhatsApp de Franco (aliados): resolución del emisor.

Antes se pasaba FRANCO_WHATSAPP_NUMBER como phone_id de la Graph API y, en
send_to_aliados_wa, también como destinatario: un mismo valor no puede ser a la
vez el ID del número emisor (Meta) y el teléfono destino, así que esos envíos
fallaban siempre o se mandaban a sí mismos.

  FRANCO_WA_PHONE_ID      ID del número emisor en Meta (recomendado).
  FRANCO_WHATSAPP_NUMBER  compatibilidad: si ya contiene un ID de Meta (15+
                          dígitos, no argentino) se usa como emisor; si es un
                          teléfono, es el destinatario de send_to_aliados_wa.
Sin emisor válido no se hace la llamada (antes fallaba en Meta) y queda un error.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)


def _digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _parece_phone_id(d: str) -> bool:
    return len(d) >= 15 and not d.startswith("54")


def phone_id_franco() -> str | None:
    pid = _digitos(os.getenv("FRANCO_WA_PHONE_ID", ""))
    if pid:
        return pid
    legado = _digitos(os.getenv("FRANCO_WHATSAPP_NUMBER", ""))
    return legado if _parece_phone_id(legado) else None


def destino_aliados() -> str | None:
    """Teléfono destino del aviso 'al canal de aliados' (Cloud API no envía a grupos)."""
    d = _digitos(os.getenv("FRANCO_WHATSAPP_NUMBER", ""))
    if not d or _parece_phone_id(d) or d == phone_id_franco():
        return None
    return d


async def enviar_franco(telefono: str, texto: str) -> bool:
    pid = phone_id_franco()
    if not pid:
        logger.error("[Franco/WA] Sin FRANCO_WA_PHONE_ID (ID del número emisor en Meta): mensaje no enviado")
        return False
    from channels.whatsapp import enviar_mensaje_wa
    return await enviar_mensaje_wa(telefono, texto, phone_id=pid)
