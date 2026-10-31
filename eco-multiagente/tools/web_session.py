"""
Sesiones del widget web firmadas por el servidor.

Antes el navegador inventaba su session_id y /chat/web lo aceptaba: quien
conociera (o adivinara) el id de otra persona leía y continuaba su conversación.
Ahora el servidor emite el id junto con una firma HMAC que solo él puede calcular;
/chat/web exige ambos. El "propietario" de la sesión es el navegador que recibió
la firma (la guarda en sessionStorage).

Secreto: WEB_SESSION_SECRET (recomendado, cualquier valor largo y aleatorio).
Si no está configurado se usa uno aleatorio por proceso: funciona, pero cada
reinicio invalida las sesiones abiertas (el widget pide una nueva sola).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid

logger = logging.getLogger(__name__)

_PREFIJO = b"eco-web-session:v1:"
_secreto_temporal = secrets.token_bytes(32)
_aviso_dado = False


def _secreto() -> bytes:
    global _aviso_dado
    s = os.getenv("WEB_SESSION_SECRET", "").strip()
    if s:
        return s.encode()
    if not _aviso_dado:
        logger.warning("[WebSession] WEB_SESSION_SECRET no configurado: secreto temporal por proceso "
                       "(las sesiones del widget se renuevan en cada reinicio)")
        _aviso_dado = True
    return _secreto_temporal


def _firma(session_id: str) -> str:
    return hmac.new(_secreto(), _PREFIJO + session_id.encode(), hashlib.sha256).hexdigest()


def nueva_sesion() -> dict:
    sid = str(uuid.uuid4())
    return {"session_id": sid, "session_token": _firma(sid)}


def sesion_valida(session_id: str | None, token: str | None) -> bool:
    if not session_id or not token or len(session_id) > 64 or len(token) > 128:
        return False
    try:
        uuid.UUID(session_id)
    except ValueError:
        return False
    return hmac.compare_digest(_firma(session_id), token)


def estado() -> dict:
    return {"secreto": "configurado" if os.getenv("WEB_SESSION_SECRET", "").strip() else "temporal_por_proceso"}
