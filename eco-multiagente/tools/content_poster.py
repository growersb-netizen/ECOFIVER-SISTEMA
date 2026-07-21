"""
Motor de contenido orgánico — Renata genera y publica automáticamente.
Publicaciones en Facebook e Instagram via Meta Graph API.
El contenido orgánico genera inbound leads sin costo.

Requiere:
  META_PAGE_ACCESS_TOKEN — token con permisos: pages_manage_posts, instagram_content_publish
  META_PAGE_ID           — ID numérico de la página de Facebook
  META_IG_USER_ID        — ID numérico de la cuenta de Instagram Business

Estrategia de contenido:
  - Lunes/Miércoles/Viernes: post de producto (módulos o piscinas según temporada)
  - Martes/Jueves: post educativo (beneficios, proceso, financiación)
  - Sábado: testimonio / caso de éxito
  - Domingo: post aspiracional / lifestyle
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

_TZ_ARG = timezone(timedelta(hours=-3))

META_PAGE_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
META_PAGE_ID    = os.getenv("META_PAGE_ID", "")
META_IG_USER_ID = os.getenv("META_IG_USER_ID", "")
META_API_BASE   = "https://graph.facebook.com/v19.0"


# ── Tipo de contenido según día y temporada ──────────────────────────────────

def _tipo_contenido_hoy() -> dict:
    """Retorna el tipo de post y producto recomendado para hoy."""
    now     = datetime.now(_TZ_ARG)
    dia     = now.weekday()   # 0=lunes … 6=domingo
    mes     = now.month

    # Temporada
    if mes in (12, 1, 2, 3):
        temporada = "verano"
        producto_star = "piscina"
    elif mes in (6, 7, 8):
        temporada = "invierno"
        producto_star = "modulo"
    else:
        temporada = "transicion"
        producto_star = "combo"

    tipos = {
        0: {"tipo": "producto",     "foco": producto_star},   # lunes
        1: {"tipo": "educativo",    "foco": "financiacion"},  # martes
        2: {"tipo": "producto",     "foco": producto_star},   # miércoles
        3: {"tipo": "educativo",    "foco": "proceso"},       # jueves
        4: {"tipo": "producto",     "foco": producto_star},   # viernes
        5: {"tipo": "testimonio",   "foco": "social_proof"},  # sábado
        6: {"tipo": "aspiracional", "foco": "lifestyle"},     # domingo
    }
    config = tipos.get(dia, tipos[0])
    config["temporada"] = temporada
    config["dia"]       = now.strftime("%A")
    return config


# ── Generación de contenido con Renata ──────────────────────────────────────

async def generar_contenido(config: dict | None = None) -> dict | None:
    """
    Renata genera el texto del post para hoy.
    Retorna dict con 'texto_fb', 'texto_ig' y 'hashtags', o None si falla.
    """
    if config is None:
        config = _tipo_contenido_hoy()

    tipo      = config["tipo"]
    foco      = config["foco"]
    temporada = config.get("temporada", "transicion")

    prompts = {
        "producto": (
            f"Generá un post para Facebook/Instagram de Eco Módulos & Piscinas. "
            f"Temporada: {temporada}. Producto foco: {foco}. "
            "Tipo: post de producto atractivo que muestre los beneficios principales. "
            "Incluir: característica estrella, precio referencial o financiación, CTA claro. "
            "IMPORTANTE: si NO es verano, destacá fuerte la FINANCIACIÓN PROPIA de fábrica "
            "(cuotas SIN interés, sin banco) para asegurar la piscina ahora y tenerla instalada "
            "para el próximo verano. El CTA siempre invita a escribir por WhatsApp/DM. "
            "Tono: cálido, aspiracional, argentino. Sin markdown, texto plano. Máx 200 palabras. "
            "Al final, en una línea separada, escribí 8 hashtags relevantes para Argentina."
        ),
        "educativo": (
            f"Generá un post educativo para Facebook/Instagram de Eco Módulos & Piscinas. "
            f"Tema: {foco}. "
            "Tipo: contenido que enseña algo útil (proceso de compra, qué incluye la instalación, "
            "cómo funciona la financiación, diferencias entre productos). "
            "CTA: invitá a consultar por WhatsApp o DM. "
            "Sin markdown, texto plano. Máx 180 palabras. "
            "Al final: 8 hashtags relevantes para Argentina."
        ),
        "testimonio": (
            "Generá un post de testimonio/caso de éxito INVENTADO PERO VEROSÍMIL para "
            "Eco Módulos & Piscinas. Familia argentina real (nombre, ciudad, producto). "
            "Que cuente el antes y el después. Emotivo pero concreto. "
            "Nota: este es un testimonio representativo de nuestros clientes. "
            "Sin markdown. Máx 200 palabras. Al final: 8 hashtags."
        ),
        "aspiracional": (
            "Generá un post aspiracional/lifestyle para Eco Módulos & Piscinas. "
            "Que pinte el imaginario: tener la piscina o la casa de los sueños. "
            "Verano, familia, disfrute, independencia. Sin hablar solo de producto — hablar de vida. "
            "CTA suave: 'escribinos y lo hacemos posible'. "
            "Sin markdown. Máx 150 palabras. Al final: 8 hashtags."
        ),
    }

    prompt = prompts.get(tipo, prompts["producto"])

    try:
        from agents.renata import get_agent
        renata  = get_agent()
        content = await renata.respond(prompt)

        if not content or len(content) < 50:
            return None

        # Separar texto de hashtags
        lines     = content.strip().split("\n")
        hashtags  = ""
        texto     = content

        for i, line in enumerate(lines):
            if line.strip().startswith("#") or line.count("#") >= 3:
                hashtags = line.strip()
                texto    = "\n".join(lines[:i]).strip()
                break

        # Versión para Instagram (más corta, solo hashtags al final)
        texto_ig = texto + ("\n\n" + hashtags if hashtags else "")
        # Versión para Facebook (más larga, sin saturar de hashtags)
        texto_fb = texto + ("\n\n" + " ".join(hashtags.split()[:5]) if hashtags else "")

        return {
            "tipo":      tipo,
            "foco":      foco,
            "texto_fb":  texto_fb[:5000],
            "texto_ig":  texto_ig[:2200],
            "hashtags":  hashtags,
            "generado":  datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        logger.error(f"[Content] Error generando contenido: {e}")
        return None


# ── Publicar en Facebook ─────────────────────────────────────────────────────

async def publicar_facebook(texto: str) -> bool:
    """Publica un post de texto en la página de Facebook."""
    if not META_PAGE_TOKEN or not META_PAGE_ID:
        logger.info("[Content/FB] Sin configuración — post no enviado")
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{META_API_BASE}/{META_PAGE_ID}/feed",
                params={"access_token": META_PAGE_TOKEN},
                json={"message": texto},
            )
            if r.status_code == 200:
                post_id = r.json().get("id", "?")
                logger.info(f"[Content/FB] Post publicado: {post_id}")
                return True
            else:
                logger.warning(f"[Content/FB] Error {r.status_code}: {r.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"[Content/FB] Error publicando: {e}")
        return False


async def publicar_facebook_foto(imagen_bytes: bytes, caption: str = "") -> bool:
    """Publica una FOTO en la página de Facebook (endpoint /photos, multipart)."""
    if not META_PAGE_TOKEN or not META_PAGE_ID:
        logger.info("[Content/FB] Sin configuración — foto no enviada")
        return False
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{META_API_BASE}/{META_PAGE_ID}/photos",
                params={"access_token": META_PAGE_TOKEN},
                data={"caption": caption[:5000]},
                files={"source": ("post.png", imagen_bytes, "image/png")},
            )
            if r.status_code == 200:
                j = r.json()
                logger.info(f"[Content/FB] Foto publicada: {j.get('post_id', j.get('id','?'))}")
                return True
            logger.warning(f"[Content/FB] Error foto {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[Content/FB] Error publicando foto: {e}")
        return False


async def _subir_foto_url_publica(imagen_bytes: bytes) -> str:
    """
    Sube una foto a la página como NO publicada y devuelve su URL pública (fbcdn),
    necesaria para Instagram (que exige image_url accesible). "" si falla.
    """
    if not META_PAGE_TOKEN or not META_PAGE_ID:
        return ""
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{META_API_BASE}/{META_PAGE_ID}/photos",
                params={"access_token": META_PAGE_TOKEN, "published": "false"},
                files={"source": ("ig.png", imagen_bytes, "image/png")},
            )
            if r.status_code != 200:
                logger.warning(f"[Content/IG] subir unpublished error: {r.text[:200]}")
                return ""
            photo_id = r.json().get("id")
            if not photo_id:
                return ""
            r2 = await c.get(
                f"{META_API_BASE}/{photo_id}",
                params={"access_token": META_PAGE_TOKEN, "fields": "images"},
            )
            imgs = r2.json().get("images", [])
            return imgs[0].get("source", "") if imgs else ""
    except Exception as e:
        logger.warning(f"[Content/IG] _subir_foto_url_publica falló: {e}")
        return ""


async def _publicar_ig_con_url(image_url: str, caption: str) -> bool:
    """Crea y publica un container de Instagram a partir de una URL de imagen."""
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r1 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media",
                params={"access_token": META_PAGE_TOKEN},
                json={"image_url": image_url, "caption": caption[:2200]},
            )
            if r1.status_code != 200:
                logger.warning(f"[Content/IG] Error creando media: {r1.text[:200]}")
                return False
            container_id = r1.json().get("id")
            await asyncio.sleep(5)
            r2 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media_publish",
                params={"access_token": META_PAGE_TOKEN},
                json={"creation_id": container_id},
            )
            if r2.status_code == 200:
                logger.info(f"[Content/IG] Foto IG publicada: {r2.json().get('id','?')}")
                return True
            logger.warning(f"[Content/IG] Error publicando: {r2.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[Content/IG] Error: {e}")
        return False


async def publicar_instagram_foto(imagen_bytes: bytes, caption: str = "") -> bool:
    """Publica una FOTO en Instagram a partir de bytes (sube → URL pública → publica)."""
    if not META_PAGE_TOKEN or not META_IG_USER_ID:
        logger.info("[Content/IG] Sin configuración IG — foto no enviada")
        return False
    image_url = await _subir_foto_url_publica(imagen_bytes)
    if not image_url:
        logger.warning("[Content/IG] No se pudo obtener URL pública de la imagen")
        return False
    return await _publicar_ig_con_url(image_url, caption)


# ── Hosting público (R2 del sitio web) para video / imágenes grandes ────────

_R2_UPLOAD_URL = os.getenv("R2_UPLOAD_URL", "https://www.ecomodulosypiscinas.com.ar/api/admin/upload")
_R2_API_KEY    = os.getenv("R2_API_KEY", "eco-crm-api-key-2024")


async def subir_a_r2(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Sube un archivo al R2 del sitio y devuelve la URL pública. '' si falla."""
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                _R2_UPLOAD_URL,
                headers={"x-api-key": _R2_API_KEY},
                files={"file": (filename, file_bytes, content_type)},
            )
            if r.status_code not in (200, 201):
                logger.warning(f"[R2] upload error {r.status_code}: {r.text[:200]}")
                return ""
            d = r.json()
            return d.get("url") or d.get("imagen_url") or d.get("path") or ""
    except Exception as e:
        logger.warning(f"[R2] subir_a_r2 falló: {e}")
        return ""


async def publicar_facebook_video(video_bytes: bytes, caption: str = "") -> bool:
    """Publica un VIDEO en la página de Facebook (endpoint /videos, multipart)."""
    if not META_PAGE_TOKEN or not META_PAGE_ID:
        return False
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"{META_API_BASE}/{META_PAGE_ID}/videos",
                params={"access_token": META_PAGE_TOKEN},
                data={"description": caption[:5000]},
                files={"source": ("video.mp4", video_bytes, "video/mp4")},
            )
            if r.status_code == 200:
                logger.info(f"[Content/FB] Video publicado: {r.json().get('id','?')}")
                return True
            logger.warning(f"[Content/FB] Error video {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[Content/FB] Error publicando video: {e}")
        return False


async def publicar_instagram_video(video_bytes: bytes, caption: str = "") -> bool:
    """
    Publica un VIDEO/REEL en Instagram. Sube el video a R2 para obtener URL pública,
    crea el container REELS, espera el procesamiento y publica.
    """
    if not META_PAGE_TOKEN or not META_IG_USER_ID:
        return False
    video_url = await subir_a_r2(video_bytes, "reel.mp4", "video/mp4")
    if not video_url:
        logger.warning("[Content/IG] No se pudo hostear el video para IG")
        return False
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r1 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media",
                params={"access_token": META_PAGE_TOKEN},
                json={"media_type": "REELS", "video_url": video_url, "caption": caption[:2200]},
            )
            if r1.status_code != 200:
                logger.warning(f"[Content/IG] Error creando reel: {r1.text[:200]}")
                return False
            container_id = r1.json().get("id")

            # El video tarda en procesarse: poll hasta FINISHED (máx ~60s)
            for _ in range(20):
                await asyncio.sleep(5)
                rs = await c.get(
                    f"{META_API_BASE}/{container_id}",
                    params={"access_token": META_PAGE_TOKEN, "fields": "status_code"},
                )
                if rs.json().get("status_code") == "FINISHED":
                    break

            r2 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media_publish",
                params={"access_token": META_PAGE_TOKEN},
                json={"creation_id": container_id},
            )
            if r2.status_code == 200:
                logger.info(f"[Content/IG] Reel publicado: {r2.json().get('id','?')}")
                return True
            logger.warning(f"[Content/IG] Error publicando reel: {r2.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[Content/IG] Error publicando video: {e}")
        return False


async def publicar_instagram_texto(texto: str) -> bool:
    """
    Publica un post de texto en Instagram Business.
    NOTA: Instagram requiere imagen para posts en feed.
    Este método usa la API de Instagram para posts con imagen/carrusel.
    Para posts solo de texto, usa las Stories o el caption de una imagen.
    Si no hay imagen configurada, loguea sin publicar.
    """
    if not META_PAGE_TOKEN or not META_IG_USER_ID:
        logger.info("[Content/IG] Sin configuración — post IG no enviado")
        return False

    IG_DEFAULT_IMAGE = os.getenv("IG_DEFAULT_IMAGE_URL", "")
    if not IG_DEFAULT_IMAGE:
        logger.info("[Content/IG] IG_DEFAULT_IMAGE_URL no configurada — solo FB por ahora")
        return False

    try:
        # Paso 1: crear container de media
        async with httpx.AsyncClient(timeout=30) as c:
            r1 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media",
                params={"access_token": META_PAGE_TOKEN},
                json={
                    "image_url": IG_DEFAULT_IMAGE,
                    "caption":   texto,
                },
            )
            if r1.status_code != 200:
                logger.warning(f"[Content/IG] Error creando media: {r1.text[:200]}")
                return False
            container_id = r1.json().get("id")

            # Esperar a que procese
            await asyncio.sleep(5)

            # Paso 2: publicar el container
            r2 = await c.post(
                f"{META_API_BASE}/{META_IG_USER_ID}/media_publish",
                params={"access_token": META_PAGE_TOKEN},
                json={"creation_id": container_id},
            )
            if r2.status_code == 200:
                ig_id = r2.json().get("id", "?")
                logger.info(f"[Content/IG] Post IG publicado: {ig_id}")
                return True
            else:
                logger.warning(f"[Content/IG] Error publicando: {r2.text[:200]}")
                return False

    except Exception as e:
        logger.error(f"[Content/IG] Error: {e}")
        return False


# ── Comentar en posts de Instagram (engagement orgánico) ────────────────────

async def responder_comentario_ig(
    media_id: str,
    comentario_id: str,
    texto_respuesta: str,
) -> bool:
    """
    Responde un comentario en un post de Instagram.
    Llamado desde meta_leads.py cuando llega un comentario.
    """
    if not META_PAGE_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{META_API_BASE}/{comentario_id}/replies",
                params={"access_token": META_PAGE_TOKEN},
                json={"message": texto_respuesta[:500]},
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"[Content/IG] Error respondiendo comentario: {e}")
        return False


# ── Tarea principal: generar y publicar ─────────────────────────────────────

async def _obtener_imagen_para_post(foco: str) -> bytes | None:
    """
    Intenta obtener una imagen para el post:
    1. Primero busca en la galería de activos.
    2. Si no hay, genera con Gemini/Cloudflare (best-effort).
    Retorna bytes de imagen o None si todo falla.
    """
    # Mapeo de foco → etiquetas de la galería
    etiquetas_map = {
        "piscina":      ["piscinas"],
        "modulo":       ["modulos"],
        "combo":        ["combo"],
        "financiacion": ["financiado"],
        "proceso":      ["obra", "instalacion"],
        "social_proof": ["familia"],
        "lifestyle":    ["exterior", "familia"],
    }
    etiquetas = etiquetas_map.get(foco, ["general"])

    try:
        from tools.asset_library import elegir_imagen_para_contenido, leer_imagen_b64
        import base64
        meta = elegir_imagen_para_contenido(etiquetas)
        if meta:
            resultado = leer_imagen_b64(meta["id"])
            if resultado:
                b64, _ = resultado
                logger.info(f"[Content] Imagen tomada de galería: {meta['nombre']} ({meta['id']})")
                return base64.b64decode(b64)
    except Exception as e:
        logger.warning(f"[Content] No se pudo leer imagen de galería: {e}")

    # Fallback: generar con IA
    try:
        from tools.cloudflare_client import generar_imagen, generar_imagen_gemini
        prompt_map = {
            "piscina":      "piscina de fibra de vidrio argentina, familia en el jardín, agua turquesa",
            "modulo":       "módulo habitable moderno NCE, fachada con jardín, iluminación natural",
            "combo":        "casa modular con piscina de fibra, jardín prolijo, atardecer",
            "financiacion": "familia argentina feliz en casa nueva, sensación de logro",
            "lifestyle":    "verano argentino, jardín, piscina, momentos en familia",
        }
        prompt = prompt_map.get(foco, "producto de calidad para el hogar argentino")
        try:
            img = await generar_imagen(prompt, "flyer")
        except Exception:
            img = await generar_imagen_gemini(prompt, "flyer")
        logger.info("[Content] Imagen generada con IA para el post")
        return img
    except Exception as e:
        logger.warning(f"[Content] No se pudo generar imagen con IA: {e}")
        return None


async def tarea_publicar_contenido_diario() -> None:
    """
    Renata genera y publica el contenido del día.
    Llamado por el scheduler 2 veces por día (10:00 y 19:00).
    Usa galería de activos primero; genera con IA como fallback.
    """
    logger.info("[Content] Iniciando publicación diaria de contenido")

    config    = _tipo_contenido_hoy()
    contenido = await generar_contenido(config)

    if not contenido:
        logger.warning("[Content] No se pudo generar contenido")
        return

    # Obtener imagen (galería → IA → sin imagen)
    imagen_bytes = await _obtener_imagen_para_post(config["foco"])

    if imagen_bytes:
        fb_ok = await publicar_facebook_foto(imagen_bytes, contenido["texto_fb"])
        ig_ok = await publicar_instagram_foto(imagen_bytes, contenido["texto_ig"])
    else:
        # Solo texto como último recurso
        fb_ok = await publicar_facebook(contenido["texto_fb"])
        ig_ok = await publicar_instagram_texto(contenido["texto_ig"])

    logger.info(
        f"[Content] Post publicado — tipo: {contenido['tipo']}, "
        f"foco: {contenido['foco']}, imagen: {'✓' if imagen_bytes else '✗'}, "
        f"FB: {'✓' if fb_ok else '✗'}, IG: {'✓' if ig_ok else '✗'}"
    )

    # Notificar a Renata del resultado para que lo registre
    try:
        from agents.renata import get_agent
        renata = get_agent()
        await renata.respond(
            f"Registrá que publicamos el siguiente contenido hoy "
            f"({contenido['generado']}): tipo={contenido['tipo']}, "
            f"foco={contenido['foco']}, con imagen: {'sí' if imagen_bytes else 'no'}. "
            f"Facebook: {'publicado' if fb_ok else 'error'}. "
            f"Instagram: {'publicado' if ig_ok else 'sin configuración'}."
        )
    except Exception:
        pass


async def tarea_sync_drive() -> None:
    """
    Sync automático diario desde Google Drive → Galería de activos.
    Solo corre si hay credenciales configuradas.
    """
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if not sa_json and not sa_file:
        logger.debug("[DriveSync] Sin credenciales configuradas — sync omitido")
        return
    try:
        from tools.drive_sync import sincronizar_drive
        resultado = await sincronizar_drive()
        if resultado.get("ok"):
            logger.info(
                f"[DriveSync] Sync Drive completo: "
                f"{resultado['nuevas']} nuevas, {resultado['saltadas']} saltadas, "
                f"{resultado['errores']} errores"
            )
        else:
            logger.warning(f"[DriveSync] Sync falló: {resultado.get('error')}")
    except Exception as e:
        logger.warning(f"[DriveSync] Error en sync automático: {e}")
