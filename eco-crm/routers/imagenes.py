"""
Módulo de generación de imágenes con IA a partir de fotos reales.
- Flyers para redes sociales (promo, novedad, entrega, catálogo)
- Imágenes de producto para MercadoLibre (fondo limpio, formato permitido)
Usa OpenRouter con gpt-image-1 (vision input + image output).
"""
import base64
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import get_config_value
from routers.mercadolibre import _ml_valid_token, _ml_headers, ML_BASE

router = APIRouter()
templates = Jinja2Templates(directory="templates")
log = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COMERCIAL"))
    )
    if not ok:
        raise HTTPException(403, "Sin permisos")


# ── Prompts por tipo ─────────────────────────────────────────────────────────

_BASE_BRAND = (
    "Empresa argentina EcoFiver, fabricante de piscinas de fibra de vidrio y viviendas modulares, "
    "Zárate, Buenos Aires. Colores corporativos: azul y verde. Estilo moderno y aspiracional."
)

_PROMPTS_FLYER = {
    "promo": (
        "Tomá esta fotografía de producto y generá un flyer publicitario profesional manteniendo exactamente "
        "la misma composición, ángulo y estructura de la imagen original. "
        "Mejoras estéticas: iluminación perfecta, colores más vibrantes y saturados, nitidez aumentada, "
        "contraste profesional. "
        "Agregá overlays comerciales en full color: badge con precio '{precio}' en tipografía bold, "
        "texto '{producto}' en banner inferior, franja de color semitransparente con '¡OFERTA!' en la parte superior, "
        "logo/texto 'EcoFiver' en esquina inferior derecha, "
        "fondo con gradiente sutil que no tape el producto. "
        "Estilo: publicidad profesional argentina, 4K, formato cuadrado 1:1 listo para Instagram y Facebook. "
        "{base}"
    ),
    "novedad": (
        "Tomá esta fotografía y generá un flyer de lanzamiento de nuevo producto manteniendo la misma "
        "composición y estructura de la imagen. "
        "Mejoras estéticas: iluminación de estudio, colores nítidos y vibrantes, alta resolución. "
        "Agregá: badge 'NUEVO' en esquina superior izquierda (color llamativo), "
        "nombre del producto '{producto}' en tipografía moderna, "
        "frase 'Disponible ahora' o similar, branding EcoFiver. "
        "Estilo: lanzamiento corporativo moderno, 4K, formato cuadrado 1:1. "
        "{base}"
    ),
    "entrega": (
        "Tomá esta fotografía de entrega o instalación real y convertila en un post profesional para redes "
        "manteniendo la misma composición de la foto (la foto real es el corazón del contenido). "
        "Mejoras estéticas: corrección de color, brillo, contraste, nitidez. "
        "Agregá overlays: header 'ENTREGA REALIZADA ✓' en banner superior, "
        "detalle '{producto}', branding EcoFiver en esquina, "
        "badge de satisfacción del cliente o estrella, "
        "franja inferior semitransparente con texto informativo. "
        "Estilo: post de obra completada, profesional, cálido, 4K, formato cuadrado 1:1. "
        "{base}"
    ),
    "catalogo": (
        "Tomá esta fotografía de producto y generá una imagen de catálogo profesional manteniendo "
        "exactamente la misma composición y ángulo. "
        "Mejoras estéticas: iluminación perfecta uniforme, colores precisos, fondo limpio y claro, "
        "máxima nitidez, sin sombras duras. "
        "Agregá solo: nombre del producto '{producto}' en tipografía elegante y discreta, "
        "logo EcoFiver en esquina (pequeño, sin interferir). "
        "Estilo: fotografía de producto de alta gama, minimalista, 4K, formato cuadrado 1:1. "
        "{base}"
    ),
}

_PROMPT_ML = (
    "Tomá esta fotografía de producto y generá una imagen profesional para publicación en MercadoLibre "
    "manteniendo exactamente la misma composición, ángulo y elementos del producto. "
    "NO cambies la estructura ni el ángulo de la toma. "
    "Mejoras requeridas: fondo blanco puro o gris muy claro uniforme, "
    "iluminación de estudio perfecta y pareja sin sombras duras, "
    "colores del producto precisos y vibrantes, máxima nitidez y resolución 4K, "
    "sin texto, sin marcas de agua, sin objetos adicionales. "
    "El producto debe verse perfectamente centrado o con la misma composición original. "
    "Cumple estándares de marketplace: fondo blanco, producto visible, alta calidad. "
    "Producto: {producto}."
)


def _build_prompt(modo: str, tipo_flyer: str, producto: str, precio: str) -> str:
    if modo == "ml":
        return _PROMPT_ML.format(producto=producto or "producto")
    plantilla = _PROMPTS_FLYER.get(tipo_flyer, _PROMPTS_FLYER["promo"])
    return plantilla.format(
        producto=producto or "producto",
        precio=precio or "",
        base=_BASE_BRAND,
    )


# ── Generación con OpenRouter (image input + image output) ───────────────────

async def _generar_desde_foto(
    db: Session,
    foto_b64: str,
    prompt: str,
    modo: str = "flyer",
    mime: str = "image/jpeg",
) -> Optional[str]:
    """
    Envía la foto original + prompt a OpenRouter gpt-image-1.
    Retorna base64 de la imagen generada, o None si falla.
    """
    or_key = get_config_value("openrouter_api_key", db) or os.getenv("OPENROUTER_API_KEY", "")
    if not or_key:
        log.error("[imagenes] No hay OPENROUTER_API_KEY configurada")
        return None

    model = os.getenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1")
    aspecto = "cuadrada 1:1 estilo publicación de Instagram" if modo != "story" else "vertical 9:16"

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{foto_b64}"},
                },
                {
                    "type": "text",
                    "text": f"{prompt} Formato final: imagen {aspecto}, 4K, alta calidad profesional.",
                },
            ],
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://eco-crm-production.up.railway.app",
                    "X-Title": "EcoFiver CRM Imagenes",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "modalities": ["image", "text"],
                },
            )
            if r.status_code != 200:
                log.error(f"[imagenes] OpenRouter error {r.status_code}: {r.text[:300]}")
                return None
            data = r.json()
            imagenes = (data.get("choices") or [{}])[0].get("message", {}).get("images") or []
            if not imagenes:
                log.warning("[imagenes] OpenRouter no devolvió imágenes")
                return None
            data_url = imagenes[0].get("image_url", {}).get("url", "")
            if "," in data_url:
                return data_url.split(",", 1)[1]
            return data_url or None
    except Exception as e:
        log.error(f"[imagenes] Error generando con OpenRouter: {e}")
        return None


# ── Página ────────────────────────────────────────────────────────────────────

@router.get("/imagenes", response_class=HTMLResponse)
async def imagenes_page(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COMERCIAL")):
        raise HTTPException(403, "Sin acceso")
    return templates.TemplateResponse("imagenes.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


# ── API: generar imágenes ─────────────────────────────────────────────────────

@router.post("/api/imagenes/generar")
async def generar_imagenes(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Recibe foto en base64 + parámetros → genera imagen(es) mejorada(s) con IA.
    Body: { foto_b64, mime, modo, tipo_flyer, producto, precio, n }
    """
    _auth(x_api_key, current_user)
    d = await request.json()
    foto_b64: str = d.get("foto_b64", "")
    mime: str = d.get("mime", "image/jpeg")
    modo: str = d.get("modo", "flyer")      # "flyer" | "ml"
    tipo_flyer: str = d.get("tipo_flyer", "promo")
    producto: str = (d.get("producto") or "").strip()
    precio: str = (d.get("precio") or "").strip()
    n: int = min(int(d.get("n") or 1), 4)

    if not foto_b64:
        raise HTTPException(400, "Se requiere foto_b64")

    prompt = _build_prompt(modo, tipo_flyer, producto, precio)
    resultados = []
    errores = []

    for i in range(n):
        b64 = await _generar_desde_foto(db, foto_b64, prompt, modo=modo, mime=mime)
        if b64:
            resultados.append(b64)
        else:
            errores.append(f"Imagen {i+1}: falló la generación")
        # Pequeña pausa entre llamadas para no saturar la API
        if i < n - 1:
            import asyncio
            await asyncio.sleep(2)

    if not resultados:
        raise HTTPException(500, "No se pudo generar ninguna imagen. " + "; ".join(errores))

    return {
        "ok": True,
        "imagenes": resultados,   # list of base64 strings (PNG)
        "prompt_usado": prompt[:200],
        "errores": errores,
    }


# ── API: subir imagen a ML ────────────────────────────────────────────────────

@router.post("/api/imagenes/subir-a-ml")
async def subir_imagen_ml(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Sube una imagen en base64 al endpoint de fotos de ML.
    Body: { imagen_b64 }   →  { ok, url, id }
    """
    _auth(x_api_key, current_user)
    d = await request.json()
    img_b64: str = d.get("imagen_b64", "")
    if not img_b64:
        raise HTTPException(400, "Se requiere imagen_b64")

    tok = await _ml_valid_token(db)

    # ML acepta imágenes como source URL o como upload multipart.
    # Usamos el endpoint de pictures que acepta base64 como data URI.
    data_uri = f"data:image/png;base64,{img_b64}"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{ML_BASE}/pictures",
                headers=_ml_headers(tok),
                json={"source": data_uri},
            )
            if r.status_code not in (200, 201):
                return {"ok": False, "error": f"ML {r.status_code}: {r.text[:200]}"}
            pic = r.json()
            return {"ok": True, "id": pic.get("id"), "url": pic.get("secure_url") or pic.get("url")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
