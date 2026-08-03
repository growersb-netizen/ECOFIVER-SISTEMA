"""
Módulo 14 — Ecopost
Gestión de contenido para redes sociales: copy + imagen con IA, flujo de aprobación.
Acceso: ADMIN y COORDINADOR_OPERATIVO
"""
import json
import base64
import logging
from datetime import datetime
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ContenidoEcopost, EcopostReferencia, Usuario, MetaPagina
from routers.auth import require_auth, get_user_roles
from routers.configuracion import get_config_value
from utils.ai_client import ai_complete, get_active_provider

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

CLOUDFLARE_WORKER_URL = "https://eco-agentes.growersb.workers.dev"
GEMINI_TEXT_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict"


# ─── AUTH HELPER ─────────────────────────────────────────────────────────────

def _require_access(user: Usuario = Depends(require_auth)) -> Usuario:
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin permisos para Ecopost")
    return user


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class GenerarCopyReq(BaseModel):
    producto: str
    modelo: Optional[str] = ""
    tipo: Optional[str] = "flyer"       # flyer | story | carrusel | reel
    tono: Optional[str] = "profesional y cercano"
    descripcion_extra: Optional[str] = ""


class GenerarImagenReq(BaseModel):
    prompt: str
    tipo: Optional[str] = "flyer"       # flyer (1:1) | story (9:16)


class GuardarContenidoReq(BaseModel):
    titulo: Optional[str] = ""
    tipo: Optional[str] = "flyer"
    producto: Optional[str] = None
    modelo_especifico: Optional[str] = None
    copy_texto: Optional[str] = ""
    copy_hashtags: Optional[str] = ""
    imagen_prompt: Optional[str] = ""
    imagen_base64: Optional[str] = None
    imagen_url: Optional[str] = None
    notas: Optional[str] = ""


class CambiarEstadoReq(BaseModel):
    estado: str     # borrador | aprobado | publicado | archivado


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _content_dict(c: ContenidoEcopost) -> dict:
    return {
        "id": c.id,
        "titulo": c.titulo,
        "tipo": c.tipo,
        "producto": c.producto,
        "modelo_especifico": c.modelo_especifico,
        "copy_texto": c.copy_texto,
        "copy_hashtags": c.copy_hashtags,
        "imagen_prompt": c.imagen_prompt,
        "imagen_url": c.imagen_url,
        "tiene_imagen": bool(c.imagen_base64 or c.imagen_url),
        "estado": c.estado,
        "notas": c.notas,
        "creado_por": c.creado_por.nombre if c.creado_por else None,
        "aprobado_por": c.aprobado_por.nombre if c.aprobado_por else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def _gemini_text(api_key: str, prompt: str) -> str:
    """Llama a Gemini Flash para generar texto."""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 1024},
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{GEMINI_TEXT_URL}?key={api_key}", json=body)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _generate_image_worker(prompt: str, tipo: str) -> Optional[str]:
    """
    Intenta generar imagen via Cloudflare Worker /generate (nuevo).
    Devuelve base64 string o None si falla.
    """
    width, height = (1080, 1080) if tipo != "story" else (1080, 1920)
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{CLOUDFLARE_WORKER_URL}/generate",
                json={"prompt": prompt, "width": width, "height": height},
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    return data.get("image_base64")
    except Exception as e:
        logger.warning(f"[ecopost] Worker /generate falló: {e}")
    return None


async def _generate_image_gemini(api_key: str, prompt: str, tipo: str) -> Optional[str]:
    """
    Genera imagen directamente via Gemini Imagen 3 (fallback cuando el worker no responde).
    """
    aspect = "1:1" if tipo != "story" else "9:16"
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect, "language": "es"},
    }
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{GEMINI_IMAGEN_URL}?key={api_key}", json=body)
            r.raise_for_status()
            data = r.json()
            b64 = data["predictions"][0].get("bytesBase64Encoded")
            return b64
    except Exception as e:
        logger.error(f"[ecopost] Gemini Imagen directo falló: {e}")
        return None


async def _generate_image_openrouter(api_key: str, prompt: str, tipo: str) -> Optional[str]:
    """
    Genera imagen vía OpenRouter (modelo de imagen de OpenAI) — mismo motor que
    usa el módulo Ecopost del agente Renata en eco-multiagente.
    """
    import os
    model = os.getenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-5-image-mini")
    aspecto = "cuadrada 1:1 estilo publicación de Instagram" if tipo != "story" else "vertical 9:16 estilo Instagram Story"
    prompt_final = f"{prompt}. Formato de imagen {aspecto}, alta calidad, fotografía profesional."
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt_final}],
                    "modalities": ["image", "text"],
                },
            )
            r.raise_for_status()
            data = r.json()
            imagenes = data["choices"][0]["message"].get("images") or []
            if not imagenes:
                return None
            data_url = imagenes[0]["image_url"]["url"]  # "data:image/png;base64,...."
            return data_url.split(",", 1)[1] if "," in data_url else None
    except Exception as e:
        logger.error(f"[ecopost] OpenRouter generar_imagen falló: {e}")
        return None


_ECOFIVER_IMG_CTX = (
    "Imagen publicitaria profesional para EcoFiver, empresa argentina fabricante de piscinas de fibra "
    "de vidrio y viviendas modulares wood frame, ubicada en Zárate, Buenos Aires. "
    "Estilo fotográfico moderno y aspiracional, colores vibrantes, alta resolución, "
    "ambiente familiar argentino, entorno al aire libre soleado. "
)


def _enriquecer_prompt_imagen(prompt: str, tipo: str) -> str:
    """Agrega contexto de marca EcoFiver al prompt para evitar imágenes genéricas o incorrectas."""
    formato = (
        "Composición cuadrada 1:1, estilo publicación de Instagram."
        if tipo != "story"
        else "Composición vertical 9:16, estilo Instagram Story."
    )
    return f"{_ECOFIVER_IMG_CTX}{prompt}. {formato}"


async def _generate_image(db: Session, prompt: str, tipo: str) -> Optional[str]:
    """Intenta OpenRouter primero (motor configurado por defecto), con fallbacks legacy."""
    import os
    or_key = get_config_value("openrouter_api_key", db) or os.getenv("OPENROUTER_API_KEY", "")
    if or_key:
        b64 = await _generate_image_openrouter(or_key, prompt, tipo)
        if b64:
            return b64
    b64 = await _generate_image_worker(prompt, tipo)
    if b64:
        return b64
    gemini_key = get_config_value("gemini_api_key", db)
    if gemini_key:
        b64 = await _generate_image_gemini(gemini_key, prompt, tipo)
    return b64


# ─── HTML PAGE ───────────────────────────────────────────────────────────────

@router.get("/ecopost", response_class=HTMLResponse)
async def ecopost_page(
    request: Request,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(user)
    return templates.TemplateResponse("ecopost.html", {
        "request": request,
        "user": user,
        "roles": roles,
    })


# ─── API LIST ────────────────────────────────────────────────────────────────

@router.get("/api/ecopost")
async def api_list(
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    limit: int = 50,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    q = db.query(ContenidoEcopost)
    if estado:
        q = q.filter(ContenidoEcopost.estado == estado)
    if producto:
        q = q.filter(ContenidoEcopost.producto == producto)
    items = q.order_by(ContenidoEcopost.created_at.desc()).limit(limit).all()
    return [_content_dict(c) for c in items]


@router.get("/api/ecopost/calendario")
async def api_calendario(
    year: Optional[int] = None,
    month: Optional[int] = None,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Devuelve el contenido agrupado por día para el calendario."""
    from calendar import monthrange
    now = datetime.now()
    y = year  or now.year
    m = month or now.month

    primer_dia = datetime(y, m, 1)
    ultimo_dia = datetime(y, m, monthrange(y, m)[1], 23, 59, 59)

    items = (
        db.query(ContenidoEcopost)
        .filter(
            ContenidoEcopost.created_at >= primer_dia,
            ContenidoEcopost.created_at <= ultimo_dia,
        )
        .order_by(ContenidoEcopost.created_at)
        .all()
    )

    por_dia: dict = {}
    for it in items:
        if it.created_at:
            dia_key = str(it.created_at.day)
            if dia_key not in por_dia:
                por_dia[dia_key] = []
            por_dia[dia_key].append({
                "id": it.id,
                "titulo": it.titulo or "(sin título)",
                "tipo": it.tipo,
                "producto": it.producto or "",
                "estado": it.estado,
                "tiene_imagen": bool(it.imagen_base64 or it.imagen_url),
            })

    return {
        "year": y,
        "month": m,
        "dias_en_mes": monthrange(y, m)[1],
        "primer_dia_semana": primer_dia.weekday(),   # 0=lunes
        "por_dia": por_dia,
        "total": len(items),
    }


@router.get("/api/ecopost/{item_id}")
async def api_get(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")
    result = _content_dict(c)
    result["imagen_base64"] = c.imagen_base64  # incluye base64 completo solo en detail
    return result


@router.get("/api/ecopost/{item_id}/imagen")
async def api_imagen(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Sirve la imagen PNG generada directamente."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c or not c.imagen_base64:
        raise HTTPException(404, "Sin imagen")
    try:
        img_bytes = base64.b64decode(c.imagen_base64)
        return Response(content=img_bytes, media_type="image/png")
    except Exception:
        raise HTTPException(500, "Error decodificando imagen")


# ─── API GENERAR COPY ────────────────────────────────────────────────────────

@router.post("/api/ecopost/generar-copy")
async def api_generar_copy(
    body: GenerarCopyReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    # Intentar via worker primero
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{CLOUDFLARE_WORKER_URL}/generar-copy",
                json={
                    "producto": body.producto,
                    "modelo": body.modelo,
                    "descripcion": body.descripcion_extra,
                    "tono": body.tono,
                },
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    return {"ok": True, "copy": data["copy"]}
    except Exception as e:
        logger.warning(f"[ecopost] Worker /generar-copy falló: {e}")

    # Fallback: IA unificada (Grok → Gemini → Claude según lo configurado)
    pname, api_key = get_active_provider(db)
    if not api_key:
        raise HTTPException(400, "No hay API key de IA configurada. Configurar en Ajustes → API Keys (Grok, Gemini o Claude).")

    tipos_desc = {
        "flyer": "imagen cuadrada 1080x1080",
        "story": "story vertical 9:16",
        "carrusel": "carrusel de fotos",
        "reel": "video reel",
    }
    tipo_str = tipos_desc.get(body.tipo, body.tipo)

    prompt = f"""Sos copywriter experto en marketing de EcoFiver, empresa argentina de Zárate, Buenos Aires.

CONTEXTO DE LA EMPRESA:
- Fabrica piscinas de fibra de vidrio llave en mano (fabricación + transporte + instalación incluida)
- Módulos habitacionales y viviendas modulares wood frame
- Accesorios: reposeras de fibra, quinchos prefabricados, cuchas para perro, iluminación para piscinas
- Hidromasajes y jacuzzis también disponibles
- Diferencial: fábrica propia, instalación incluida, financiación propia en cuotas

Escribís siempre en castellano de Argentina. Tono cálido, cercano y profesional: hablás de vos a vos, generás confianza sin ser informal ni usar lunfardo.
Escribí copy para redes sociales (formato {tipo_str}):
- Producto: {body.producto}
- Modelo / variante: {body.modelo or 'genérico'}
- Info adicional: {body.descripcion_extra or 'ninguna'}
- Tono pedido: {body.tono}

Respondé SOLO con este formato exacto, sin texto adicional:
TITULO: [título llamativo, max 10 palabras, en castellano argentino]
COPY: [2-3 oraciones para Instagram/Facebook con emojis, mencionar beneficio clave y CTA]
HASHTAGS: [6-10 hashtags separados por espacio, mezclar genéricos y específicos]"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=1024, temperature=0.85)
        # Parsear la respuesta
        titulo = ""
        copy = respuesta
        hashtags = ""
        for line in respuesta.split("\n"):
            line = line.strip()
            if line.startswith("TITULO:"):
                titulo = line[7:].strip()
            elif line.startswith("COPY:"):
                copy = line[5:].strip()
            elif line.startswith("HASHTAGS:"):
                hashtags = line[9:].strip()

        return {"ok": True, "copy": f"{titulo}\n\n{copy}", "hashtags": hashtags}
    except Exception as e:
        raise HTTPException(502, f"Error generando copy: {str(e)}")


# ─── API GENERAR IMAGEN ──────────────────────────────────────────────────────

@router.post("/api/ecopost/generar-imagen")
async def api_generar_imagen(
    body: GenerarImagenReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    prompt_final = _enriquecer_prompt_imagen(body.prompt, body.tipo)
    b64 = await _generate_image(db, prompt_final, body.tipo)
    if not b64:
        raise HTTPException(502, "No se pudo generar la imagen. Verificá que haya una API key de OpenRouter configurada en Configuración → API Keys.")

    return {"ok": True, "image_base64": b64, "mime_type": "image/png"}


# ─── API GUARDAR ─────────────────────────────────────────────────────────────

@router.post("/api/ecopost")
async def api_crear(
    body: GuardarContenidoReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    c = ContenidoEcopost(
        titulo=body.titulo,
        tipo=body.tipo,
        producto=body.producto,
        modelo_especifico=body.modelo_especifico,
        copy_texto=body.copy_texto,
        copy_hashtags=body.copy_hashtags,
        imagen_prompt=body.imagen_prompt,
        imagen_base64=body.imagen_base64,
        imagen_url=body.imagen_url,
        notas=body.notas,
        estado="borrador",
        creado_por_id=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"ok": True, "id": c.id, "item": _content_dict(c)}


@router.put("/api/ecopost/{item_id}")
async def api_actualizar(
    item_id: int,
    body: GuardarContenidoReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    for field, val in body.dict(exclude_none=True).items():
        setattr(c, field, val)

    db.commit()
    db.refresh(c)
    return {"ok": True, "item": _content_dict(c)}


# ─── API CAMBIAR ESTADO ──────────────────────────────────────────────────────

@router.patch("/api/ecopost/{item_id}/estado")
async def api_cambiar_estado(
    item_id: int,
    body: CambiarEstadoReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    estados_validos = {"borrador", "aprobado", "publicado", "archivado"}
    if body.estado not in estados_validos:
        raise HTTPException(400, f"Estado inválido. Válidos: {estados_validos}")

    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    c.estado = body.estado
    if body.estado == "aprobado" and not c.aprobado_por_id:
        c.aprobado_por_id = user.id

    db.commit()
    return {"ok": True, "estado": c.estado}


# ─── API ELIMINAR ─────────────────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/subir-r2")
async def subir_imagen_r2(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Sube la imagen base64 del contenido a R2 (Cloudflare) y actualiza imagen_url."""
    import io
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")
    if not c.imagen_base64:
        raise HTTPException(400, "El contenido no tiene imagen generada")

    try:
        img_bytes = base64.b64decode(c.imagen_base64)
    except Exception:
        raise HTTPException(400, "Imagen base64 inválida")

    filename = f"ecopost_{item_id}_{c.tipo}.png"
    web_base_url = "https://www.ecomodulosypiscinas.com.ar"
    web_api_key  = "eco-crm-api-key-2024"

    import io as _io
    form_data = _io.BytesIO(img_bytes)
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            r = await hc.post(
                f"{web_base_url}/api/admin/upload",
                headers={"x-api-key": web_api_key},
                files={"file": (filename, form_data, "image/png")},
            )
        if r.status_code not in (200, 201):
            raise HTTPException(r.status_code, f"Error subiendo a R2: {r.text[:200]}")
        data = r.json()
        url = data.get("url") or data.get("imagen_url") or data.get("path")
        if not url:
            raise HTTPException(500, "R2 no devolvió URL")

        c.imagen_url  = url
        c.imagen_base64 = None   # limpiar base64 del DB
        db.commit()
        return {"ok": True, "imagen_url": url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error de conexión con R2: {str(e)[:100]}")


@router.delete("/api/ecopost/{item_id}")
async def api_eliminar(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(user)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar contenido")

    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    db.delete(c)
    db.commit()
    return {"ok": True}


# ─── PUBLICACIÓN EN REDES SOCIALES ───────────────────────────────────────────

META_GRAPH_URL = "https://graph.facebook.com/v22.0"


@router.post("/api/ecopost/{item_id}/publicar-facebook")
async def api_publicar_facebook(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica el contenido en la página de Facebook."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    page_id    = get_config_value("meta_page_id", db)

    if not page_token or not page_id:
        raise HTTPException(400, "Configurar Meta Page Access Token y Page ID en Configuración → Meta")

    # Prefer per-page Page Access Token (pages_manage_posts) over global user token
    page_obj = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if page_obj and page_obj.page_token:
        page_token = page_obj.page_token

    message = "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))

    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            if c.imagen_url:
                r = await hc.post(
                    f"{META_GRAPH_URL}/{page_id}/photos",
                    data={"url": c.imagen_url, "caption": message, "access_token": page_token},
                )
            elif c.imagen_base64:
                img_bytes = base64.b64decode(c.imagen_base64)
                r = await hc.post(
                    f"{META_GRAPH_URL}/{page_id}/photos",
                    data={"caption": message, "access_token": page_token},
                    files={"source": ("imagen.png", img_bytes, "image/png")},
                )
            else:
                r = await hc.post(
                    f"{META_GRAPH_URL}/{page_id}/feed",
                    data={"message": message, "access_token": page_token},
                )

        if r.status_code != 200:
            err = r.json()
            raise HTTPException(400, f"Error Meta API: {err.get('error', {}).get('message', r.text[:200])}")

        post_id = r.json().get("id") or r.json().get("post_id")
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        db.commit()
        return {"ok": True, "red": "facebook", "post_id": post_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando en Facebook: {str(e)[:150]}")


@router.post("/api/ecopost/{item_id}/publicar-instagram")
async def api_publicar_instagram(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """
    Publica en Instagram Business.
    Si solo hay base64, intenta subir a R2 automáticamente antes de publicar.
    """
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    ig_user_id = get_config_value("meta_ig_user_id", db)

    if not page_token or not ig_user_id:
        raise HTTPException(400, "Configurar Meta Page Access Token e IG User ID en Configuración → Meta")

    img_url = c.imagen_url
    if not img_url and c.imagen_base64:
        # Auto-subir a R2 para obtener URL pública
        try:
            img_bytes = base64.b64decode(c.imagen_base64)
            filename  = f"ecopost_{c.id}_{c.tipo}.png"
            async with httpx.AsyncClient(timeout=30) as hc:
                r = await hc.post(
                    "https://www.ecomodulosypiscinas.com.ar/api/admin/upload",
                    headers={"x-api-key": "eco-crm-api-key-2024"},
                    files={"file": (filename, img_bytes, "image/png")},
                )
            if r.status_code in (200, 201):
                url = r.json().get("url") or r.json().get("imagen_url") or r.json().get("path")
                if url:
                    img_url = url
                    c.imagen_url    = url
                    c.imagen_base64 = None
                    db.flush()
        except Exception as e:
            logger.warning(f"[ecopost] Auto-subida R2 para IG falló: {e}")

    if not img_url:
        raise HTTPException(400, "Instagram requiere imagen con URL pública. Usá 'Subir imagen' primero.")

    caption = "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))

    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            r1 = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media",
                data={"image_url": img_url, "caption": caption, "access_token": page_token},
            )
            if r1.status_code != 200:
                err = r1.json()
                raise HTTPException(400, f"Error container IG: {err.get('error', {}).get('message', r1.text[:200])}")

            creation_id = r1.json().get("id")
            if not creation_id:
                raise HTTPException(502, "Meta no devolvió creation_id")

            r2 = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": page_token},
            )
            if r2.status_code != 200:
                err = r2.json()
                raise HTTPException(400, f"Error publicando IG: {err.get('error', {}).get('message', r2.text[:200])}")

        ig_media_id = r2.json().get("id")
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        db.commit()
        return {"ok": True, "red": "instagram", "ig_media_id": ig_media_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando en Instagram: {str(e)[:150]}")


# ─── GESTIÓN DE PÁGINAS META (MULTI-PÁGINA) ───────────────────────────────────

@router.get("/api/meta/paginas")
async def api_meta_paginas_list(
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    pages = db.query(MetaPagina).order_by(MetaPagina.nombre).all()
    return [
        {"page_id": p.page_id, "nombre": p.nombre, "ig_user_id": p.ig_user_id, "activa": p.activa}
        for p in pages
    ]


@router.post("/api/meta/paginas/sync")
async def api_meta_paginas_sync(
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Sincroniza páginas desde el Business Manager usando el System User token."""
    token = get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Configurar meta_page_access_token en Configuración → Meta")

    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(
            f"{META_GRAPH_URL}/me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account{id,name}",
                "limit": "50",
                "access_token": token,
            },
        )
    if r.status_code != 200:
        err = r.json()
        raise HTTPException(400, f"Error Graph API: {err.get('error', {}).get('message', r.text[:200])}")

    pages_data = r.json().get("data", [])
    synced = []
    for p in pages_data:
        ig_id = None
        iba = p.get("instagram_business_account")
        if isinstance(iba, dict):
            ig_id = iba.get("id")

        page_tok = p.get("access_token") or None

        existing = db.query(MetaPagina).filter(MetaPagina.page_id == p["id"]).first()
        if existing:
            existing.nombre = p["name"]
            if page_tok:
                existing.page_token = page_tok
            if ig_id and not existing.ig_user_id:
                existing.ig_user_id = ig_id
        else:
            db.add(MetaPagina(page_id=p["id"], nombre=p["name"], ig_user_id=ig_id,
                              page_token=page_tok, activa=True))
        synced.append({"page_id": p["id"], "nombre": p["name"], "ig_user_id": ig_id})

    db.commit()
    return {"ok": True, "synced": len(synced), "pages": synced}


@router.put("/api/meta/paginas/{page_id}")
async def api_meta_paginas_update(
    page_id: str,
    request: Request,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    p = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not p:
        raise HTTPException(404, "Página no encontrada")
    data = await request.json()
    if "activa" in data:
        p.activa = bool(data["activa"])
    if "ig_user_id" in data:
        p.ig_user_id = data["ig_user_id"] or None
    db.commit()
    return {"ok": True}


class PublicarRedesReq(BaseModel):
    pages: List[dict]  # [{page_id, facebook, instagram}]


@router.post("/api/ecopost/{item_id}/publicar-redes")
async def api_publicar_redes(
    item_id: int,
    req: PublicarRedesReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica en múltiples páginas de Facebook e Instagram simultáneamente."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    token = get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Configurar meta_page_access_token en Configuración → Meta")

    message = "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))

    # Auto-subir imagen base64 → URL pública (necesario para Instagram)
    img_url = c.imagen_url
    if not img_url and c.imagen_base64:
        try:
            img_bytes = base64.b64decode(c.imagen_base64)
            filename = f"ecopost_{c.id}_{c.tipo}.png"
            async with httpx.AsyncClient(timeout=10) as hc:
                r = await hc.post(
                    "https://www.ecomodulosypiscinas.com.ar/api/admin/upload",
                    headers={"x-api-key": "eco-crm-api-key-2024"},
                    files={"file": (filename, img_bytes, "image/png")},
                )
            if r.status_code in (200, 201):
                url = r.json().get("url") or r.json().get("imagen_url") or r.json().get("path")
                if url:
                    img_url = url
                    c.imagen_url = url
                    c.imagen_base64 = None
                    db.flush()
        except Exception as e:
            logger.warning(f"[ecopost] Auto-subida R2 falló: {e}")

    resultados = []

    async with httpx.AsyncClient(timeout=8) as hc:
        for page_req in req.pages:
            pid = page_req.get("page_id")
            do_fb = page_req.get("facebook", False)
            do_ig = page_req.get("instagram", False)

            page_obj = db.query(MetaPagina).filter(MetaPagina.page_id == pid).first()
            ig_uid = page_obj.ig_user_id if page_obj else None
            # Prefer per-page Page Access Token (pages_manage_posts) over global user token
            page_token_to_use = (page_obj.page_token if page_obj and page_obj.page_token else None) or token

            if do_fb:
                try:
                    if c.imagen_url:
                        r = await hc.post(
                            f"{META_GRAPH_URL}/{pid}/photos",
                            data={"url": c.imagen_url, "caption": message, "access_token": page_token_to_use},
                        )
                    elif c.imagen_base64:
                        img_bytes2 = base64.b64decode(c.imagen_base64)
                        r = await hc.post(
                            f"{META_GRAPH_URL}/{pid}/photos",
                            data={"caption": message, "access_token": page_token_to_use},
                            files={"source": ("imagen.png", img_bytes2, "image/png")},
                        )
                    else:
                        r = await hc.post(
                            f"{META_GRAPH_URL}/{pid}/feed",
                            data={"message": message, "access_token": page_token_to_use},
                        )
                    if r.status_code == 200:
                        post_id = r.json().get("id") or r.json().get("post_id")
                        resultados.append({"page_id": pid, "red": "facebook", "ok": True, "post_id": post_id})
                    else:
                        err_msg = r.json().get("error", {}).get("message", r.text[:150])
                        resultados.append({"page_id": pid, "red": "facebook", "ok": False, "error": err_msg})
                except Exception as e:
                    resultados.append({"page_id": pid, "red": "facebook", "ok": False, "error": str(e)[:150]})

            if do_ig:
                if not ig_uid:
                    resultados.append({"page_id": pid, "red": "instagram", "ok": False, "error": "Sin Instagram Business Account configurado"})
                elif not img_url:
                    resultados.append({"page_id": pid, "red": "instagram", "ok": False, "error": "Instagram requiere imagen con URL pública"})
                else:
                    try:
                        r1 = await hc.post(
                            f"{META_GRAPH_URL}/{ig_uid}/media",
                            data={"image_url": img_url, "caption": message, "access_token": page_token_to_use},
                        )
                        if r1.status_code != 200:
                            err_msg = r1.json().get("error", {}).get("message", r1.text[:150])
                            resultados.append({"page_id": pid, "red": "instagram", "ok": False, "error": err_msg})
                        else:
                            creation_id = r1.json().get("id")
                            r2 = await hc.post(
                                f"{META_GRAPH_URL}/{ig_uid}/media_publish",
                                data={"creation_id": creation_id, "access_token": page_token_to_use},
                            )
                            if r2.status_code == 200:
                                resultados.append({"page_id": pid, "red": "instagram", "ok": True, "ig_media_id": r2.json().get("id")})
                            else:
                                err_msg = r2.json().get("error", {}).get("message", r2.text[:150])
                                resultados.append({"page_id": pid, "red": "instagram", "ok": False, "error": err_msg})
                    except Exception as e:
                        resultados.append({"page_id": pid, "red": "instagram", "ok": False, "error": str(e)[:150]})

    any_ok = any(r["ok"] for r in resultados)
    if any_ok:
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        db.commit()

    return {"ok": any_ok, "resultados": resultados}


# ─── REFERENCIAS DE ESTILO ────────────────────────────────────────────────────

@router.get("/api/ecopost/referencias")
async def api_refs_list(
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    refs = db.query(EcopostReferencia).order_by(EcopostReferencia.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "nombre": r.nombre,
            "descripcion": r.descripcion,
            "tipo": r.tipo,
            "tiene_imagen": bool(r.imagen_base64),
            "subido_por": r.subido_por.nombre if r.subido_por else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in refs
    ]


@router.post("/api/ecopost/referencias")
async def api_refs_crear(
    file: UploadFile = File(...),
    nombre: str = Form(""),
    descripcion: str = Form(""),
    tipo: str = Form("estilo"),
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "La imagen no puede superar 5 MB")

    b64 = base64.b64encode(raw).decode()
    ref = EcopostReferencia(
        nombre=nombre or file.filename or "Referencia",
        descripcion=descripcion,
        tipo=tipo,
        imagen_base64=b64,
        subido_por_id=user.id,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return {"ok": True, "id": ref.id}


@router.get("/api/ecopost/referencias/{ref_id}/imagen")
async def api_refs_imagen(
    ref_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    ref = db.query(EcopostReferencia).filter(EcopostReferencia.id == ref_id).first()
    if not ref or not ref.imagen_base64:
        raise HTTPException(404, "Sin imagen")
    try:
        img_bytes = base64.b64decode(ref.imagen_base64)
        return Response(content=img_bytes, media_type="image/jpeg")
    except Exception:
        raise HTTPException(500, "Error decodificando imagen")


@router.delete("/api/ecopost/referencias/{ref_id}")
async def api_refs_eliminar(
    ref_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(user)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar referencias")
    ref = db.query(EcopostReferencia).filter(EcopostReferencia.id == ref_id).first()
    if not ref:
        raise HTTPException(404, "Referencia no encontrada")
    db.delete(ref)
    db.commit()
    return {"ok": True}


# ─── PLANIFICADOR DE CONTENIDO ────────────────────────────────────────────────

class PlanificadorReq(BaseModel):
    dias: int = 7          # 7 | 15 | 21 | 31
    redes: List[str] = ["instagram", "facebook"]  # instagram | facebook | tiktok | youtube
    productos: List[str] = ["PISCINA", "MODULO"]  # PISCINA | MODULO | COMBO
    tono: Optional[str] = "profesional y cercano"


@router.post("/api/ecopost/planificador/generar")
async def api_planificador_generar(
    body: PlanificadorReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Genera un plan de contenido para N días con IA. Devuelve lista de posts a revisar antes de guardar."""
    if body.dias not in (7, 15, 21, 31):
        raise HTTPException(400, "Días válidos: 7, 15, 21, 31")

    redes_str = ", ".join(body.redes)
    prods_str = ", ".join(body.productos)
    tipos = ["flyer", "story", "carrusel", "reel"]

    prompt = f"""Sos un experto en marketing digital para EcoFiver, empresa argentina de Zárate, Buenos Aires que vende piscinas de fibra de vidrio, módulos habitacionales y viviendas modulares wood frame.

Generá un plan de contenido para redes sociales de exactamente {body.dias} posts, distribuidos para las redes: {redes_str}.
Productos a promocionar: {prods_str}.
Tono: {body.tono}.

Para cada post incluí:
- dia: número del día (1 a {body.dias})
- red: la red social (una de: {redes_str})
- tipo: flyer, story, carrusel o reel
- producto: PISCINA, MODULO o COMBO
- titulo: título del post (máx 80 caracteres, castellano argentino)
- copy: texto del post con emojis (2-3 frases, castellano argentino)
- hashtags: 5-8 hashtags separados por espacio
- prompt_imagen: descripción para generar la imagen con IA (en inglés, detallado, fotorrealista)

Reglas:
- Variá los tipos de contenido y los productos
- Incluí siempre contenido de verano (piscinas) y de vivienda
- Día 1 empezá con algo de alto impacto visual
- Repartí proporcionalmente entre las redes
- Castellano rioplatense, nada de "usted" ni español neutro

Respondé SOLO con un JSON válido, sin texto adicional:
{{"plan": [
  {{"dia": 1, "red": "instagram", "tipo": "flyer", "producto": "PISCINA", "titulo": "...", "copy": "...", "hashtags": "...", "prompt_imagen": "..."}}
]}}"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=4000, temperature=0.8)
        # Extraer JSON
        respuesta = respuesta.strip()
        if "```json" in respuesta:
            respuesta = respuesta.split("```json")[1].split("```")[0].strip()
        elif "```" in respuesta:
            respuesta = respuesta.split("```")[1].split("```")[0].strip()

        data = json.loads(respuesta)
        plan = data.get("plan", [])

        # Asegurar que no supere los días pedidos
        plan = plan[:body.dias]

        return {"ok": True, "dias": body.dias, "total": len(plan), "plan": plan}
    except json.JSONDecodeError as e:
        raise HTTPException(502, f"IA devolvió formato inválido. Intentá de nuevo.")
    except Exception as e:
        raise HTTPException(502, f"Error generando plan: {str(e)[:120]}")


@router.post("/api/ecopost/planificador/guardar")
async def api_planificador_guardar(
    body: dict,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Guarda los posts seleccionados del plan como borradores en Ecopost."""
    posts = body.get("posts", [])
    if not posts:
        raise HTTPException(400, "No hay posts para guardar")

    guardados = []
    for p in posts:
        c = ContenidoEcopost(
            titulo=p.get("titulo", "")[:200],
            tipo=p.get("tipo", "flyer"),
            producto=p.get("producto"),
            copy_texto=p.get("copy", ""),
            copy_hashtags=p.get("hashtags", ""),
            imagen_prompt=p.get("prompt_imagen", ""),
            notas=f"Red: {p.get('red','')} · Día {p.get('dia','')} del plan",
            estado="borrador",
            creado_por_id=user.id,
        )
        db.add(c)
        db.flush()
        guardados.append(c.id)

    db.commit()
    return {"ok": True, "guardados": len(guardados), "ids": guardados}
