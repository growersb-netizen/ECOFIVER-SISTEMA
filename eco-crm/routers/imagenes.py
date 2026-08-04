"""
Módulo de generación de imágenes con IA a partir de fotos reales.
Flujo dos pasos: gpt-4o-mini (visión → descripción) + gpt-image-1 (generación).
Cada imagen ML tiene un rol específico. Cada formato Meta tiene sus best-practices.
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

API_KEY   = os.getenv("API_KEY", "eco-crm-api-key-2024")
_OR_BASE  = "https://openrouter.ai/api/v1"
_OR_HDR   = {"HTTP-Referer": "https://eco-crm-production.up.railway.app", "X-Title": "EcoFiver CRM Imagenes"}
_VIS_MDL  = "openai/gpt-4o-mini"
_GEN_MDL  = lambda: os.getenv("OPENROUTER_IMAGE_MODEL", "openai/dall-e-3")


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user)
                             for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COMERCIAL"))
    )
    if not ok:
        raise HTTPException(403, "Sin permisos")


def _key(db):
    return get_config_value("openrouter_api_key", db) or os.getenv("OPENROUTER_API_KEY", "")


def _hdr(key):
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **_OR_HDR}


# ══════════════════════════════════════════════════════════════════════════════
# ROLES DE IMAGEN — MercadoLibre
# Cada posición tiene un propósito específico que ML y los compradores esperan.
# ══════════════════════════════════════════════════════════════════════════════

ML_ROLES = [
    {
        "slug":   "principal",
        "nombre": "Principal",
        "icon":   "⭐",
        "badge":  "La más importante — define el CTR",
        "tip":    "Fondo blanco puro, producto completo centrado. ML la usa en búsquedas y feeds. "
                  "Determina si el comprador hace clic.",
        "prompt": (
            "FOTO PRINCIPAL para publicación en MercadoLibre — la imagen que define el CTR. "
            "Requisitos estrictos del marketplace: fondo BLANCO PURO (#FFFFFF absoluto), "
            "producto completamente visible y perfectamente centrado, ocupando el 75-80 porciento del frame, "
            "iluminación de estudio perfecta y uniforme sin sombras, colores del producto fieles y atractivos, "
            "máxima nitidez, resolución alta. "
            "SIN texto, SIN marcas de agua, SIN bordes decorativos, SIN objetos adicionales. "
            "El producto debe verse impecable, profesional, como catálogo de fabricante."
        ),
    },
    {
        "slug":   "detalle",
        "nombre": "Detalle / Calidad",
        "icon":   "🔍",
        "badge":  "Demuestra la calidad del material",
        "tip":    "Close-up de la textura, el acabado, la calidad constructiva. "
                  "Genera confianza en el comprador que no puede tocar el producto.",
        "prompt": (
            "FOTO DE DETALLE Y CALIDAD para MercadoLibre. Objetivo: generar confianza mostrando la calidad. "
            "Close-up profesional enfocado en la textura del material, el acabado superficial y la calidad de terminación. "
            "Para piscinas de fibra de vidrio: mostrar el brillo tipo espejo, la suavidad y uniformidad de la superficie. "
            "Para módulos y viviendas: mostrar la calidad de las terminaciones, la carpintería, los detalles constructivos. "
            "Iluminación que resalte texturas. Fondo blanco o gris muy claro. "
            "SIN texto. El detalle debe transmitir calidad premium."
        ),
    },
    {
        "slug":   "ambiente",
        "nombre": "Ambiente / Instalado",
        "icon":   "🌿",
        "badge":  "Aspiracional — el comprador se imagina con el producto",
        "tip":    "Foto del producto instalado en un entorno real y atractivo. "
                  "Aumenta el deseo de compra mostrando cómo quedará en casa.",
        "prompt": (
            "FOTO LIFESTYLE / AMBIENTE para MercadoLibre. Objetivo: que el comprador se imagine disfrutando el producto. "
            "Mostrar el producto instalado y en uso en un entorno real aspiracional: jardín cuidado, espacio exterior verde, "
            "luz natural cálida de tarde. Ambiente familiar argentino, prolijo y atractivo. "
            "Para piscinas: familia disfrutando, agua azul brillante, entorno verde. "
            "Para módulos: exterior bien presentado en terreno, integrado con la naturaleza. "
            "Alta calidad fotográfica, colores vibrantes y cálidos. SIN texto. "
            "El objetivo es despertar el deseo y proyección emocional del comprador."
        ),
    },
    {
        "slug":   "alternativo",
        "nombre": "Ángulo alternativo",
        "icon":   "📐",
        "badge":  "Vista complementaria que no muestra la foto principal",
        "tip":    "Ángulo diferente: vista aérea, interior, lateral o detalle que la primera foto no cubre. "
                  "Completa la información visual del producto.",
        "prompt": (
            "ÁNGULO ALTERNATIVO para MercadoLibre. Mostrar el producto desde una perspectiva diferente "
            "a la que generalmente se usa como foto principal, para completar la información visual. "
            "Para piscinas: vista aérea (desde arriba) mostrando la forma y el espacio interior, "
            "o vista desde un extremo mostrando la profundidad. "
            "Para módulos y viviendas: vista del interior del espacio habitable, distribución interior, "
            "o fachada lateral que no se ve en la foto principal. "
            "Fondo blanco o contexto neutro limpio. Iluminación profesional. SIN texto."
        ),
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# FORMATOS META — Facebook e Instagram
# Cada formato tiene dimensiones, zonas seguras y criterios de rendimiento.
# ══════════════════════════════════════════════════════════════════════════════

META_FORMATOS = {
    "feed_cuadrado": {
        "nombre":      "Feed cuadrado",
        "plataforma":  "Instagram & Facebook Feed",
        "dimensiones": "1080×1080 px",
        "aspecto":     "1:1",
        "icon":        "⬛",
        "tip":         "Texto máximo 20% de la imagen para no perder alcance. "
                       "Producto o persona debe dominar el 70% del frame. "
                       "Zona central es la más visible en el feed.",
        "prompt_extra": (
            "Formato 1:1 cuadrado para Feed de Instagram y Facebook. "
            "Criterios de rendimiento Meta: el producto o sujeto principal debe ocupar el 70-75 porciento del frame, "
            "centrado. Texto en la imagen máximo 20 porciento del área (Meta penaliza más texto en el alcance pago). "
            "Composición equilibrada, colores vibrantes que detienen el scroll. "
            "Franja de texto (si incluye) solo en la parte inferior, discreta y legible en móvil."
        ),
    },
    "story_vertical": {
        "nombre":      "Story / Reel",
        "plataforma":  "Instagram Story & Reels",
        "dimensiones": "1080×1920 px",
        "aspecto":     "9:16",
        "icon":        "📱",
        "tip":         "Zonas seguras: dejar los 250px superiores e inferiores libres de elementos importantes "
                       "(los ocupa la UI de Instagram). El producto va al centro del frame.",
        "prompt_extra": (
            "Formato 9:16 vertical para Instagram Stories y Reels. "
            "Zona segura crítica: los 250 píxeles superiores (zona de interfaz de usuario, nombre de cuenta) "
            "y los 250 píxeles inferiores (zona de respuesta y swipe-up) deben estar libres de elementos importantes. "
            "El producto y el mensaje principal van en la zona central (entre 25% y 75% de la altura). "
            "Diseño vertical dinámico, colores llamativos, producto grande y visible. "
            "Si hay texto, centrado en el área segura, tipografía grande y legible en pantalla de teléfono."
        ),
    },
    "feed_horizontal": {
        "nombre":      "Feed horizontal",
        "plataforma":  "Facebook Feed",
        "dimensiones": "1200×628 px",
        "aspecto":     "1.91:1",
        "icon":        "🖥",
        "tip":         "Formato óptimo para anuncios en Facebook Feed y compartir en timeline. "
                       "El producto debe verse bien en la parte izquierda del frame.",
        "prompt_extra": (
            "Formato horizontal 1.91:1 para Facebook Feed y anuncios. "
            "Composición: producto o imagen principal en el tercio izquierdo/central, "
            "texto o información de marca en el tercio derecho (si aplica, discreta). "
            "Alta calidad visual, colores que contrasten con el fondo blanco del feed de Facebook. "
            "Diseño profesional corporativo, no recargado."
        ),
    },
    "carrusel": {
        "nombre":      "Carrusel",
        "plataforma":  "Instagram & Facebook Carrusel",
        "dimensiones": "1080×1080 px c/u",
        "aspecto":     "1:1",
        "icon":        "🎠",
        "tip":         "La primera imagen es la más importante (hook). Estilo visual consistente entre slides. "
                       "Esta foto se genera como primera imagen del carrusel.",
        "prompt_extra": (
            "Primera imagen de un carrusel para Instagram y Facebook. "
            "Esta imagen es el 'hook': debe ser la más llamativa de toda la secuencia para que el usuario "
            "deslice y vea las siguientes. "
            "Composición: producto con mayor impacto visual posible, colores vibrantes, fondo que contraste. "
            "Puede incluir un pequeño indicador visual de que hay más imágenes ('Deslizá ▶'). "
            "Estilo que sea replicable consistentemente en las demás fotos del carrusel."
        ),
    },
}

# Tipos de flyer para Meta con best practices específicas
META_TIPOS = {
    "promo": {
        "nombre": "Promo / Descuento",
        "prompt": (
            "Post promocional para redes sociales EcoFiver. "
            "Mejoras estéticas sobre la foto original: iluminación mejorada, colores más vibrantes, nitidez aumentada. "
            "Agregar (con datos REALES provistos, nada inventado): badge de precio o descuento '{texto}' "
            "en el área permitida, franja semitransparente inferior con nombre del producto, "
            "branding EcoFiver discreto en esquina. "
            "Texto máximo 20% del frame. Sin inventar precios ni características. Estilo prolijo."
        ),
    },
    "novedad": {
        "nombre": "Nuevo Producto",
        "prompt": (
            "Post de lanzamiento de producto nuevo para redes sociales EcoFiver. "
            "Mejoras estéticas: iluminación de estudio, colores precisos y vivos. "
            "Agregar: badge 'NUEVO' en esquina superior, nombre del producto '{texto}' si se indica, "
            "branding EcoFiver mínimo. Sin precios ni medidas inventadas. Composición limpia."
        ),
    },
    "entrega": {
        "nombre": "Entrega / Instalación",
        "prompt": (
            "Post de entrega o instalación completada para redes sociales EcoFiver. "
            "Mantener la autenticidad de la foto real — eso es lo que genera confianza en redes. "
            "Mejoras estéticas: corrección de color, brillo, contraste. "
            "Agregar: franja superior oscura con 'Entrega realizada ✓', dato '{texto}' si se provee, "
            "branding EcoFiver en esquina. Imagen auténtica, sin excesos gráficos."
        ),
    },
    "catalogo": {
        "nombre": "Catálogo",
        "prompt": (
            "Imagen de catálogo profesional y minimalista para redes sociales EcoFiver. "
            "Mejoras estéticas: iluminación perfecta, fondo claro o neutro, máxima nitidez. "
            "Solo agregar: nombre del producto '{texto}' en tipografía elegante y discreta, "
            "pequeño logo EcoFiver en esquina. Sin precios, sin efectos gráficos recargados."
        ),
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE GENERACIÓN
# ══════════════════════════════════════════════════════════════════════════════

async def _describir_foto(key: str, foto_b64: str, mime: str, contexto: str) -> tuple[str, str]:
    prompt = (
        f"Describí esta fotografía en detalle para usarla como referencia de generación con IA. "
        f"Incluí: composición, ángulo, iluminación, colores, objetos principales, fondo, ambiente. "
        f"{contexto} Respondé solo con la descripción objetiva, sin introducción ni cierre. "
        f"No inventes nada que no veas en la imagen."
    )
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_OR_BASE}/chat/completions",
                headers=_hdr(key),
                json={
                    "model": _VIS_MDL,
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{foto_b64}"}},
                        {"type": "text", "text": prompt},
                    ]}],
                },
            )
            if r.status_code != 200:
                return "", f"Visión {r.status_code}: {r.text[:200]}"
            data = r.json()
            desc = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return desc.strip(), ""
    except Exception as e:
        return "", f"Visión excepción: {e}"


async def _generar_imagen(key: str, descripcion: str, prompt_rol: str, formato_extra: str = "") -> tuple[str, str]:
    import base64 as _b64lib

    # Tamaño según formato: DALL-E 3 soporta 1024x1024, 1024x1792, 1792x1024
    if "9:16" in formato_extra:
        size = "1024x1792"
    elif "1.91:1" in formato_extra:
        size = "1792x1024"
    else:
        size = "1024x1024"

    prompt_final = (
        f"Referencia visual: {descripcion[:400]}\n\n"
        f"{prompt_rol}\n\n"
        f"{formato_extra}"
    ).strip()[:4000]   # DALL-E 3 acepta hasta 4000 chars

    try:
        async with httpx.AsyncClient(timeout=90) as c:
            # OpenRouter: generación de imágenes usa /images/generations, no /chat/completions
            r = await c.post(
                f"{_OR_BASE}/images/generations",
                headers=_hdr(key),
                json={
                    "model": _GEN_MDL(),
                    "prompt": prompt_final,
                    "n": 1,
                    "size": size,
                    "response_format": "b64_json",
                    "quality": "standard",
                },
            )
            if r.status_code != 200:
                return "", f"Generación {r.status_code}: {r.text[:300]}"
            data = r.json()
            imgs = data.get("data") or []
            if not imgs:
                return "", "El modelo no devolvió imágenes"
            b64 = imgs[0].get("b64_json") or ""
            if not b64:
                # Fallback: algunos modelos devuelven URL en vez de b64
                url = imgs[0].get("url", "")
                if url:
                    dl = await c.get(url, timeout=30)
                    if dl.status_code == 200:
                        b64 = _b64lib.b64encode(dl.content).decode()
            if not b64:
                return "", "El modelo no devolvió imagen en formato válido"
            return b64, ""
    except Exception as e:
        return "", f"Generación excepción: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/imagenes", response_class=HTMLResponse)
async def imagenes_page(request: Request, current_user: Usuario = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ("ADMIN", "COORDINADOR_OPERATIVO", "COMERCIAL")):
        raise HTTPException(403, "Sin acceso")
    return templates.TemplateResponse("imagenes.html", {
        "request": request, "user": current_user, "roles": roles,
        "ml_roles": ML_ROLES,
        "meta_formatos": META_FORMATOS,
        "meta_tipos": META_TIPOS,
    })


@router.get("/api/imagenes/config")
async def config_imagenes(x_api_key: Optional[str] = Header(None),
                          current_user: Optional[Usuario] = Depends(get_current_user)):
    """Devuelve roles ML y formatos Meta para que el frontend los use."""
    _auth(x_api_key, current_user)
    return {"ml_roles": ML_ROLES, "meta_formatos": META_FORMATOS, "meta_tipos": META_TIPOS}


@router.post("/api/imagenes/generar-ml")
async def generar_ml(request: Request, db: Session = Depends(get_db),
                     x_api_key: Optional[str] = Header(None),
                     current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Genera imágenes para ML. Cada una con el rol específico según su posición.
    Body: { foto_b64, mime, producto_texto, roles: ['principal','detalle',...] }
    """
    _auth(x_api_key, current_user)
    d = await request.json()
    foto_b64: str      = d.get("foto_b64", "")
    mime: str          = d.get("mime", "image/jpeg")
    producto: str      = (d.get("producto_texto") or "").strip()
    roles_sel: list    = d.get("roles") or [r["slug"] for r in ML_ROLES[:int(d.get("n", 1))]]

    if not foto_b64:
        raise HTTPException(400, "Se requiere foto_b64")

    key = _key(db)
    if not key:
        raise HTTPException(503, "No hay clave de OpenRouter configurada")

    contexto = f"El producto es: {producto}." if producto else ""
    descripcion, err_vis = await _describir_foto(key, foto_b64, mime, contexto)
    if not descripcion:
        raise HTTPException(502, f"No se pudo analizar la foto: {err_vis}")

    roles_map = {r["slug"]: r for r in ML_ROLES}
    resultados = []
    for i, slug in enumerate(roles_sel):
        rol = roles_map.get(slug)
        if not rol:
            continue
        prompt_rol = rol["prompt"] + (f" Producto: {producto}." if producto else "")
        b64, err = await _generar_imagen(key, descripcion, prompt_rol)
        resultados.append({
            "slug": slug,
            "nombre": rol["nombre"],
            "icon": rol["icon"],
            "badge": rol["badge"],
            "imagen": b64,
            "error": err if not b64 else "",
        })
        if i < len(roles_sel) - 1:
            await asyncio.sleep(3)

    exitosas = sum(1 for r in resultados if r["imagen"])
    if not exitosas:
        errores = [r["error"] for r in resultados if r["error"]]
        raise HTTPException(502, "No se pudo generar ninguna imagen. " + " | ".join(errores))

    return {"ok": True, "descripcion_ia": descripcion[:300], "imagenes": resultados}


@router.post("/api/imagenes/generar-meta")
async def generar_meta(request: Request, db: Session = Depends(get_db),
                       x_api_key: Optional[str] = Header(None),
                       current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Genera imagen para Meta (Facebook/Instagram) con el formato y tipo indicados.
    Body: { foto_b64, mime, formato, tipo_flyer, producto_texto }
    """
    _auth(x_api_key, current_user)
    d = await request.json()
    foto_b64: str   = d.get("foto_b64", "")
    mime: str       = d.get("mime", "image/jpeg")
    formato_slug    = d.get("formato", "feed_cuadrado")
    tipo_slug       = d.get("tipo_flyer", "promo")
    producto: str   = (d.get("producto_texto") or "").strip()

    if not foto_b64:
        raise HTTPException(400, "Se requiere foto_b64")

    key = _key(db)
    if not key:
        raise HTTPException(503, "No hay clave de OpenRouter configurada")

    fmt  = META_FORMATOS.get(formato_slug, META_FORMATOS["feed_cuadrado"])
    tipo = META_TIPOS.get(tipo_slug, META_TIPOS["promo"])

    contexto = f"El producto es: {producto}." if producto else ""
    descripcion, err_vis = await _describir_foto(key, foto_b64, mime, contexto)
    if not descripcion:
        raise HTTPException(502, f"No se pudo analizar la foto: {err_vis}")

    prompt_tipo = tipo["prompt"].replace("{texto}", producto or "EcoFiver")
    prompt_rol  = (
        f"Empresa EcoFiver — fabricante argentina de piscinas de fibra de vidrio y viviendas modulares. "
        f"Paleta corporativa: azul y verde. Estilo moderno, prolijo, aspiracional.\n\n"
        f"Tipo de contenido: {tipo['nombre']}. {prompt_tipo}\n\n"
        f"Plataforma destino: {fmt['plataforma']} ({fmt['dimensiones']}). {fmt['prompt_extra']}"
    )

    b64, err = await _generar_imagen(key, descripcion, prompt_rol,
                                     formato_extra=fmt["prompt_extra"])
    if not b64:
        raise HTTPException(502, f"No se pudo generar la imagen: {err}")

    return {
        "ok": True,
        "imagen": b64,
        "formato": fmt["nombre"],
        "tipo": tipo["nombre"],
        "plataforma": fmt["plataforma"],
        "dimensiones": fmt["dimensiones"],
        "descripcion_ia": descripcion[:300],
    }


@router.post("/api/imagenes/subir-a-ml")
async def subir_imagen_ml(request: Request, db: Session = Depends(get_db),
                           x_api_key: Optional[str] = Header(None),
                           current_user: Optional[Usuario] = Depends(get_current_user)):
    """Sube imagen base64 al endpoint de fotos de ML."""
    _auth(x_api_key, current_user)
    d = await request.json()
    img_b64: str = d.get("imagen_b64", "")
    if not img_b64:
        raise HTTPException(400, "Se requiere imagen_b64")

    tok = await _ml_valid_token(db)
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{ML_BASE}/pictures", headers=_ml_headers(tok),
                             json={"source": f"data:image/png;base64,{img_b64}"})
            if r.status_code not in (200, 201):
                return {"ok": False, "error": f"ML {r.status_code}: {r.text[:200]}"}
            pic = r.json()
            return {"ok": True, "id": pic.get("id"), "url": pic.get("secure_url") or pic.get("url")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
