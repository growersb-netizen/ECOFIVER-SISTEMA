import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"

# WhatsApp Meta Cloud API
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "ecomodulos_verify_2024")
WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

# Telegram — notificaciones a Rodo
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "ecomodulos.db")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Flete
FLETE_BASE_KM = 3000  # $ por km desde Zárate

# Horarios videollamada
VIDEOLLAMADA_HORARIO = "lunes a viernes 11:30 a 18:00hs"
VIDEOLLAMADA_MAX_POR_HORA = 2


# ─── Validación de variables críticas ────────────────────────────────────────

_REQUIRED_VARS = {
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "WHATSAPP_TOKEN": WHATSAPP_TOKEN,
    "WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
}


def validate_config() -> None:
    """Verifica que todas las variables de entorno críticas estén configuradas.
    Loggea un error claro por cada variable faltante. No detiene el proceso
    para permitir correr en modo simulado/desarrollo, pero advierte en stderr.
    """
    import logging
    log = logging.getLogger("config")
    missing = [k for k, v in _REQUIRED_VARS.items() if not v]
    if missing:
        for var in missing:
            log.error(
                "Variable de entorno requerida no configurada: %s — "
                "agregala al archivo .env o como secret en Fly.io", var
            )
        log.warning(
            "La app puede funcionar en modo limitado sin las variables anteriores."
        )
