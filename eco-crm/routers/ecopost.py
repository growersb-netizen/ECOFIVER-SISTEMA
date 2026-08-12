"""
Módulo 14 — Ecopost
Gestión de contenido para redes sociales: copy + imagen con IA, flujo de aprobación.
Acceso: ADMIN y COORDINADOR_OPERATIVO
"""
import json
import base64
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

VIDEO_DIR = Path("data/ecopost_videos")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

from database.database import get_db
from database.models import ContenidoEcopost, EcopostReferencia, Usuario, MetaPagina
from routers.auth import require_auth, get_user_roles
from routers.configuracion import get_config_value
from utils.ai_client import ai_complete, get_active_provider
from utils.contexto_ecofiver import ctx_redes_sociales, ctx_empresa

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
    tipo: Optional[str] = "flyer"       # flyer (1:1) | story (9:16) | carrusel | reel
    producto: Optional[str] = ""        # para contextualizar dimensiones reales


class GuardarContenidoReq(BaseModel):
    titulo: Optional[str] = ""
    tipo: Optional[str] = "flyer"
    media_type: Optional[str] = "photo"   # photo | video | carousel | story | reel
    producto: Optional[str] = None
    modelo_especifico: Optional[str] = None
    copy_texto: Optional[str] = ""
    copy_hashtags: Optional[str] = ""
    subtitulos: Optional[str] = ""
    imagen_prompt: Optional[str] = ""
    imagen_base64: Optional[str] = None
    imagen_url: Optional[str] = None
    carousel_urls: Optional[List[str]] = []
    publish_at: Optional[str] = None      # ISO datetime string para programar
    notas: Optional[str] = ""


class CambiarEstadoReq(BaseModel):
    estado: str     # borrador | aprobado | publicado | archivado


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _content_dict(c: ContenidoEcopost) -> dict:
    crm_host = "https://eco-crm-production.up.railway.app"
    video_url = None
    if getattr(c, 'video_token', None):
        video_url = f"{crm_host}/pub/video/{c.video_token}"
    return {
        "id": c.id,
        "titulo": c.titulo,
        "tipo": c.tipo,
        "media_type": getattr(c, 'media_type', 'photo') or 'photo',
        "producto": c.producto,
        "modelo_especifico": c.modelo_especifico,
        "copy_texto": c.copy_texto,
        "copy_hashtags": c.copy_hashtags,
        "subtitulos": getattr(c, 'subtitulos', '') or '',
        "imagen_prompt": c.imagen_prompt,
        "imagen_url": c.imagen_url,
        "video_url": video_url,
        "carousel_urls": json.loads(getattr(c, 'carousel_urls', None) or '[]'),
        "tiene_imagen": bool(c.imagen_base64 or c.imagen_url),
        "tiene_video": bool(getattr(c, 'video_token', None)),
        "duracion_seg": getattr(c, 'duracion_seg', None),
        "publish_at": c.publish_at.isoformat() if getattr(c, 'publish_at', None) else None,
        "redes_publicadas": json.loads(getattr(c, 'redes_publicadas', None) or '{}'),
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
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 1024},
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
    "de vidrio y módulos habitacionales de celulosa estructural, ubicada en Zárate, Buenos Aires. "
    "Estilo fotográfico moderno y aspiracional, colores vibrantes, alta resolución, "
    "ambiente familiar argentino, entorno al aire libre soleado. "
)

# Dimensiones reales de los productos para dar contexto preciso a la IA
_DIMENSIONES_PRODUCTO = {
    "PISCINA": (
        "Las piscinas de fibra de vidrio EcoFiver miden entre 5m×2.5m (pequeña) y 10m×4m (grande), "
        "con profundidad de 1.35m a 1.70m. Son autoportantes, van sobre tierra o losa. "
        "Colores disponibles: azul cielo, verde agua, blanco perla, arena. "
        "Instalación superficial, sin excavación profunda."
    ),
    "MODULO": (
        "Los módulos habitacionales EcoFiver son construcciones prefabricadas de celulosa estructural "
        "de 15m², 20m², 25m², 30m² o mayor. Techo a dos aguas o plano, ventanas amplias, "
        "puerta de entrada. Se instalan en un día. Terminación exterior: chapa prepintada o revestimiento vinílico. "
        "Interior: paredes lisas, piso flotante. Pueden usarse como oficina, habitación, local comercial."
    ),
    "COMBO": (
        "Combo piscina + módulo habitacional EcoFiver: piscina de fibra de vidrio instalada junto a "
        "un módulo de 15-25m². Todo en un solo día de instalación. Espacio exterior recreativo completo."
    ),
    "HIDROMASAJE": (
        "Hidromasajes y jacuzzis EcoFiver de fibra de vidrio: modelos de 2 personas (1.5m×1.5m) "
        "hasta 6 personas (2.2m×2.2m). Jets de agua, iluminación LED, cubierta opcional. "
        "Para uso interior o exterior."
    ),
    "REPOSERA_FIBRA": (
        "Reposeras de fibra de vidrio EcoFiver: resistentes, impermeables, diseño ergonómico, "
        "colores vibrantes (azul, blanco, verde). Ideales para bordes de piscina y jardines. "
        "Tamaño estándar 180cm×65cm."
    ),
    "CUCHA": (
        "Cuchas para perros de polietileno reciclado EcoFiver: impermeables, resistentes al sol, "
        "fáciles de limpiar. Tamaños pequeño (40×50cm), mediano (60×70cm), grande (80×90cm)."
    ),
    "BANIO_QUIMICO": (
        "Baños químicos portátiles EcoFiver de polietileno rotomoldeado: 1.2m×1.2m×2.4m, "
        "capacidad 250 litros. Colores: azul, verde, gris. Para obras y eventos."
    ),
    "GARITA_SEGURIDAD": (
        "Garitas de seguridad EcoFiver prefabricadas: 1.5m×1.5m o 2m×2m, "
        "con ventana lateral, puerta con cerradura. Instalación rápida en cualquier terreno."
    ),
}


def _enriquecer_prompt_imagen(prompt: str, tipo: str, producto: str = "") -> str:
    """Agrega contexto de marca EcoFiver + dimensiones reales al prompt para imágenes más precisas."""
    formato_map = {
        "story":     "Composición vertical 9:16, estilo Instagram Story, texto grande arriba.",
        "carrusel":  "Composición cuadrada 1:1, primer slide de carrusel Instagram.",
        "reel":      "Frame de video vertical 9:16, escena dinámica con movimiento implícito.",
    }
    formato = formato_map.get(tipo, "Composición cuadrada 1:1, estilo publicación de Instagram.")
    dim_ctx = ""
    prod_key = producto.upper() if producto else ""
    for key, desc in _DIMENSIONES_PRODUCTO.items():
        if key in prod_key or prod_key in key:
            dim_ctx = f" Dimensiones y características del producto: {desc}"
            break
    return f"{_ECOFIVER_IMG_CTX}{dim_ctx} {prompt}. {formato}"


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


@router.get("/api/ecopost/programados")
async def api_programados(
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Lista los contenidos con publicación programada pendiente."""
    ahora = datetime.now()
    items = (
        db.query(ContenidoEcopost)
        .filter(
            ContenidoEcopost.publish_at.isnot(None),
            ContenidoEcopost.publish_at > ahora,
            ContenidoEcopost.estado.in_(["borrador", "aprobado"]),
        )
        .order_by(ContenidoEcopost.publish_at)
        .all()
    )
    return [_content_dict(c) for c in items]


@router.get("/api/ecopost/ml-fotos")
async def api_ml_fotos(
    producto: Optional[str] = None,
    limit: int = 40,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Expone las fotos de la biblioteca ML para usarlas en Ecopost sin resubir."""
    try:
        from database.models import BorradorML
        q = db.query(BorradorML).filter(BorradorML.fotos_json.isnot(None))
        if producto:
            q = q.filter(BorradorML.producto.ilike(f"%{producto}%"))
        borradores = q.order_by(BorradorML.updated_at.desc()).limit(limit).all()

        fotos_list = []
        seen: set = set()
        for b in borradores:
            try:
                fotos = json.loads(b.fotos_json or "[]")
                for f in fotos:
                    url = (f.get("url") or f.get("secure_url") or f.get("imagen_url") or "").strip()
                    if url and url not in seen:
                        seen.add(url)
                        fotos_list.append({
                            "url": url,
                            "titulo": b.titulo or "",
                            "producto": b.producto or "",
                            "borrador_id": b.id,
                        })
            except Exception:
                pass

        return {"ok": True, "total": len(fotos_list), "fotos": fotos_list}
    except Exception as e:
        logger.warning(f"[ecopost] api_ml_fotos error: {e}")
        return {"ok": True, "total": 0, "fotos": [], "nota": "Sin fotos ML disponibles"}


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
    """Sirve la imagen PNG generada directamente (requiere sesión)."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c or not c.imagen_base64:
        raise HTTPException(404, "Sin imagen")
    try:
        img_bytes = base64.b64decode(c.imagen_base64)
        return Response(content=img_bytes, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})
    except Exception:
        raise HTTPException(500, "Error decodificando imagen")


@router.get("/pub/img/{token}")
async def api_imagen_publica(
    token: str,
    db: Session = Depends(get_db),
):
    """Endpoint PÚBLICO (sin auth) para servir imágenes Ecopost via token UUID.
    Usado para publicar en Instagram/Meta que necesitan URL accesible sin cookies."""
    if not token or len(token) < 20:
        raise HTTPException(404, "Not found")
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.public_token == token).first()
    if not c or not c.imagen_base64:
        raise HTTPException(404, "Imagen no encontrada")
    try:
        img_bytes = base64.b64decode(c.imagen_base64)
        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception:
        raise HTTPException(500, "Error decodificando imagen")


def _ensure_public_token(c: ContenidoEcopost, db: Session) -> str:
    """Asegura que el contenido tenga un public_token. Genera uno si no tiene."""
    if not c.public_token:
        import secrets
        c.public_token = secrets.token_urlsafe(32)
        db.commit()
    return c.public_token


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

    prompt = f"""{ctx_redes_sociales(tipo_contenido=tipo_str, producto=body.producto, modelo=body.modelo or "")}

════════════════════════════════════════════
TAREA: Escribí copy para redes sociales — formato {tipo_str}
════════════════════════════════════════════

- Producto: {body.producto}
- Modelo / variante: {body.modelo or "genérico"}
- Info adicional: {body.descripcion_extra or "ninguna"}
- Tono pedido: {body.tono}

Respondé SOLO con este formato exacto, sin texto adicional:
TITULO: [título llamativo, max 10 palabras, en castellano argentino]
COPY: [2-3 oraciones para Instagram/Facebook con emojis, mencionar beneficio clave y CTA]
HASHTAGS: [6-10 hashtags separados por espacio, mezclar genéricos y específicos]"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=1024, temperature=0.65)
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
    prompt_final = _enriquecer_prompt_imagen(body.prompt, body.tipo, body.producto or "")
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
    publish_at_dt = None
    if body.publish_at:
        try:
            publish_at_dt = datetime.fromisoformat(body.publish_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    c = ContenidoEcopost(
        titulo=body.titulo,
        tipo=body.tipo,
        media_type=body.media_type or "photo",
        producto=body.producto,
        modelo_especifico=body.modelo_especifico,
        copy_texto=body.copy_texto,
        copy_hashtags=body.copy_hashtags,
        subtitulos=body.subtitulos or "",
        imagen_prompt=body.imagen_prompt,
        imagen_base64=body.imagen_base64,
        imagen_url=body.imagen_url,
        carousel_urls=json.dumps(body.carousel_urls or []),
        publish_at=publish_at_dt,
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

    data = body.dict(exclude_none=True)
    # Serialize special fields before storing
    if "carousel_urls" in data:
        data["carousel_urls"] = json.dumps(data["carousel_urls"] or [])
    if "publish_at" in data and data["publish_at"]:
        try:
            data["publish_at"] = datetime.fromisoformat(data["publish_at"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            data.pop("publish_at", None)
    for field, val in data.items():
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
    """Genera URL pública para la imagen usando el endpoint propio del CRM (no depende de R2 externo)."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")
    if not c.imagen_base64:
        raise HTTPException(400, "El contenido no tiene imagen generada")

    token = _ensure_public_token(c, db)
    crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
    url = f"{crm_host.rstrip('/')}/pub/img/{token}"
    # Actualizar imagen_url para que quede registrado en el contenido
    c.imagen_url = url
    db.commit()
    return {"ok": True, "imagen_url": url}


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
        # Generar URL pública usando el endpoint propio del CRM (no depende de sitio externo)
        token = _ensure_public_token(c, db)
        crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
        img_url = f"{crm_host.rstrip('/')}/pub/img/{token}"
        logger.info(f"[ecopost] Usando URL pública propia para IG: {img_url}")

    if not img_url:
        raise HTTPException(400, "Instagram requiere imagen. Generá una imagen primero.")

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

    # Auto-generar URL pública usando el endpoint propio del CRM (Instagram la necesita)
    img_url = c.imagen_url
    if not img_url and c.imagen_base64:
        try:
            token_pub = _ensure_public_token(c, db)
            crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
            img_url = f"{crm_host.rstrip('/')}/pub/img/{token_pub}"
            c.imagen_url = img_url
            db.flush()
            logger.info(f"[ecopost] URL pública generada para publicar-redes: {img_url}")
        except Exception as e:
            logger.warning(f"[ecopost] No se pudo generar URL pública: {e}")

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

    prompt = f"""{ctx_redes_sociales(tipo_contenido="plan de contenido para redes sociales")}

════════════════════════════════════════════
TAREA: Plan de contenido — {body.dias} posts
════════════════════════════════════════════

Redes: {redes_str}
Productos a promocionar: {prods_str}
Tono: {body.tono}

Para cada post incluí:
- dia: número del día (1 a {body.dias})
- red: la red social (una de: {redes_str})
- tipo: flyer, story, carrusel o reel
- producto: PISCINA, MODULO, HIDROMASAJE o COMBO
- titulo: título del post (máx 80 caracteres, castellano argentino)
- copy: texto del post con emojis (2-3 frases, castellano argentino rioplatense)
- hashtags: 5-8 hashtags separados por espacio
- prompt_imagen: descripción para generar la imagen con IA (en inglés, detallado, fotorrealista, mostrando el producto real)

Reglas de distribución:
- Día 1 empezá con alto impacto visual (piscina instalada, módulo terminado)
- Variá los tipos de contenido y los productos a lo largo del plan
- Incluí al menos 1 post educativo (comparar fibra vs hormigón, autoportante vs enterrada, etc.)
- Incluí al menos 1 post de prueba social (cliente, resultado de instalación)
- Repartí proporcionalmente entre las redes
- Nunca prometás precios ni plazos exactos en el copy

Respondé SOLO con un JSON válido, sin texto adicional:
{{"plan": [
  {{"dia": 1, "red": "instagram", "tipo": "flyer", "producto": "PISCINA", "titulo": "...", "copy": "...", "hashtags": "...", "prompt_imagen": "..."}}
]}}"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=4000, temperature=0.65)
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


# ─── VIDEO UPLOAD & SERVING ──────────────────────────────────────────────────

ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/api/ecopost/{item_id}/upload-video")
async def api_upload_video(
    item_id: int,
    video: UploadFile = File(...),
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Sube un video MP4/MOV y genera un token público para servir sin autenticación."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    if video.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(400, f"Formato no soportado: {video.content_type}. Usar MP4, MOV, AVI o WEBM.")

    raw = await video.read()
    if len(raw) > MAX_VIDEO_SIZE:
        raise HTTPException(400, "El video no puede superar 500 MB")

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    ext = Path(video.filename or "video.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".avi", ".webm"}:
        ext = ".mp4"
    filename = f"{token}{ext}"
    filepath = VIDEO_DIR / filename
    filepath.write_bytes(raw)

    c.video_token = token
    if not getattr(c, "media_type", None) or c.media_type == "photo":
        c.media_type = "video"
    db.commit()

    crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
    video_url = f"{crm_host.rstrip('/')}/pub/video/{token}"
    return {
        "ok": True,
        "video_token": token,
        "video_url": video_url,
        "size_mb": round(len(raw) / 1024 / 1024, 2),
    }


@router.get("/pub/video/{token}")
async def api_video_publico(
    token: str,
    db: Session = Depends(get_db),
):
    """Endpoint PÚBLICO (sin auth) — sirve videos Ecopost via token para Reels/TikTok/YouTube."""
    if not token or len(token) < 20:
        raise HTTPException(404, "Not found")
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.video_token == token).first()
    if not c:
        raise HTTPException(404, "Video no encontrado")
    for ext in (".mp4", ".mov", ".avi", ".webm"):
        filepath = VIDEO_DIR / f"{token}{ext}"
        if filepath.exists():
            media_type = "video/mp4" if ext == ".mp4" else (
                "video/quicktime" if ext == ".mov" else "video/webm"
            )
            return FileResponse(
                str(filepath),
                media_type=media_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    raise HTTPException(404, "Archivo de video no encontrado en disco")


# ─── INSTAGRAM REELS ─────────────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/publicar-ig-reel")
async def api_publicar_ig_reel(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica el video como Reel en Instagram Business via Meta Graph API."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    ig_user_id = get_config_value("meta_ig_user_id", db)
    if not page_token or not ig_user_id:
        raise HTTPException(400, "Configurar Meta Page Access Token e IG User ID en Configuración → Meta")

    if not getattr(c, "video_token", None):
        raise HTTPException(400, "Sin video. Subí un MP4/MOV primero usando 'Subir Video'.")

    crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
    video_url = f"{crm_host.rstrip('/')}/pub/video/{c.video_token}"
    caption = "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))

    try:
        import asyncio
        async with httpx.AsyncClient(timeout=120) as hc:
            # Paso 1: crear media container
            r1 = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": page_token,
                },
            )
            if r1.status_code != 200:
                err = r1.json()
                raise HTTPException(400, f"Error container Reel: {err.get('error', {}).get('message', r1.text[:200])}")

            creation_id = r1.json().get("id")
            if not creation_id:
                raise HTTPException(502, "Meta no devolvió creation_id para el Reel")

            # Paso 2: esperar procesamiento de video (máx 60s)
            for _ in range(12):
                await asyncio.sleep(5)
                r_st = await hc.get(
                    f"{META_GRAPH_URL}/{creation_id}",
                    params={"fields": "status_code", "access_token": page_token},
                )
                if r_st.status_code == 200:
                    status = r_st.json().get("status_code", "")
                    if status == "FINISHED":
                        break
                    elif status == "ERROR":
                        raise HTTPException(502, "Error procesando video en Meta. Verificar formato (H.264 / AAC).")

            # Paso 3: publicar
            r2 = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": page_token},
            )
            if r2.status_code != 200:
                err = r2.json()
                raise HTTPException(400, f"Error publicando Reel: {err.get('error', {}).get('message', r2.text[:200])}")

        ig_media_id = r2.json().get("id")
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        redes_pub = json.loads(getattr(c, "redes_publicadas", None) or "{}")
        redes_pub["instagram_reel"] = datetime.now().isoformat()
        c.redes_publicadas = json.dumps(redes_pub)
        db.commit()
        return {"ok": True, "red": "instagram_reel", "ig_media_id": ig_media_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando Reel: {str(e)[:150]}")


# ─── INSTAGRAM STORIES ────────────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/publicar-ig-story")
async def api_publicar_ig_story(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica como Story en Instagram. Soporta imagen o video."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    ig_user_id = get_config_value("meta_ig_user_id", db)
    if not page_token or not ig_user_id:
        raise HTTPException(400, "Configurar Meta Page Access Token e IG User ID en Configuración → Meta")

    crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
    has_video = bool(getattr(c, "video_token", None))
    img_url = c.imagen_url
    if not img_url and c.imagen_base64:
        tok = _ensure_public_token(c, db)
        img_url = f"{crm_host.rstrip('/')}/pub/img/{tok}"

    if not has_video and not img_url:
        raise HTTPException(400, "Story requiere imagen o video. Generá una imagen o subí un video.")

    try:
        async with httpx.AsyncClient(timeout=60) as hc:
            if has_video:
                payload = {
                    "media_type": "STORIES",
                    "video_url": f"{crm_host.rstrip('/')}/pub/video/{c.video_token}",
                    "access_token": page_token,
                }
            else:
                payload = {
                    "media_type": "STORIES",
                    "image_url": img_url,
                    "access_token": page_token,
                }
            r1 = await hc.post(f"{META_GRAPH_URL}/{ig_user_id}/media", data=payload)
            if r1.status_code != 200:
                err = r1.json()
                raise HTTPException(400, f"Error creando Story: {err.get('error', {}).get('message', r1.text[:200])}")

            creation_id = r1.json().get("id")
            r2 = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": creation_id, "access_token": page_token},
            )
            if r2.status_code != 200:
                err = r2.json()
                raise HTTPException(400, f"Error publicando Story: {err.get('error', {}).get('message', r2.text[:200])}")

        ig_media_id = r2.json().get("id")
        redes_pub = json.loads(getattr(c, "redes_publicadas", None) or "{}")
        redes_pub["instagram_story"] = datetime.now().isoformat()
        c.redes_publicadas = json.dumps(redes_pub)
        db.commit()
        return {"ok": True, "red": "instagram_story", "ig_media_id": ig_media_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando Story: {str(e)[:150]}")


# ─── FACEBOOK VIDEO ───────────────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/publicar-fb-video")
async def api_publicar_fb_video(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica un video en la página de Facebook via file_url."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    page_id    = get_config_value("meta_page_id", db)
    if not page_token or not page_id:
        raise HTTPException(400, "Configurar Meta Page Access Token y Page ID en Configuración → Meta")

    page_obj = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if page_obj and page_obj.page_token:
        page_token = page_obj.page_token

    if not getattr(c, "video_token", None):
        raise HTTPException(400, "Sin video. Subí un MP4/MOV primero.")

    crm_host = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"
    video_url = f"{crm_host.rstrip('/')}/pub/video/{c.video_token}"
    description = "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))
    title = c.titulo or "Video EcoFiver"

    try:
        async with httpx.AsyncClient(timeout=60) as hc:
            r = await hc.post(
                f"{META_GRAPH_URL}/{page_id}/videos",
                data={
                    "file_url": video_url,
                    "title": title[:100],
                    "description": description,
                    "access_token": page_token,
                },
            )
            if r.status_code != 200:
                err = r.json()
                raise HTTPException(400, f"Error Facebook Video: {err.get('error', {}).get('message', r.text[:200])}")

        post_id = r.json().get("id")
        redes_pub = json.loads(getattr(c, "redes_publicadas", None) or "{}")
        redes_pub["facebook_video"] = datetime.now().isoformat()
        c.redes_publicadas = json.dumps(redes_pub)
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        db.commit()
        return {"ok": True, "red": "facebook_video", "post_id": post_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando video en Facebook: {str(e)[:150]}")


# ─── INSTAGRAM CAROUSEL ───────────────────────────────────────────────────────

class CarouselUrlsReq(BaseModel):
    urls: Optional[List[str]] = []    # URLs públicas de las imágenes (2-10)
    caption: Optional[str] = ""


@router.post("/api/ecopost/{item_id}/publicar-ig-carousel")
async def api_publicar_ig_carousel(
    item_id: int,
    body: CarouselUrlsReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica un carrusel de imágenes en Instagram Business (2-10 imágenes)."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    page_token = get_config_value("meta_page_access_token", db)
    ig_user_id = get_config_value("meta_ig_user_id", db)
    if not page_token or not ig_user_id:
        raise HTTPException(400, "Configurar Meta Page Access Token e IG User ID en Configuración → Meta")

    urls = body.urls or []
    if not urls:
        # Intentar usar las carousel_urls guardadas en el contenido
        urls = json.loads(getattr(c, "carousel_urls", None) or "[]")
    if len(urls) < 2:
        raise HTTPException(400, "El carrusel necesita al menos 2 URLs de imágenes")
    urls = urls[:10]

    caption = body.caption or "\n\n".join(filter(None, [c.copy_texto, c.copy_hashtags]))

    try:
        async with httpx.AsyncClient(timeout=60) as hc:
            # Paso 1: crear container para cada imagen
            child_ids = []
            for img_url in urls:
                r_child = await hc.post(
                    f"{META_GRAPH_URL}/{ig_user_id}/media",
                    data={
                        "image_url": img_url,
                        "is_carousel_item": "true",
                        "access_token": page_token,
                    },
                )
                if r_child.status_code != 200:
                    err = r_child.json()
                    raise HTTPException(400, f"Error item carrusel: {err.get('error', {}).get('message', r_child.text[:150])}")
                child_ids.append(r_child.json().get("id"))

            # Paso 2: container del carrusel
            r_car = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media",
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_ids),
                    "caption": caption,
                    "access_token": page_token,
                },
            )
            if r_car.status_code != 200:
                err = r_car.json()
                raise HTTPException(400, f"Error carrusel container: {err.get('error', {}).get('message', r_car.text[:200])}")

            carousel_id = r_car.json().get("id")

            # Paso 3: publicar
            r_pub = await hc.post(
                f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
                data={"creation_id": carousel_id, "access_token": page_token},
            )
            if r_pub.status_code != 200:
                err = r_pub.json()
                raise HTTPException(400, f"Error publicando carrusel: {err.get('error', {}).get('message', r_pub.text[:200])}")

        ig_media_id = r_pub.json().get("id")
        redes_pub = json.loads(getattr(c, "redes_publicadas", None) or "{}")
        redes_pub["instagram_carousel"] = datetime.now().isoformat()
        c.redes_publicadas = json.dumps(redes_pub)
        c.estado = "publicado"
        if not c.aprobado_por_id:
            c.aprobado_por_id = user.id
        db.commit()
        return {"ok": True, "red": "instagram_carousel", "ig_media_id": ig_media_id, "items": len(child_ids)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Error publicando carrusel: {str(e)[:150]}")


# ─── BULK PUBLICAR ────────────────────────────────────────────────────────────

class BulkPublicarReq(BaseModel):
    ids: List[int]
    redes: List[str]   # "facebook" | "instagram"


@router.post("/api/ecopost/bulk-publicar")
async def api_bulk_publicar(
    body: BulkPublicarReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Publica múltiples contenidos en simultáneo a las redes seleccionadas."""
    if not body.ids:
        raise HTTPException(400, "No hay IDs seleccionados")

    page_token = get_config_value("meta_page_access_token", db)
    page_id    = get_config_value("meta_page_id", db)
    ig_user_id = get_config_value("meta_ig_user_id", db)
    crm_host   = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"

    resultados = []
    for cid in body.ids:
        c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == cid).first()
        if not c:
            resultados.append({"id": cid, "ok": False, "error": "No encontrado"})
            continue

        message = "\n\n".join(filter(None, [c.copy_texto or "", c.copy_hashtags or ""]))
        img_url = c.imagen_url
        if not img_url and c.imagen_base64:
            try:
                tok = _ensure_public_token(c, db)
                img_url = f"{crm_host.rstrip('/')}/pub/img/{tok}"
                c.imagen_url = img_url
                db.flush()
            except Exception:
                pass

        item_res: dict = {"id": cid, "titulo": c.titulo or "(sin título)", "redes": {}}

        async with httpx.AsyncClient(timeout=20) as hc:
            for red in body.redes:
                try:
                    if red == "facebook" and page_token and page_id:
                        page_obj = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
                        pt = (page_obj.page_token if page_obj and page_obj.page_token else None) or page_token
                        if img_url:
                            r = await hc.post(
                                f"{META_GRAPH_URL}/{page_id}/photos",
                                data={"url": img_url, "caption": message, "access_token": pt},
                            )
                        else:
                            r = await hc.post(
                                f"{META_GRAPH_URL}/{page_id}/feed",
                                data={"message": message, "access_token": pt},
                            )
                        ok = r.status_code == 200
                        item_res["redes"]["facebook"] = {
                            "ok": ok,
                            **({"post_id": r.json().get("id")} if ok else
                               {"error": r.json().get("error", {}).get("message", r.text[:100])}),
                        }

                    elif red == "instagram" and page_token and ig_user_id and img_url:
                        r1 = await hc.post(
                            f"{META_GRAPH_URL}/{ig_user_id}/media",
                            data={"image_url": img_url, "caption": message, "access_token": page_token},
                        )
                        if r1.status_code == 200:
                            r2 = await hc.post(
                                f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
                                data={"creation_id": r1.json().get("id"), "access_token": page_token},
                            )
                            ok2 = r2.status_code == 200
                            item_res["redes"]["instagram"] = {
                                "ok": ok2,
                                **({"ig_media_id": r2.json().get("id")} if ok2 else
                                   {"error": r2.json().get("error", {}).get("message", r2.text[:100])}),
                            }
                        else:
                            item_res["redes"]["instagram"] = {"ok": False, "error": r1.json().get("error", {}).get("message", r1.text[:100])}
                    else:
                        item_res["redes"][red] = {"ok": False, "error": "Config incompleta o sin imagen"}
                except Exception as e:
                    item_res["redes"][red] = {"ok": False, "error": str(e)[:100]}

        any_ok = any(v.get("ok") for v in item_res["redes"].values())
        if any_ok:
            c.estado = "publicado"
            if not c.aprobado_por_id:
                c.aprobado_por_id = user.id
            db.commit()
        item_res["ok"] = any_ok
        resultados.append(item_res)

    return {"ok": True, "resultados": resultados, "total": len(resultados)}


# ─── CONTENIDO PROGRAMADO ─────────────────────────────────────────────────────

async def _auto_publicar_programados():
    """Scheduler job: publica en Facebook los contenidos 'aprobados' cuya hora ya pasó."""
    try:
        from database.database import SessionLocal
        db = SessionLocal()
        ahora = datetime.now()
        pendientes = (
            db.query(ContenidoEcopost)
            .filter(
                ContenidoEcopost.publish_at.isnot(None),
                ContenidoEcopost.publish_at <= ahora,
                ContenidoEcopost.estado == "aprobado",
            )
            .all()
        )
        if not pendientes:
            db.close()
            return

        page_token = get_config_value("meta_page_access_token", db)
        page_id    = get_config_value("meta_page_id", db)
        crm_host   = get_config_value("crm_public_url", db) or "https://eco-crm-production.up.railway.app"

        for c in pendientes:
            try:
                message = "\n\n".join(filter(None, [c.copy_texto or "", c.copy_hashtags or ""]))
                img_url = c.imagen_url
                if not img_url and c.imagen_base64:
                    tok = _ensure_public_token(c, db)
                    img_url = f"{crm_host.rstrip('/')}/pub/img/{tok}"
                    c.imagen_url = img_url
                    db.flush()

                if page_token and page_id:
                    async with httpx.AsyncClient(timeout=20) as hc:
                        if img_url:
                            r = await hc.post(
                                f"{META_GRAPH_URL}/{page_id}/photos",
                                data={"url": img_url, "caption": message, "access_token": page_token},
                            )
                        else:
                            r = await hc.post(
                                f"{META_GRAPH_URL}/{page_id}/feed",
                                data={"message": message, "access_token": page_token},
                            )
                        if r.status_code == 200:
                            c.estado = "publicado"
                            c.publish_at = None
                            db.commit()
                            logger.info(f"[scheduler] Ecopost #{c.id} publicado automáticamente")
                        else:
                            logger.warning(f"[scheduler] Ecopost #{c.id} falló: {r.text[:150]}")
            except Exception as e:
                logger.error(f"[scheduler] Error publicando Ecopost #{c.id}: {e}")

        db.close()
    except Exception as e:
        logger.error(f"[scheduler] _auto_publicar_programados: {e}")


# ─── SCRIPT PARA VIDEO (TikTok / YouTube) ────────────────────────────────────

class GenerarScriptReq(BaseModel):
    plataforma: str = "tiktok"     # tiktok | youtube | youtube_shorts
    duracion_seg: int = 30          # 15 | 30 | 60 | 180 | 600
    formato: Optional[str] = "tutorial"   # tutorial | testimonial | demo | educativo


@router.post("/api/ecopost/{item_id}/generar-script")
async def api_generar_script(
    item_id: int,
    body: GenerarScriptReq,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Genera un guión de video con IA, adaptado a TikTok o YouTube."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    plat_desc = {
        "tiktok":          "TikTok — vertical 9:16, hook en los primeros 3 segundos, ritmo rápido, lenguaje joven",
        "youtube":         "YouTube — horizontal 16:9, intro con hook, desarrollo, CTA al final",
        "youtube_shorts":  "YouTube Shorts — vertical 9:16, menos de 60 segundos",
    }
    plat = plat_desc.get(body.plataforma, body.plataforma)
    producto = c.producto or "piscinas de fibra de vidrio EcoFiver"
    copy_base = c.copy_texto or ""

    dim_ctx = ""
    for key, desc in _DIMENSIONES_PRODUCTO.items():
        if key in producto.upper():
            dim_ctx = desc
            break

    prompt = f"""{ctx_empresa()}

════════════════════════════════════════════
GUIÓN DE VIDEO — {body.plataforma.upper()}
════════════════════════════════════════════
Plataforma: {plat}
Producto: {producto}
{f"Características: {dim_ctx}" if dim_ctx else ""}
Duración: {body.duracion_seg} segundos
Formato: {body.formato}
Copy disponible: {copy_base[:200] if copy_base else "ninguno"}

Escribí en castellano argentino rioplatense. Responder con este formato exacto:

TITULO_VIDEO: [título, max 70 chars]
DESCRIPCION_YT: [descripción YouTube con SEO, 150 palabras — solo para youtube]
TAGS: [10 tags separados por coma]
GUION:
[00:00] Hook: texto que dice el presentador
[00:05] escena, texto en pantalla y descripción visual
...
[FIN] CTA: llamada a la acción
NOTAS_PRODUCCION: indicaciones técnicas (luz, música, transiciones)"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=2000, temperature=0.7)
        # Parsear respuesta
        titulo_video, descripcion_yt, tags, guion, notas = "", "", "", "", ""
        section = None
        for line in respuesta.split("\n"):
            s = line.strip()
            if s.startswith("TITULO_VIDEO:"):
                titulo_video = s[13:].strip(); section = None
            elif s.startswith("DESCRIPCION_YT:"):
                descripcion_yt = s[15:].strip(); section = "desc"
            elif s.startswith("TAGS:"):
                tags = s[5:].strip(); section = None
            elif s.startswith("GUION:"):
                section = "guion"
            elif s.startswith("NOTAS_PRODUCCION:"):
                notas = s[17:].strip(); section = "notas"
            elif section == "guion":
                guion += line + "\n"
            elif section == "desc":
                descripcion_yt += "\n" + line
            elif section == "notas":
                notas += "\n" + line

        c.subtitulos = guion.strip()
        db.commit()

        return {
            "ok": True,
            "plataforma": body.plataforma,
            "titulo_video": titulo_video,
            "descripcion_yt": descripcion_yt.strip(),
            "tags": tags,
            "guion": guion.strip(),
            "notas_produccion": notas.strip(),
        }
    except Exception as e:
        raise HTTPException(502, f"Error generando guión: {str(e)[:150]}")


# ─── VARIACIONES A/B DE COPY ─────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/variaciones-copy")
async def api_variaciones_copy(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Genera 3 variaciones A/B del copy con enfoques diferentes para testear conversión."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    copy_original = c.copy_texto or ""
    producto = c.producto or "EcoFiver"
    tipo = c.tipo or "flyer"

    prompt = f"""{ctx_redes_sociales(tipo_contenido=tipo, producto=producto)}

════════════════════════════════════════════
VARIACIONES A/B DE COPY
════════════════════════════════════════════
Copy original: {copy_original}
Producto: {producto}
Tipo: {tipo}
Hashtags actuales: {c.copy_hashtags or ""}

Generá 3 variaciones con enfoque diferente:
- A: BENEFICIO EMOCIONAL (la vida que tendrías con el producto)
- B: URGENCIA (cupos limitados, temporada, última unidad)
- C: PRUEBA SOCIAL (resultado real, dato concreto, cliente satisfecho)

Respondé SOLO con este JSON válido:
{{"variaciones": [
  {{"id": "A", "enfoque": "Beneficio emocional", "copy": "...", "hashtags": "..."}},
  {{"id": "B", "enfoque": "Urgencia", "copy": "...", "hashtags": "..."}},
  {{"id": "C", "enfoque": "Prueba social", "copy": "...", "hashtags": "..."}}
]}}"""

    try:
        respuesta = await ai_complete(db, prompt, max_tokens=1500, temperature=0.75)
        respuesta = respuesta.strip()
        if "```json" in respuesta:
            respuesta = respuesta.split("```json")[1].split("```")[0].strip()
        elif "```" in respuesta:
            respuesta = respuesta.split("```")[1].split("```")[0].strip()
        data = json.loads(respuesta)
        return {"ok": True, "variaciones": data.get("variaciones", []), "copy_original": copy_original}
    except json.JSONDecodeError:
        raise HTTPException(502, "IA devolvió formato inválido. Intentá de nuevo.")
    except Exception as e:
        raise HTTPException(502, f"Error generando variaciones: {str(e)[:150]}")


# ─── DUPLICAR CONTENIDO ───────────────────────────────────────────────────────

@router.post("/api/ecopost/{item_id}/duplicar")
async def api_duplicar(
    item_id: int,
    user: Usuario = Depends(_require_access),
    db: Session = Depends(get_db),
):
    """Crea una copia de un contenido como nuevo borrador."""
    c = db.query(ContenidoEcopost).filter(ContenidoEcopost.id == item_id).first()
    if not c:
        raise HTTPException(404, "Contenido no encontrado")

    nuevo = ContenidoEcopost(
        titulo=f"[COPIA] {c.titulo or ''}",
        tipo=c.tipo,
        media_type=getattr(c, "media_type", "photo") or "photo",
        producto=c.producto,
        modelo_especifico=c.modelo_especifico,
        copy_texto=c.copy_texto,
        copy_hashtags=c.copy_hashtags,
        subtitulos=getattr(c, "subtitulos", "") or "",
        imagen_prompt=c.imagen_prompt,
        imagen_base64=c.imagen_base64,
        imagen_url=c.imagen_url,
        carousel_urls=getattr(c, "carousel_urls", "[]") or "[]",
        notas=c.notas,
        estado="borrador",
        creado_por_id=user.id,
        # No copiar: video_token, public_token, publish_at — el clon empieza fresco
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"ok": True, "id": nuevo.id, "item": _content_dict(nuevo)}
