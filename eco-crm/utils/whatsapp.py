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
    """Devuelve (token, phone_id). DB es la fuente primaria; env vars son el fallback."""
    import os
    from database.models import ConfiguracionSistema
    from database.encryption import decrypt_value
    token_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "wa_token"
    ).first()
    phone_cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "wa_phone_id"
    ).first()
    # wa_token se guarda encriptado (es_secreto=True) — hay que desencriptarlo.
    token = decrypt_value(token_cfg.valor) if token_cfg and token_cfg.valor else None
    phone_id = phone_cfg.valor if phone_cfg and phone_cfg.valor else None
    # Fallback: si la DB no tiene las credenciales (primer arranque antes del sync,
    # o ENCRYPTION_KEY girado sin restartar), usar directamente las env vars.
    if not token:
        token = os.getenv("WA_TOKEN") or None
    if not phone_id:
        phone_id = os.getenv("WA_PHONE_ID") or None
    return token, phone_id


def send_whatsapp_text(db: Session, to: str, mensaje: str) -> bool:
    """
    Envía un mensaje de texto simple via WhatsApp Cloud API.
    `to` debe ser el número sin + (ej: 5491135164644).
    Retorna True si fue exitoso, False si falló.
    """
    try:
        token, phone_id = _get_wa_creds(db)
        if not token or not phone_id:
            log.warning("[WA] Credenciales no configuradas — omitiendo envío")
            return False

        # Normalizar número: sacar +, espacios y guiones
        numero = to.replace("+", "").replace(" ", "").replace("-", "")

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
OTP_TEMPLATE_LANG = "es"   # Meta usa "es", no "es_AR"


def send_whatsapp_otp(db: Session, to: str, codigo: str) -> bool:
    """
    Envía OTP por WhatsApp.  Intenta primero con la plantilla aprobada por Meta;
    si la plantilla falla (no existe, no aprobada, ventana de 24h cerrada, etc.)
    cae a texto libre.  Retorna True si alguno de los dos métodos funcionó.
    """
    token, phone_id = _get_wa_creds(db)
    if not token or not phone_id:
        log.warning("[WA] Credenciales no configuradas — omitiendo OTP")
        return False

    numero = to.replace("+", "").replace(" ", "").replace("-", "")

    # ── Intento 1: plantilla de autenticación ────────────────────────────────
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
            log.info(f"[WA] OTP (template) enviado a {numero}")
            return True
        log.warning(
            f"[WA] Template OTP falló {resp.status_code}: {resp.text[:400]} "
            "— cayendo a texto libre"
        )
    except Exception as e:
        log.error(f"[WA] Excepción template OTP: {e} — cayendo a texto libre")

    # ── Intento 2: texto libre (funciona dentro de la ventana de 24 h) ───────
    mensaje = (
        f"🔐 *Tu código de verificación EcoFiver es: {codigo}*\n\n"
        f"Ingresalo en el panel para verificar tu WhatsApp.\n"
        f"Vence en 10 minutos. No lo compartas con nadie."
    )
    ok = send_whatsapp_text(db, to, mensaje)
    if ok:
        log.info(f"[WA] OTP (texto libre) enviado a {numero}")
    else:
        log.error(f"[WA] No se pudo enviar OTP a {numero} por ningún método")
    return ok


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
