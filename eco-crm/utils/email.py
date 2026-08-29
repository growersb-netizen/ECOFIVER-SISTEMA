"""
Utilidad para enviar mails vía SMTP (ej: Gmail con contraseña de aplicación).
Usa smtp_host / smtp_port / smtp_user / smtp_password / smtp_from de
ConfiguracionSistema — mismo patrón que utils/whatsapp.py.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _get_smtp_creds(db: Session):
    from database.models import ConfiguracionSistema

    def _valor(clave, default=""):
        row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        return row.valor if row and row.valor else default

    host = _valor("smtp_host", "smtp.gmail.com")
    port = _valor("smtp_port", "587")
    user = _valor("smtp_user")
    password = _valor("smtp_password")
    remitente = _valor("smtp_from") or user
    return host, port, user, password, remitente


def send_email_text(db: Session, to: str, subject: str, body: str) -> bool:
    """
    Envía un mail de texto plano simple. Retorna True si fue exitoso,
    False si falló (nunca lanza excepción — igual que send_whatsapp_text).
    """
    host, port, user, password, remitente = _get_smtp_creds(db)
    if not user or not password:
        log.warning("[EMAIL] Credenciales SMTP no configuradas — omitiendo envío")
        return False
    if not to:
        return False

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = f"EcoFiver <{remitente}>"
        msg["To"] = to

        with smtplib.SMTP(host, int(port), timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(remitente, [to], msg.as_string())

        log.info(f"[EMAIL] Mensaje enviado a {to}")
        return True
    except Exception as e:
        log.error(f"[EMAIL] Excepción al enviar a {to}: {e}")
        return False
