"""
Cliente para el panel Ecopost (Cloudflare Workers + Gemini Imagen 3).
Genera imágenes para marketing y las sube a Google Drive.

Worker endpoints (v2.0):
  GET  /health          → {"ok": true}
  POST /generate        → {"ok": true, "image_base64": "...", "mime_type": "image/png"}
  POST /generar-copy    → {"ok": true, "copy": "..."}
  POST /api/gemini      → compat
  POST /api/imagen      → compat
"""

import httpx
import os
import logging
import base64
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CLOUDFLARE_WORKER_URL = os.getenv(
    "CLOUDFLARE_WORKER_URL",
    "https://eco-agentes.growersb.workers.dev",
)
GOOGLE_DRIVE_FOLDER_ID = os.getenv(
    "GOOGLE_DRIVE_FOLDER_ID",
    "1tXwe5E9M7R31Q8X-fMhpmn-TgVWPak4W",
)

TIMEOUT = 60.0  # Las generaciones de imagen pueden tardar

# Mapeo de categorías a subcarpetas de Drive
CARPETAS_DRIVE = {
    "piscina_flyer":  "Piscinas/Flyers 1080x1080",
    "piscina_story":  "Piscinas/Stories 9x16",
    "modulo_flyer":   "Módulos/Flyers 1080x1080",
    "modulo_story":   "Módulos/Stories 9x16",
    "combo":          "Combos",
    "publicado":      "Publicado",
    "archivo":        "Archivo",
}


async def health_check() -> bool:
    """Devuelve True si el worker responde."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{CLOUDFLARE_WORKER_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


async def generar_imagen(
    prompt_es: str,
    tipo: str = "flyer",
    foto_base: bytes | None = None,
    categoria: str = "piscina_flyer",
) -> bytes:
    """
    Llama al worker de Cloudflare para generar una imagen con Gemini Imagen 3.

    Args:
        prompt_es: descripción en español de la imagen a generar
        tipo: "flyer" (1080x1080) o "story" (9:16 → 1080x1920)
        foto_base: imagen opcional en bytes para usar como base
        categoria: clave de CARPETAS_DRIVE para organizar el resultado

    Returns:
        bytes de la imagen generada (PNG)
    """
    dimensiones = {
        "flyer": {"width": 1080, "height": 1080},
        "story": {"width": 1080, "height": 1920},
    }
    dims = dimensiones.get(tipo, dimensiones["flyer"])

    payload = {
        "prompt": prompt_es,
        "width": dims["width"],
        "height": dims["height"],
        "language": "es",
    }

    if foto_base:
        payload["image_base64"] = base64.b64encode(foto_base).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Intentar nuevo endpoint /generate (worker v2.0)
            r = await client.post(
                f"{CLOUDFLARE_WORKER_URL}/generate",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

            if data.get("ok") and data.get("image_base64"):
                # Worker v2.0: devuelve JSON con base64
                return base64.b64decode(data["image_base64"])

            # Fallback: worker v1.0 /api/imagen (devuelve Gemini raw JSON)
            r2 = await client.post(
                f"{CLOUDFLARE_WORKER_URL}/api/imagen",
                json={"prompt": prompt_es},
            )
            r2.raise_for_status()
            raw = r2.json()
            b64 = raw.get("predictions", [{}])[0].get("bytesBase64Encoded")
            if b64:
                return base64.b64decode(b64)
            raise ValueError("Worker no devolvió imagen")

    except Exception as e:
        logger.error(f"[cloudflare_client] generar_imagen falló: {e}")
        raise


async def generar_imagen_gemini(prompt_es: str, tipo: str = "flyer") -> bytes:
    """
    Genera una imagen directamente con los modelos Gemini de imagen
    (generateContent con responseModalities=IMAGE). Útil cuando el worker
    de Cloudflare no tiene GEMINI_API_KEY propia.

    Prueba varios modelos en orden. Si todos dan 429 (cuota agotada del free
    tier), levanta un error claro para que la UI lo muestre.
    Returns: bytes PNG/JPEG.
    """
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    orientacion = "vertical 9:16 (story)" if tipo == "story" else "cuadrada 1:1 (feed)"
    full_prompt = (
        f"Generá una foto publicitaria profesional, fotorrealista, de alta calidad, "
        f"orientación {orientacion}, para redes sociales de una empresa argentina de "
        f"módulos habitables y piscinas de fibra. {prompt_es}. "
        f"Sin texto ni logos superpuestos, iluminación natural, estética aspiracional."
    )
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    modelos = ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image"]
    ultimo_err = ""
    cuota_agotada = False

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for modelo in modelos:
            try:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={key}",
                    json=body,
                )
                if r.status_code == 429:
                    cuota_agotada = True
                    ultimo_err = "cuota de generación de imágenes agotada"
                    continue
                r.raise_for_status()
                data = r.json()
                for cand in data.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        idata = part.get("inlineData") or part.get("inline_data")
                        if idata and idata.get("data"):
                            return base64.b64decode(idata["data"])
                ultimo_err = "el modelo no devolvió imagen"
            except Exception as e:
                ultimo_err = str(e)[:120]
                continue

    if cuota_agotada:
        raise RuntimeError(
            "Se alcanzó el límite diario de generación de imágenes (plan gratuito). "
            "Probá de nuevo más tarde o subí tu propia foto."
        )
    raise RuntimeError(f"No se pudo generar la imagen: {ultimo_err}")


async def generar_copy(
    producto: str,
    modelo: str = "",
    descripcion: str = "",
    tono: str = "profesional y cercano",
) -> str:
    """
    Genera copy de redes sociales via worker (Gemini Flash).
    Devuelve el texto generado.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CLOUDFLARE_WORKER_URL}/generar-copy",
                json={
                    "producto": producto,
                    "modelo": modelo,
                    "descripcion": descripcion,
                    "tono": tono,
                },
            )
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return data.get("copy", "")
    except Exception as e:
        logger.error(f"[cloudflare_client] generar_copy falló: {e}")
    return ""


async def generar_y_subir(
    prompt_es: str,
    nombre: str,
    tipo: str = "flyer",
    categoria: str = "piscina_flyer",
    foto_base: bytes | None = None,
) -> dict:
    """
    Pipeline completo: genera imagen.
    (Subida a Drive quedó deprecada — las imágenes se guardan en la DB como base64.)

    Returns:
        dict con imagen_bytes, nombre_archivo, carpeta
    """
    imagen = await generar_imagen(prompt_es, tipo, foto_base, categoria)

    return {
        "imagen_bytes": imagen,
        "imagen_base64": base64.b64encode(imagen).decode("utf-8"),
        "nombre_archivo": f"{nombre}.png",
        "carpeta": CARPETAS_DRIVE.get(categoria, "Archivo"),
    }
