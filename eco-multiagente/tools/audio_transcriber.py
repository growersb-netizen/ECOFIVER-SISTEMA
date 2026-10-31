"""
Transcripcion de audio a texto - modulo compartido para WhatsApp y Telegram.

Politica de EcoFiver: TODO el consumo de IA pasa por OpenRouter.
Antes: Groq Whisper -> OpenRouter (audio enviado como image_url) -> Gemini SDK.
Ahora: solo OpenRouter, con el formato de audio de la API (`input_audio`).

- Los formatos que no son wav/mp3 (WhatsApp y Telegram mandan OGG/Opus) se
  convierten a mp3 con ffmpeg (instalado en la imagen Docker). Si ffmpeg no
  esta disponible se intenta con el formato original.
- Modelos en orden: AUDIO_OPENROUTER_MODELS="modelo1,modelo2"
  (default: google/gemini-2.5-flash, google/gemini-2.5-flash-lite).
- Cada intento queda en /health/ia (agente "transcripcion").
- Si todo falla devuelve "(Audio recibido -- ...)": los canales responden
  pidiendo que el cliente escriba (comportamiento existente).
"""

import asyncio
import base64
import json as json_module
import logging
import os
import re
import shutil
import time

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Prompt ASCII puro (sin tildes) para evitar codec errors en cualquier entorno
_PROMPT = (
    "Transcribe this audio message in Argentine Spanish. "
    "Return ONLY the transcribed text. No quotes, no comments, no explanations. "
    "If empty or inaudible, return: (inaudible)"
)

_FORMATO_DIRECTO = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/mp3": "mp3"}
_FORMATO_ORIGINAL = {"audio/ogg": "ogg", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/webm": "webm",
                     "audio/flac": "flac", "audio/aac": "aac"}


# Respuestas típicas de un modelo que NO transcribió (negativas o descripciones del audio).
# Acotado a frases sobre la tarea, para no confundir a un cliente que dice "no puedo pagar".
_NO_TRANSCRIPCION_RE = re.compile(
    r"^\W*(?:"
    r"i'?m sorry|i am sorry|sorry,|i can'?t|i cannot|i'?m unable|i am unable|unable to|as an ai"
    r"|lo siento,? (?:pero )?no (?:puedo|pude) (?:ayudar|transcribir|procesar|escuchar|entender)"
    r"|no (?:puedo|pude|es posible) (?:transcribir|procesar|escuchar) (?:el|este|tu) audio"
    r"|(?:the|this) audio (?:is|contains|appears|seems)"
    r"|el audio (?:es|contiene|parece|está)"
    r")",
    re.IGNORECASE,
)


def no_es_transcripcion(texto: str) -> bool:
    return bool(_NO_TRANSCRIPCION_RE.search((texto or "").strip()))


def _modelos() -> list[str]:
    """Modelo y respaldos del rol "audio" (tools.model_policy; validados contra el catálogo)."""
    from tools.model_policy import resolver
    cfg = resolver("transcripcion")
    return [cfg.modelo] + [m for m in cfg.respaldo if m != cfg.modelo]


class _OpenRouterAudio:
    """Descriptor minimo para registrar la llamada en tools.ai_metrics."""
    def __init__(self, model: str):
        self._model = model


async def _a_mp3(audio_bytes: bytes) -> bytes | None:
    """Convierte cualquier audio a mp3 con ffmpeg. None si ffmpeg no esta o falla."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
            "-ac", "1", "-ar", "16000", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(audio_bytes), timeout=30)
        if proc.returncode == 0 and out:
            return out
        logger.warning(f"[Audio] ffmpeg fallo ({proc.returncode}): {err[:200]!r}")
    except Exception as e:
        logger.warning(f"[Audio] ffmpeg error: {e}")
    return None


async def _preparar(audio_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """Devuelve (bytes, formato) aptos para input_audio."""
    if mime in _FORMATO_DIRECTO:
        return audio_bytes, _FORMATO_DIRECTO[mime]
    mp3 = await _a_mp3(audio_bytes)
    if mp3:
        return mp3, "mp3"
    return audio_bytes, _FORMATO_ORIGINAL.get(mime, "ogg")


async def transcribir_bytes(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    idioma: str = "es",
) -> str:
    """
    Transcribe audio desde bytes via OpenRouter.

    Returns:
        Texto transcripto o mensaje de error descriptivo.
    """
    if not audio_bytes:
        return "(Audio vacio)"

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("[Audio] Sin OPENROUTER_API_KEY")
        return "(Audio recibido -- sin metodo de transcripcion activo)"

    clean_mime = mime_type.split(";")[0].strip()
    datos, formato = await _preparar(audio_bytes, clean_mime)

    for model in _modelos():
        t0 = time.monotonic()
        try:
            texto = await _openrouter(datos, formato, model, api_key)
            if texto and no_es_transcripcion(texto):
                # El modelo respondió algo que no es la transcripción (una negativa o
                # una descripción). Antes se le pasaba al agente como si fuera lo que
                # dijo el usuario.
                _medir(model, ok=False, t0=t0, error=f"respuesta no es transcripción: {texto[:80]}")
                logger.warning(f"[Audio] {model} no devolvió una transcripción: {texto[:160]!r}")
                continue
            _medir(model, ok=bool(texto), t0=t0, chars_out=len(texto or ""))
            if texto:
                return texto
        except httpx.HTTPStatusError as e:
            _medir(model, ok=False, t0=t0, error=f"HTTP {e.response.status_code}")
            logger.warning(f"[Audio] OpenRouter {model} HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            _medir(model, ok=False, t0=t0, error=str(e))
            logger.warning(f"[Audio] OpenRouter {model} fallo: {e}")

    logger.warning("[Audio] Todos los modelos de OpenRouter fallaron")
    return "(Audio recibido -- sin metodo de transcripcion activo)"


def _medir(model: str, ok: bool, t0: float, chars_in: int = 0, chars_out: int = 0, error: str = "") -> None:
    try:
        from tools.ai_metrics import registrar_llamada
        registrar_llamada(agente="transcripcion", provider=_OpenRouterAudio(model), ok=ok, fallback=False,
                          latencia_s=time.monotonic() - t0, chars_in=chars_in, chars_out=chars_out, error=error)
    except Exception:
        pass


async def _openrouter(audio_bytes: bytes, formato: str, model: str, api_key: str) -> str:
    """Envia el audio como input_audio (formato de la API de OpenRouter)."""
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "input_audio", "input_audio": {
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                    "format": formato,
                }},
            ],
        }],
        "max_tokens": 1000,
    }

    # ensure_ascii=True garantiza que no haya bytes > 127 en el body
    body = json_module.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://eco-multiagente-production.up.railway.app",
        "X-Title":       "EcoFiver IA",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(_OPENROUTER_URL, content=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    try:
        from tools.ai_metrics import informar_uso
        informar_uso(data.get("usage"))
    except Exception:
        pass

    texto = (data["choices"][0]["message"]["content"] or "").strip()
    # Limpiar prefijos que el modelo agrega a veces
    for prefix in ("Transcription:", "The audio says:", "Audio:", "Transcripcion:"):
        if texto.lower().startswith(prefix.lower()):
            texto = texto[len(prefix):].strip()
            break

    logger.info(f"[Audio/OR:{model}] OK ({len(audio_bytes)}B {formato}): {texto[:80]}")
    return texto
