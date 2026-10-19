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
OTP_TEMPLATE_LANG = "es_AR"  # Confirmado: la plantilla está registrada en es_AR (no "es")

# Estructuras de componentes a probar en orden.  URL button va primero porque es
# la estructura confirmada para ecofiver_codigo_verificacion (es_AR).
_OTP_COMPONENT_CANDIDATES = [
    # 1. Body + URL button — confirmado con test en producción
    [
        {"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]},
        {"type": "button", "sub_type": "url", "index": "0",
         "parameters": [{"type": "text", "text": "{codigo}"}]},
    ],
    # 2. Solo body — fallback para plantillas sin botón dinámico
    [{"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]}],
    # 3. Body + COPY_CODE — fallback para plantillas AUTHENTICATION con botón COPY_CODE
    [
        {"type": "body", "parameters": [{"type": "text", "text": "{codigo}"}]},
        {"type": "button", "sub_type": "copy_code", "index": "0",
         "parameters": [{"type": "coupon_code", "coupon_code": "{codigo}"}]},
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

    labels = ["url-button", "body-only", "copy_code"]
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

    # ── Fallback: texto libre ────────────────────────────────────────────────
    # NOTA: Solo funciona si el destinatario inició conversación con el número
    # en las últimas 24h.  Los socios que nunca mandaron un mensaje NO lo recibirán.
    # Si llegamos acá, la plantilla está mal configurada en Meta — revisar estructura.
    log.error(
        "[WA] Todos los intentos de plantilla fallaron para OTP a %s. "
        "Intentando texto libre (solo funcionará si hay ventana de 24h abierta).",
        numero,
    )
    mensaje = (
        f"🔐 *Tu código de verificación EcoFiver es: {codigo}*\n\n"
        f"Ingresalo en el panel para verificar tu WhatsApp.\n"
        f"Vence en 10 minutos. No lo compartas con nadie."
    )
    ok = send_whatsapp_text(db, to, mensaje)
    if ok:
        log.info(f"[WA] OTP (texto libre) enviado a {numero}")
    else:
        log.error(
            "[WA] OTP no entregado a %s. La plantilla '%s' falló con todas las "
            "estructuras conocidas — verificar en Meta BM que esté APROBADA y revisar "
            "sus componentes con GET /api/admin/wa/plantillas?destino=%s",
            numero, OTP_TEMPLATE_NAME, numero,
        )
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
