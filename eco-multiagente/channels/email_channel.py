"""
Canal de email para Eco Módulos & Piscinas.
Recibe emails de clientes, los procesa con Valentina y responde automáticamente.

Configuración env vars:
  EMAIL_HOST     — servidor IMAP/SMTP (ej: imap.gmail.com o outlook.office365.com)
  EMAIL_USER     — dirección de email (ej: contacto@ecomodulosypiscinas.com.ar)
  EMAIL_PASSWORD — contraseña de app (Gmail: App Password de 16 caracteres)
  EMAIL_IMAP_PORT — puerto IMAP (default: 993)
  EMAIL_SMTP_PORT — puerto SMTP (default: 587)
  EMAIL_POLL_INTERVAL — segundos entre chequeos (default: 180)

Para Gmail: activar "Acceso de aplicaciones menos seguras" o crear App Password.
Para Outlook/Office365: usar contraseña de app.
"""

import os
import re
import asyncio
import email
import imaplib
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TZ_ARG = timezone(timedelta(hours=-3))

# ── Configuración ────────────────────────────────────────────────────────────
EMAIL_HOST     = os.getenv("EMAIL_HOST",     "imap.gmail.com")
EMAIL_USER     = os.getenv("EMAIL_USER",     "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
IMAP_PORT      = int(os.getenv("EMAIL_IMAP_PORT", "993"))
SMTP_PORT      = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_HOST      = os.getenv("EMAIL_SMTP_HOST", EMAIL_HOST.replace("imap.", "smtp."))
POLL_INTERVAL  = int(os.getenv("EMAIL_POLL_INTERVAL", "180"))  # 3 minutos

# Asunto por defecto para las respuestas
_SUBJECT_RE    = "Re: {original}"
_FROM_NAME     = "Eco Módulos & Piscinas"

# ── Decodificación de headers ────────────────────────────────────────────────

def _decodificar_header(valor: str) -> str:
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = []
    for parte, enc in partes:
        if isinstance(parte, bytes):
            try:
                resultado.append(parte.decode(enc or "utf-8", errors="replace"))
            except Exception:
                resultado.append(parte.decode("latin-1", errors="replace"))
        else:
            resultado.append(parte)
    return " ".join(resultado)


def _extraer_cuerpo(msg: email.message.Message) -> str:
    """Extrae el texto plano del email (prioriza text/plain sobre text/html)."""
    cuerpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    cuerpo  = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    pass
        if not cuerpo:
            for part in msg.walk():
                if part.get_content_type() == "text/html" and "attachment" not in part.get("Content-Disposition", ""):
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        html    = part.get_payload(decode=True).decode(charset, errors="replace")
                        # Extraer texto del HTML con regex básico
                        cuerpo  = re.sub(r"<[^>]+>", " ", html)
                        cuerpo  = re.sub(r"\s+", " ", cuerpo).strip()
                    except Exception:
                        pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            cuerpo  = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return cuerpo.strip()


def _extraer_telefono_email(texto: str) -> str:
    """Extrae teléfono de texto libre."""
    m = re.search(r"(?:\+?54\s*9?\s*)?(?:11|2[0-9]|3[0-9]|4[0-9])[\s\-]?\d{4}[\s\-]?\d{4}", texto)
    if m:
        t = re.sub(r"[^\d]", "", m.group(0))
        if not t.startswith("549"):
            t = "549" + (t[1:] if t.startswith("0") else t)
        return t if len(t) >= 11 else ""
    return ""


def _inferir_producto(asunto: str, cuerpo: str) -> str:
    texto = (asunto + " " + cuerpo).lower()
    if any(k in texto for k in ["piscina", "pileta", "pool", "fibra"]):
        return "piscina"
    if any(k in texto for k in ["modulo", "módulo", "vivienda", "casa", "nce", "prefab"]):
        return "modulo"
    if any(k in texto for k in ["combo", "piscina y modulo", "modulo y piscina"]):
        return "combo"
    return "general"


# ── IMAP: leer emails nuevos ─────────────────────────────────────────────────

def _leer_emails_nuevos() -> list[dict]:
    """
    Conecta al buzón IMAP y retorna los emails no leídos.
    Ejecutado en thread separado (operación sincrónica).
    """
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return []

    emails_nuevos = []
    try:
        imap = imaplib.IMAP4_SSL(EMAIL_HOST, IMAP_PORT)
        imap.login(EMAIL_USER, EMAIL_PASSWORD)
        imap.select("INBOX")

        _, ids = imap.search(None, "UNSEEN")
        if not ids or not ids[0]:
            imap.logout()
            return []

        for uid in ids[0].split()[-20:]:  # Máximo 20 emails por ciclo
            try:
                _, data = imap.fetch(uid, "(RFC822)")
                raw  = data[0][1]
                msg  = email.message_from_bytes(raw)

                de      = _decodificar_header(msg.get("From", ""))
                asunto  = _decodificar_header(msg.get("Subject", "Sin asunto"))
                cuerpo  = _extraer_cuerpo(msg)
                msg_id  = msg.get("Message-ID", "")
                fecha   = msg.get("Date", "")

                # Extraer email del remitente
                email_remitente = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", de)
                email_remitente = email_remitente.group(0).lower() if email_remitente else ""

                if not email_remitente or not cuerpo:
                    # Marcar como leído igual para no reprocesar
                    imap.store(uid, "+FLAGS", "\\Seen")
                    continue

                # Ignorar emails de sistemas (no-reply, postmaster, etc.)
                if any(k in email_remitente for k in ["noreply", "no-reply", "postmaster", "mailer-daemon"]):
                    imap.store(uid, "+FLAGS", "\\Seen")
                    continue

                emails_nuevos.append({
                    "uid":             uid,
                    "de":              de,
                    "email":           email_remitente,
                    "asunto":          asunto,
                    "cuerpo":          cuerpo[:2000],
                    "message_id":      msg_id,
                    "telefono":        _extraer_telefono_email(cuerpo),
                    "producto_interes": _inferir_producto(asunto, cuerpo),
                })

                # Marcar como leído para no reprocesar
                imap.store(uid, "+FLAGS", "\\Seen")

            except Exception as e:
                logger.warning(f"[Email] Error procesando email {uid}: {e}")
                continue

        imap.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"[Email] Error IMAP: {e}")
    except Exception as e:
        logger.error(f"[Email] Error inesperado: {e}")

    return emails_nuevos


# ── SMTP: enviar respuesta ───────────────────────────────────────────────────

def _enviar_respuesta(destinatario: str, asunto: str, cuerpo: str) -> bool:
    """Envía email de respuesta via SMTP. Sincrónico."""
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{_FROM_NAME} <{EMAIL_USER}>"
        msg["To"]      = destinatario
        msg["Subject"] = asunto

        texto_plano = MIMEText(cuerpo, "plain", "utf-8")
        msg.attach(texto_plano)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_USER, destinatario, msg.as_string())

        logger.info(f"[Email] Respuesta enviada a {destinatario}")
        return True

    except Exception as e:
        logger.error(f"[Email] Error enviando a {destinatario}: {e}")
        return False


# ── Procesamiento de un email ────────────────────────────────────────────────

async def _procesar_email(item: dict) -> None:
    """
    Procesa un email recibido:
    1. Crea/actualiza lead en CRM
    2. Genera respuesta con Valentina
    3. Envía respuesta por email
    4. Si tiene teléfono → también contacta por WhatsApp
    """
    try:
        from tools import crm_client
        from orchestrator.router import route_message

        email_addr = item["email"]
        session_id = f"email_{re.sub(r'[^a-z0-9]', '_', email_addr)}"
        nombre     = item["de"].split("<")[0].strip().split("@")[0].title()[:50]
        producto   = item["producto_interes"]
        cuerpo     = item["cuerpo"]
        asunto     = item["asunto"]
        telefono   = item.get("telefono", "")

        # ── Crear lead en CRM ────────────────────────────────────────────────
        lead = await crm_client.get_lead(session_id)
        if not lead:
            await crm_client.create_lead({
                "session_id":       session_id,
                "canal_origen":     "email",
                "agente_asignado":  "valentina",
                "estado":           "nuevo",
                "nombre":           nombre,
                "email":            email_addr,
                "telefono":         telefono,
                "producto_interes": producto,
            })
            logger.info(f"[Email] Nuevo lead creado: {email_addr}")

        # ── Obtener historial ────────────────────────────────────────────────
        historial = await crm_client.get_conversation_history(session_id, limit=5)
        contexto  = (
            f"El cliente escribe por EMAIL. "
            f"Su asunto: '{asunto}'. "
            f"Email del cliente: {email_addr}. "
            f"{'Historial: ' + historial if historial else ''}"
        )

        # ── Generar respuesta ────────────────────────────────────────────────
        result = await route_message(
            canal="email",
            session_id=session_id,
            mensaje=cuerpo,
            msg_type="text",
        )
        respuesta = result.get("reply", "")
        if not respuesta:
            return

        # ── Enviar respuesta por email ───────────────────────────────────────
        asunto_resp = _SUBJECT_RE.format(original=asunto)
        # Ejecutar en thread (smtplib es sincrónico)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _enviar_respuesta, email_addr, asunto_resp, respuesta
        )

        # ── Si tiene teléfono → también contactar por WhatsApp ───────────────
        if telefono and telefono.startswith("549"):
            try:
                from channels.whatsapp import send_whatsapp_message
                msg_wa = (
                    f"Hola {nombre}! Recibí tu consulta por email. "
                    f"Para responderte más rápido te escribo por acá también. "
                    f"{respuesta[:300]}"
                )
                await send_whatsapp_message(telefono, msg_wa)
                logger.info(f"[Email] También contactado por WA: {telefono}")
            except Exception as e:
                logger.warning(f"[Email] Error contactando WA {telefono}: {e}")

    except Exception as e:
        logger.error(f"[Email] Error procesando email de {item.get('email', '?')}: {e}")


# ── Loop de polling continuo ─────────────────────────────────────────────────

_polling_activo = False


async def iniciar_polling_email() -> None:
    """
    Loop infinito que chequea el buzón cada POLL_INTERVAL segundos.
    Se inicia como background task en el startup de FastAPI.
    """
    global _polling_activo

    if not EMAIL_USER or not EMAIL_PASSWORD:
        logger.info("[Email] Sin credenciales configuradas — canal email inactivo")
        return

    if _polling_activo:
        logger.warning("[Email] Polling ya activo, no se inicia otro")
        return

    _polling_activo = True
    logger.info(f"[Email] Polling iniciado — chequeando {EMAIL_USER} cada {POLL_INTERVAL}s")

    while True:
        try:
            loop  = asyncio.get_event_loop()
            items = await loop.run_in_executor(None, _leer_emails_nuevos)

            if items:
                logger.info(f"[Email] {len(items)} emails nuevos encontrados")
                for item in items:
                    await _procesar_email(item)
                    await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[Email] Error en ciclo de polling: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def procesar_ciclo_email_unico() -> int:
    """
    Ejecuta UN ciclo de chequeo de email (para llamar desde el scheduler).
    Retorna cantidad de emails procesados.
    """
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return 0
    try:
        loop  = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, _leer_emails_nuevos)
        for item in items:
            await _procesar_email(item)
            await asyncio.sleep(1)
        return len(items)
    except Exception as e:
        logger.error(f"[Email] Error en ciclo único: {e}")
        return 0
