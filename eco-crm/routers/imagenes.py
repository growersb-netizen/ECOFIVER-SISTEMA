"""
Módulo de generación de imágenes con IA a partir de fotos reales.
Flujo de dos pasos vía OpenRouter:
  1) gpt-4o-mini (visión) → descripción detallada de la foto
  2) gpt-image-1 (generación) → imagen profesional basada en la descripción
"""
import asyncio
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

_OR_BASE = "https://openrouter.ai/api/v1"
_OR_HEADERS_BASE = {
    "HTTP-Referer": "https://eco-crm-production.up.railway.app",
    "X-Title": "EcoFiver CRM Imagenes",
}

# Modelos
_VISION_MODEL   = "openai/gpt-4o-mini"          # describe la foto (visión + texto)
_GEN_MODEL_ENV  = "OPENROUTER_IMAGE_MODEL"       # generación (env o default)
_GEN_MODEL_DEF  = "openai/gpt-image-1"          # default si no hay env


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in
                             ("ADMIN", "COORDINADOR_OPERATIVO", "COMERCIAL"))
    )
    if not ok:
        raise HTTPException(403, "Sin permisos")


def _or_key(db: Session) -> str:
    return get_config_value("openrouter_api_key", db) or os.getenv("OPENROUTER_API_KEY", "")


def _or_headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **_OR_HEADERS_BASE}


# ── Paso 1: describir la foto con visión ──────────────────────────────────────

async def _describir_foto(key: str, foto_b64: str, mime: str, contexto: str) -> tuple[str, str]:
    """
    Usa gpt-4o-mini (visión) para describir la foto en detalle.
    Devuelve (descripcion, error_msg).
    """
    prompt_vision = (
        f"Describí esta fotografía en detalle para usarla como referencia para generar "
        f"una versión mejorada con IA. Incluí: composición, ángulo de toma, iluminación actual, "
        f"colores, objetos visibles, fondo, contexto general. {contexto} "
        f"Sé específico y objetivo. No inventes ni agregues nada que no veas en la imagen. "
        f"Respondé solo con la descripción, sin introducción ni cierre."
    )
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_OR_BASE}/chat/completions",
                headers=_or_headers(key),
                json={
                    "model": _VISION_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{foto_b64}"}},
                            {"type": "text", "text": prompt_vision},
                        ],
                    }],
                },
            )
            if r.status_code != 200:
                return "", f"Visión error {r.status_code}: {r.text[:200]}"
            data = r.json()
            desc = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return desc.strip(), ""
    except Exception as e:
        return "", f"Visión excepción: {e}"


# ── Paso 2: generar imagen desde descripción ──────────────────────────────────

async def _generar_desde_descripcion(
    key: str, descripcion: str, prompt_estilo: str, modo: str
) -> tuple[str, str]:
    """
    Usa el modelo de generación para crear una imagen profesional.
    Devuelve (base64_imagen, error_msg).
    """
    gen_model = os.getenv(_GEN_MODEL_ENV, _GEN_MODEL_DEF)
    aspecto = "cuadrada 1:1" if modo != "story" else "vertical 9:16"
    prompt_final = (
        f"Fotografía real de: {descripcion[:600]}\n\n"
        f"{prompt_estilo}\n\n"
        f"Formato: imagen {aspecto}, alta resolución, estilo fotográfico profesional."
    )
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(
                f"{_OR_BASE}/chat/completions",
                headers=_or_headers(key),
                json={
                    "model": gen_model,
                    "messages": [{"role": "user", "content": prompt_final}],
                    "modalities": ["image", "text"],
                },
            )
            if r.status_code != 200:
                return "", f"Generación error {r.status_code}: {r.text[:200]}"
            data = r.json()
            imagenes = (data.get("choices") or [{}])[0].get("message", {}).get("images") or []
            if not imagenes:
                return "", "El modelo no devolvió imágenes en la respuesta"
            url = imagenes[0].get("image_url", {}).get("url", "")
            b64 = url.split(",", 1)[1] if "," in url else url
            return b64, ""
    except Exception as e:
        return "", f"Generación excepción: {e}"


# ── Prompts de estilo (solo mejoras estéticas + datos reales) ─────────────────

_ESTILO_COMUN = (
    "Empresa EcoFiver — fabricante argentina de piscinas de fibra de vidrio y viviendas modulares. "
    "Estilo visual: moderno, prolijo, aspiracional. "
    "Paleta corporativa: azul y verde. "
)

_ESTILOS = {
    "promo": (
        "Estilo: post profesional para Instagram/Facebook. "
        "Mejoras estéticas: iluminación perfecta, colores más vivos, mayor nitidez, contraste profesional. "
        "Agregar: franja semitransparente en la parte inferior con el texto real '{texto_inferior}', "
        "logo o nombre 'EcoFiver' discreto en esquina. "
        "Sin inventar texto adicional. Sin precios ni medidas que no se indiquen explícitamente. "
        "Imagen limpia, sin excesos gráficos. {comun}"
    ),
    "novedad": (
        "Estilo: post de lanzamiento de producto para redes sociales. "
        "Mejoras estéticas: mejor iluminación, colores nítidos, composición equilibrada. "
        "Agregar: badge 'NUEVO' discreto en una esquina, nombre del producto '{texto_inferior}' si se indica, "
        "branding EcoFiver mínimo. "
        "Sin inventar características ni precios. Imagen prolija y ordenada. {comun}"
    ),
    "entrega": (
        "Estilo: post de obra o entrega completada para redes sociales. "
        "Mejoras estéticas: corrección de color, brillo y contraste, aspecto más profesional. "
        "Agregar: franja semitransparente superior con 'Entrega realizada ✓' o similar, "
        "dato '{texto_inferior}' si se provee, branding EcoFiver mínimo en esquina. "
        "Mantener la autenticidad de la foto real. Sin excesivos adornos. {comun}"
    ),
    "catalogo": (
        "Estilo: imagen de catálogo profesional, limpia y minimalista. "
        "Mejoras estéticas: iluminación perfecta y pareja, colores precisos, máxima nitidez, "
        "fondo claro o neutro, sin distracciones. "
        "Texto mínimo: nombre del producto '{texto_inferior}' en tipografía elegante si se indica, "
        "pequeño logo EcoFiver en esquina. Sin precios, sin excesos gráficos. {comun}"
    ),
    "ml": (
        "Estilo: foto de producto para marketplace (MercadoLibre). Estándares requeridos: "
        "fondo blanco puro o gris muy claro, iluminación de estudio pareja sin sombras duras, "
        "producto perfectamente visible y centrado con la misma composición de la foto original, "
        "colores precisos, máxima nitidez. "
        "SIN texto, SIN marcas de agua, SIN objetos adicionales. "
        "Producto: {texto_inferior}."
    ),
}


def _build_estilo(modo: str, tipo_flyer: str, texto_producto: str) -> str:
    clave = modo if modo == "ml" else tipo_flyer
    plantilla = _ESTILOS.get(clave, _ESTILOS["promo"])
    return plantilla.format(
        texto_inferior=texto_producto or "",
        comun=_ESTILO_COMUN,
    )


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
        "request": request, "user": current_user, "roles": roles,
    })


# ── API: generar imágenes (dos pasos) ────────────────────────────────────────

@router.post("/api/imagenes/generar")
async def generar_imagenes(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Dos pasos: 1) visión describe la foto → 2) generación crea versión mejorada.
    Body: { foto_b64, mime, modo, tipo_flyer, producto_texto, n }
    """
    _auth(x_api_key, current_user)
    d = await request.json()
    foto_b64: str       = d.get("foto_b64", "")
    mime: str           = d.get("mime", "image/jpeg")
    modo: str           = d.get("modo", "flyer")        # "flyer" | "ml"
    tipo_flyer: str     = d.get("tipo_flyer", "promo")
    producto_texto: str = (d.get("producto_texto") or "").strip()
    n: int              = min(max(int(d.get("n") or 1), 1), 4)

    if not foto_b64:
        raise HTTPException(400, "Se requiere foto_b64")

    key = _or_key(db)
    if not key:
        raise HTTPException(503, "No hay clave de OpenRouter configurada en el sistema")

    # Paso 1: describir la foto
    contexto_vision = f"El producto en la imagen es: {producto_texto}." if producto_texto else ""
    descripcion, err_vision = await _describir_foto(key, foto_b64, mime, contexto_vision)
    if not descripcion:
        raise HTTPException(502, f"No se pudo analizar la foto: {err_vision}")

    # Paso 2: generar N variantes
    estilo = _build_estilo(modo, tipo_flyer, producto_texto)
    resultados = []
    errores = []

    for i in range(n):
        b64, err = await _generar_desde_descripcion(key, descripcion, estilo, modo)
        if b64:
            resultados.append(b64)
        else:
            errores.append(f"Imagen {i+1}: {err}")
            log.error(f"[imagenes] Generación {i+1} falló: {err}")
        if i < n - 1:
            await asyncio.sleep(3)

    if not resultados:
        raise HTTPException(502, "No se pudo generar ninguna imagen. Detalles: " + " | ".join(errores))

    return {
        "ok": True,
        "imagenes": resultados,
        "descripcion_ia": descripcion[:300],
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
    """Sube imagen en base64 al endpoint de fotos de ML. Body: { imagen_b64 }"""
    _auth(x_api_key, current_user)
    d = await request.json()
    img_b64: str = d.get("imagen_b64", "")
    if not img_b64:
        raise HTTPException(400, "Se requiere imagen_b64")

    tok = await _ml_valid_token(db)
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
