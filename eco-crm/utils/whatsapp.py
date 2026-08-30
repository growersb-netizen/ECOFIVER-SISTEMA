"""
Utilidad para enviar mensajes via WhatsApp Cloud API.
Usa wa_token y wa_phone_id de ConfiguracionSistema.
"""
import logging
import os
import httpx
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

WA_API_URL = "https://graph.facebook.com/v19.0"


def _get_wa_creds(db: Session):
    """Devuelve (token, phone_id) desde la configuración. Retorna (None, None) si no están."""
    from database.models import ConfiguracionSistema
    from database.encryption import decrypt_value
    token_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "wa_token"
    ).first()
    phone_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "wa_phone_id"
    ).first()
    # wa_token se guarda encriptado (es_secreto=True) — hay que desencriptarlo antes
    # de usarlo. Antes se mandaba el valor cifrado tal cual como Bearer token, lo
    # que siempre daba 401 "Authentication Error" sin importar qué tan válido
    # fuera el token real detrás.
    token = decrypt_value(token_cfg.valor) if token_cfg and token_cfg.valor else None
    phone_id = phone_cfg.valor if phone_cfg and phone_cfg.valor else None
    return token, phone_id


def send_whatsapp_text(db: Session, to: str, mensaje: str) -> bool:
    """
    Envía un mensaje de texto simple via WhatsApp Cloud API.
    `to` debe ser el número sin + (ej: 5491135164644).
    Retorna True si fue exitoso, False si falló.
    """
    token, phone_id = _get_wa_creds(db)
    if not token or not phone_id:
        log.warning("[WA] Credenciales no configuradas — omitiendo envío")
        return False

    # Normalizar número: sacar +, espacios y guiones
    numero = to.replace("+", "").replace(" ", "").replace("-", "")

    try:
        resp = httpx.post(
            f"{WA_API_URL}/{phone_id}/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "text",
                "text": {"body": mensaje},
            },
            timeout=10,
        )
        if resp.status_code == 200:
            log.info(f"[WA] Mensaje enviado a {numero}")
            return True
        else:
            log.warning(f"[WA] Error {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log.error(f"[WA] Excepción al enviar: {e}")
        return False


OTP_TEMPLATE_NAME = "ecofiver_codigo_verificacion"
OTP_TEMPLATE_LANG = "es_AR"


def send_whatsapp_otp(db: Session, to: str, codigo: str) -> bool:
    """
    Envía un código de verificación usando la plantilla de autenticación
    aprobada por Meta ('ecofiver_codigo_verificacion'). Es OBLIGATORIO usar
    una plantilla (no texto libre) para el primer mensaje a un número —
    WhatsApp rechaza texto libre fuera de la ventana de 24hs de conversación
    con el error 131047 "Re-engagement message", que es exactamente el caso
    de un socio nuevo que nunca escribió antes. Retorna True si Meta aceptó
    el envío (no garantiza entrega — eso llega después por webhook de status).
    """
    token, phone_id = _get_wa_creds(db)
    if not token or not phone_id:
        log.warning("[WA] Credenciales no configuradas — omitiendo envío")
        return False

    numero = to.replace("+", "").replace(" ", "").replace("-", "")

    try:
        resp = httpx.post(
            f"{WA_API_URL}/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "template",
                "template": {
                    "name": OTP_TEMPLATE_NAME,
                    "language": {"code": OTP_TEMPLATE_LANG},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": codigo}]},
                        {"type": "button", "sub_type": "url", "index": "0",
                         "parameters": [{"type": "text", "text": codigo}]},
                    ],
                },
            },
            timeout=10,
        )
        if resp.status_code == 200:
            log.info(f"[WA] OTP enviado a {numero}")
            return True
        log.warning(f"[WA] Error OTP {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as e:
        log.error(f"[WA] Excepción al enviar OTP: {e}")
        return False


def notificar_asesor_nuevo_lead(db: Session, asesor_telefono: str, lead_nombre: str,
                                 producto: str, localidad: str, forma_pago: str, lead_id: int):
    """Notifica al asesor que le llegó un nuevo lead."""
    APP_URL = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app")
    msg = (
        f"📋 *Nuevo lead asignado*\n"
        f"👤 Cliente: {lead_nombre}\n"
        f"🏠 Producto: {producto}\n"
        f"📍 Localidad: {localidad}\n"
        f"💳 Forma de pago: {forma_pago}\n"
        f"🔗 Ver en CRM: {APP_URL}/leads"
    )
    return send_whatsapp_text(db, asesor_telefono, msg)


def notificar_rodrigo(db: Session, mensaje: str) -> bool:
    """Envía notificación a Rodrigo (número hardcodeado en config o fallback)."""
    from database.models import ConfiguracionSistema
    dest_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "notif_wa_destino"
    ).first()
    numero = dest_cfg.valor if dest_cfg and dest_cfg.valor else "5491135164644"
    return send_whatsapp_text(db, numero, mensaje)
