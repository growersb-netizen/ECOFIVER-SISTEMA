"""
Transcripcion de audio a texto - modulo compartido para WhatsApp y Telegram.

Estrategia (en orden de prioridad):
  1. Groq Whisper   (GROQ_API_KEY que empiece con gsk_  -- groq.com, no xAI)
  2. OpenRouter con google/gemini-2.5-flash-preview:free
  3. OpenRouter con google/gemini-flash-1.5-8b:free     (fallback modelo)
  4. Gemini SDK directo si hay GEMINI_API_KEY
  5. Mensaje descriptivo (no bloquea el flujo)

OGG/Opus es el formato de WhatsApp y Telegram Voice Notes.
"""

import io
import os
import base64
import json as json_module
import logging

import httpx

logger = logging.getLogger(__name__)

# Groq.com (Whisper) -- clave empieza con gsk_
# DISTINTO de xAI Grok (GROK_API_KEY que NO empieza con gsk_)
_groq_raw    = os.getenv("GROQ_API_KEY", "") or os.getenv("GROK_API_KEY", "")
GROQ_API_KEY = _groq_raw if _groq_raw.startswith("gsk_") else ""

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

# Modelos OpenRouter a intentar en orden (el primero que funcione)
_OR_MODELS = [
    "google/gemini-2.5-flash-preview:free",
    "google/gemini-flash-1.5-8b:free",
    "google/gemini-flash-1.5",
]
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_GROQ_URL           = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

# Prompt ASCII puro (sin tildes) para evitar codec errors en cualquier entorno
_PROMPT = (
    "Transcribe this audio message in Argentine Spanish. "
    "Return ONLY the transcribed text. No quotes, no comments, no explanations. "
    "If empty or inaudible, return: (inaudible)"
)

_MIME_TO_FILENAME = {
    "audio/ogg":   "audio.ogg",
    "audio/mpeg":  "audio.mp3",
    "audio/mp4":   "audio.m4a",
    "audio/wav":   "audio.wav",
    "audio/webm":  "audio.webm",
    "audio/flac":  "audio.flac",
    "audio/x-m4a": "audio.m4a",
}


async def transcribir_bytes(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    idioma: str = "es",
) -> str:
    """
    Transcribe audio desde bytes usando la primera API disponible.

    Returns:
        Texto transcripto o mensaje de error descriptivo.
    """
    if not audio_bytes:
        return "(Audio vacio)"

    clean_mime = mime_type.split(";")[0].strip()

    # ── Metodo 1: Groq Whisper ─────────────────────────────────────────────
    if GROQ_API_KEY:
        try:
            resultado = await _groq(audio_bytes, clean_mime, idioma)
            if resultado and resultado.strip():
                return resultado
        except Exception as e:
            logger.warning(f"[Audio] Groq Whisper fallo: {e}")
    else:
        logger.debug("[Audio] No hay GROQ_API_KEY valida (gsk_...) -- saltando Groq")

    # ── Metodo 2: OpenRouter (prueba modelos en orden) ─────────────────────
    if OPENROUTER_API_KEY:
        for model in _OR_MODELS:
            try:
                resultado = await _openrouter(audio_bytes, clean_mime, model)
                if resultado and not resultado.startswith("(Error"):
                    return resultado
            except httpx.HTTPStatusError as e:
                logger.warning(f"[Audio] OpenRouter {model} HTTP {e.response.status_code}: {e}")
                continue
            except Exception as e:
                logger.warning(f"[Audio] OpenRouter {model} fallo: {e}")
                continue
        logger.warning("[Audio] Todos los modelos de OpenRouter fallaron")

    # ── Metodo 3: Gemini SDK directo ───────────────────────────────────────
    if GEMINI_API_KEY:
        try:
            return await _gemini_sdk(audio_bytes, clean_mime)
        except Exception as e:
            logger.error(f"[Audio] Gemini SDK fallo: {e}")

    logger.warning("[Audio] Sin metodo de transcripcion disponible")
    return "(Audio recibido -- sin metodo de transcripcion activo)"


async def _groq(audio_bytes: bytes, mime: str, idioma: str) -> str:
    filename = _MIME_TO_FILENAME.get(mime, "audio.ogg")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, mime)},
            data={"model": _GROQ_WHISPER_MODEL, "language": idioma, "response_format": "text"},
        )
        r.raise_for_status()
    texto = r.text.strip()
    logger.info(f"[Audio/Groq] OK ({len(audio_bytes)}B): {texto[:80]}")
    return texto


async def _openrouter(audio_bytes: bytes, mime: str, model: str) -> str:
    """
    Envia audio como data URL multimodal a OpenRouter.
    Usa json.dumps con ensure_ascii=True para evitar codec errors.
    """
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    data_url  = f"data:{mime};base64,{audio_b64}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
        "max_tokens": 1000,
    }

    # ensure_ascii=True garantiza que no haya bytes > 127 en el body
    body = json_module.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://eco-multiagente-polished-sunset-4227.fly.dev",
        "X-Title":       "Eco Modulos IA",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(_OPENROUTER_URL, content=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    texto = data["choices"][0]["message"]["content"].strip()
    # Limpiar prefijos que el modelo agrega a veces
    for prefix in ("Transcription:", "The audio says:", "Audio:", "Transcripcion:"):
        if texto.lower().startswith(prefix.lower()):
            texto = texto[len(prefix):].strip()
            break

    logger.info(f"[Audio/OR:{model}] OK ({len(audio_bytes)}B): {texto[:80]}")
    return texto


async def _gemini_sdk(audio_bytes: bytes, mime: str) -> str:
    """Fallback: SDK oficial de Gemini con upload via BytesIO."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    # SDK necesita un file-like object, NO bytes crudos
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = _MIME_TO_FILENAME.get(mime, "audio.ogg")

    uploaded = client.files.upload(
        file=audio_file,
        config={"mime_type": mime},
    )

    result = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime),
            types.Part(text=_PROMPT),
        ],
    )

    texto = result.text.strip()
    logger.info(f"[Audio/Gemini] OK ({len(audio_bytes)}B): {texto[:80]}")
    return texto
