"""
Lectura de documentos por foto (DNI, etc.) — usa un modelo con visión real
(no el truco de audio-como-imagen). Mismo proveedor que el resto del sistema:
OpenRouter con un modelo que soporte image_url de verdad.
"""

import base64
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o-mini")

_PROMPT_DNI = """Esta es una foto de un documento de identidad argentino (DNI, frente o dorso).
Extraé EXACTAMENTE los datos que puedas leer con claridad. Si un dato no está visible o no
podés leerlo con confianza, dejalo como null — NUNCA inventes ni completes un dato que no ves.

Devolvé SOLO un JSON válido, sin texto antes ni después, con esta forma exacta:
{
  "nombre": string o null,
  "apellido": string o null,
  "dni": string o null (solo números),
  "fecha_nacimiento": string o null (formato DD/MM/AAAA),
  "sexo": string o null,
  "nacionalidad": string o null,
  "domicilio": string o null,
  "lugar_nacimiento": string o null,
  "fecha_emision": string o null (formato DD/MM/AAAA),
  "fecha_vencimiento": string o null (formato DD/MM/AAAA),
  "cara_detectada": "frente" o "dorso" o "desconocido",
  "confianza": "alta" o "media" o "baja"
}"""


async def extraer_datos_documento(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Extrae datos de un documento (DNI) desde una foto usando visión real.
    Retorna dict con los campos del prompt, o {"error": "..."} si falla.
    Nunca inventa: los campos no legibles vienen en null desde el propio modelo.
    """
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY no configurada"}

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT_DNI},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 500,
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
                    "X-Title": "EcoFiver",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.error(f"[Vision] Error llamando a OpenRouter: {e}")
        return {"error": str(e)}

    texto = data["choices"][0]["message"]["content"].strip()
    # El modelo a veces envuelve el JSON en ```json ... ```
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        extraido = json.loads(texto)
    except Exception as e:
        logger.warning(f"[Vision] Respuesta no era JSON válido: {e} — raw: {texto[:200]}")
        return {"error": "No pude interpretar el documento con claridad"}

    logger.info(f"[Vision] DNI extraído: {extraido.get('nombre')} {extraido.get('apellido')} — DNI {extraido.get('dni')}")
    return extraido
