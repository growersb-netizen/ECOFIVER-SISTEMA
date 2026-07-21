"""
Procesamiento de audio con Gemini nativo.
Descarga el audio de WhatsApp y lo transcribe con Gemini.
"""
import httpx
import base64
import tempfile
import os
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL, WHATSAPP_TOKEN

genai.configure(api_key=GEMINI_API_KEY)


async def download_whatsapp_media(media_id: str) -> bytes:
    """Descarga un archivo de media de WhatsApp dado su media_id."""
    async with httpx.AsyncClient() as client:
        # Primero obtenemos la URL del archivo
        url_response = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        url_response.raise_for_status()
        media_url = url_response.json()["url"]

        # Descargamos el archivo
        file_response = await client.get(
            media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        file_response.raise_for_status()
        return file_response.content


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcribe audio usando Gemini nativo.
    Gemini 2.0 Flash soporta audio directamente sin necesidad de Whisper.
    """
    try:
        # Convertimos a base64
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        model = genai.GenerativeModel(model_name=GEMINI_MODEL)

        # Gemini puede procesar audio directamente
        response = model.generate_content([
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": audio_b64
                }
            },
            "Transcribí este audio en español argentino, palabra por palabra. Solo el texto, sin explicaciones."
        ])
        return response.text.strip()
    except Exception as e:
        # Si falla la transcripción, retornamos un mensaje genérico
        return "[Audio recibido - no se pudo transcribir]"


async def process_whatsapp_audio(media_id: str, mime_type: str = "audio/ogg") -> str:
    """
    Pipeline completo: descarga audio de WhatsApp y lo transcribe.
    Retorna el texto transcripto.
    """
    try:
        audio_bytes = await download_whatsapp_media(media_id)
        transcript = await transcribe_audio(audio_bytes, mime_type)
        return transcript
    except Exception as e:
        return "[Recibí tu audio pero no pude entenderlo bien. ¿Me podés escribir?]"
