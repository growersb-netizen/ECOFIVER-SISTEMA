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

# Estructuras de componentes a probar en orden.  Meta devuelve (#100) Invalid parameter
# cuando la estructura enviada no coincide con los componentes registrados en la plantilla.
# Las plantillas AUTHENTICATION pueden tener: sin botón, botón COPY_CODE, o botón URL.
_OTP_COMPONENT_CANDIDATES = [
    # 1. Solo body — cubre plantillas sin botón dinámico o con botón estático
    [{"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]}],
    # 2. Body + COPY_CODE — estructura estándar de plantillas AUTHENTICATION con botón
    [
        {"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]},
        {"type": "button", "sub_type": "copy_code", "index": "0",
         "parameters": [{"type": "coupon_code", "coupon_code": "{codigo}"}]},
    ],
    # 3. Body + URL button — plantillas con botón de URL variable (estructura original)
    [
        {"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]},
        {"type": "button", "sub_type": "url", "index": "0",
         "parameters": [{"type": "text", "text": "{codigo}"}]},
    ],
]


def _build_otp_components(template: list, codigo: str) -> list:
    """Reemplaza el placeholder {codigo} por el código real en la estructura de componentes."""
    import json
    return json.loads(json.dumps(template).replace('"{codigo}"', json.dumps(codigo)))


def send_whatsapp_otp(db: Session, to: str, codigo: str) -> bool:
    """
    Envía OTP por WhatsApp.  Prueba todas las estructuras de componentes conocidas
    de la plantilla de autenticación antes de caer a texto libre.
    """
    token, phone_id = _get_wa_creds(db)
    if not token or not phone_id:
        log.warning("[WA] Credenciales no configuradas — omitiendo OTP")
        return False

    numero = to.replace("+", "").replace(" ", "").replace("-", "")

    labels = ["body-only", "copy_code", "url-button"]
    for idx, candidate in enumerate(_OTP_COMPONENT_CANDIDATES):
        label = labels[idx]
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
                        "components": _build_otp_components(candidate, codigo),
                    },
                },
                timeout=10,
            )
            if resp.status_code == 200:
                log.info(f"[WA] OTP (template/{label}) enviado a {numero}")
                return True
            log.warning(f"[WA] Template OTP [{label}] falló {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            log.error(f"[WA] Excepción template OTP [{label}]: {e}")

    # ── Fallback: texto libre (funciona dentro de la ventana de 24 h) ────────
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
