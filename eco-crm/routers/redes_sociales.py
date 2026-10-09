"""
Panel unificado de gestión de redes sociales.
Endpoints: /redes (HTML) + /api/redes/...
"""
import logging
import time
import os
import asyncio
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db, SessionLocal
from database.models import MetaPagina, Usuario, FacebookInteraccion, ConfiguracionSistema
from database.encryption import encrypt_value
from routers.auth import require_auth, get_user_roles
from routers.configuracion import get_config_value
from routers.ecopost import META_GRAPH_URL

router = APIRouter()
templates = Jinja2Templates(directory="templates")
log = logging.getLogger(__name__)


def _check_access(user: Usuario, db: Session):
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin acceso al panel de redes sociales")
    return roles


async def _meta_get(url: str, params: dict, timeout: int = 20) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.get(url, params=params)
    body = r.json() if r.content else {}
    # Meta sometimes returns HTTP 200 with {"error": {...}} body
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", r.text[:250]))
    return body


# ─── HTML PAGE ────────────────────────────────────────────────────────────────

@router.get("/redes", response_class=HTMLResponse)
async def redes_page(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    roles = _check_access(user, db)
    return templates.TemplateResponse("redes_sociales.html", {
        "request": request,
        "user": user,
        "roles": roles,
    })


# ─── PÁGINAS ──────────────────────────────────────────────────────────────────

@router.get("/api/redes/admin/paginas")
async def api_redes_admin_paginas(
    t: str = "",
    db: Session = Depends(get_db),
):
    """Lista todas las páginas con su estado. Requiere ?t=<ML_AUDIT_TOKEN>."""
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    paginas = db.query(MetaPagina).order_by(MetaPagina.nombre).all()
    return [
        {
            "page_id": p.page_id,
            "nombre": p.nombre,
            "numero_whatsapp": p.numero_whatsapp or "",
            "tiene_token": bool(p.page_token),
            "webhook_subscribed": bool(p.webhook_subscribed),
            "activa": bool(p.activa),
            "auto_reply_mensajes": bool(p.auto_reply_mensajes),
            "auto_reply_comentarios": bool(p.auto_reply_comentarios),
            "auto_eliminar_negativos": bool(p.auto_eliminar_negativos),
            "vendedor": getattr(p, "vendedor", None) or "",
        }
        for p in paginas
    ]


@router.patch("/api/redes/admin/paginas/{page_id}")
async def api_redes_admin_patch_pagina(
    page_id: str,
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Actualiza campos de una página: numero_whatsapp, activa, vendedor.
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")

    if "numero_whatsapp" in body:
        numero = (body["numero_whatsapp"] or "").strip()
        pg.numero_whatsapp = numero or None
    if "activa" in body:
        pg.activa = bool(body["activa"])
    if "vendedor" in body:
        pg.vendedor = (body["vendedor"] or "").strip() or None

    db.commit()
    return {"ok": True, "page_id": page_id, "nombre": pg.nombre, "activa": pg.activa, "numero_whatsapp": pg.numero_whatsapp}


@router.post("/api/redes/admin/paginas/batch-auto-reply")
async def api_redes_admin_batch_auto_reply(
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Activa o desactiva auto_reply_mensajes / auto_reply_comentarios / auto_eliminar_negativos
    en todas las páginas activas (o en las indicadas).
    Body: {auto_reply_mensajes: bool, auto_reply_comentarios: bool, auto_eliminar_negativos: bool, page_ids: [...] opcional}
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    page_ids = body.get("page_ids")
    q = db.query(MetaPagina).filter(MetaPagina.activa == True)
    if page_ids:
        q = q.filter(MetaPagina.page_id.in_(page_ids))
    paginas = q.all()
    for campo in ("auto_reply_mensajes", "auto_reply_comentarios", "auto_eliminar_negativos"):
        if campo in body:
            for pg in paginas:
                setattr(pg, campo, bool(body[campo]))
    db.commit()
    return {"ok": True, "actualizadas": len(paginas)}


@router.post("/api/redes/admin/paginas/batch-deactivate")
async def api_redes_admin_batch_deactivate(
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Desactiva un conjunto de páginas: limpia numero_whatsapp y pone activa=False.
    Body: {page_ids: ["id1","id2",...]}
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    page_ids = body.get("page_ids") or []
    if not page_ids:
        raise HTTPException(400, "page_ids requerido")

    resultados = []
    for pid in page_ids:
        pg = db.query(MetaPagina).filter(MetaPagina.page_id == str(pid)).first()
        if not pg:
            resultados.append({"page_id": pid, "ok": False, "error": "no encontrada"})
            continue
        pg.numero_whatsapp = None
        pg.activa = False
        db.commit()
        resultados.append({"page_id": pid, "nombre": pg.nombre, "ok": True})

    desactivadas = sum(1 for r in resultados if r.get("ok"))
    return {"ok": True, "total": len(page_ids), "desactivadas": desactivadas, "resultados": resultados}


@router.delete("/api/redes/admin/paginas/{page_id}")
async def api_redes_admin_delete_pagina(
    page_id: str,
    t: str = "",
    db: Session = Depends(get_db),
):
    """Elimina una página y TODAS sus interacciones de la DB. Requiere ?t=<ML_AUDIT_TOKEN>."""
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")
    nombre = pg.nombre
    n_int = db.query(FacebookInteraccion).filter(FacebookInteraccion.page_id == page_id).delete()
    db.delete(pg)
    db.commit()
    return {"ok": True, "page_id": page_id, "nombre": nombre, "interacciones_eliminadas": n_int}


@router.get("/api/redes/paginas")
async def api_redes_paginas(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Lista páginas de la DB + fan_count y seguidores IG desde Meta."""
    _check_access(user, db)
    pages = db.query(MetaPagina).order_by(MetaPagina.nombre).all()

    token = get_config_value("meta_page_access_token", db)
    result = []

    def _pg_base(p):
        return {
            "page_id": p.page_id, "nombre": p.nombre,
            "portafolio": getattr(p, "portafolio", None) or "EcoFiver",
            "ig_user_id": p.ig_user_id, "activa": p.activa,
            "auto_reply_comentarios": bool(p.auto_reply_comentarios),
            "auto_reply_mensajes": bool(p.auto_reply_mensajes),
            "auto_eliminar_negativos": bool(p.auto_eliminar_negativos),
            "webhook_subscribed": bool(p.webhook_subscribed),
            "numero_whatsapp": p.numero_whatsapp or "",
            "vendedor": getattr(p, "vendedor", None) or "",
            "page_token_ok": bool(p.page_token),  # True si tiene token propio de página
            "fan_count": None, "ig_followers": None, "picture": None,
        }

    if not token:
        return [_pg_base(p) for p in pages]

    async with httpx.AsyncClient(timeout=15) as hc:
        for p in pages:
            item = _pg_base(p)
            try:
                r = await hc.get(
                    f"{META_GRAPH_URL}/{p.page_id}",
                    params={"fields": "fan_count,followers_count,picture.type(normal)", "access_token": token},
                )
                if r.status_code == 200:
                    d = r.json()
                    item["fan_count"] = d.get("fan_count") or d.get("followers_count")
                    pic_data = d.get("picture", {}).get("data", {})
                    item["picture"] = pic_data.get("url") if not pic_data.get("is_silhouette") else None
            except Exception:
                pass

            if p.ig_user_id:
                try:
                    r2 = await hc.get(
                        f"{META_GRAPH_URL}/{p.ig_user_id}",
                        params={"fields": "followers_count", "access_token": token},
                    )
                    if r2.status_code == 200:
                        item["ig_followers"] = r2.json().get("followers_count")
                except Exception:
                    pass

            result.append(item)

    return result


@router.patch("/api/redes/paginas/{page_id}")
async def api_redes_pagina_update(
    page_id: str,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Actualiza activa y/o ig_user_id de una página."""
    _check_access(user, db)
    body = await request.json()
    p = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not p:
        raise HTTPException(404, "Página no encontrada")
    if "activa" in body:
        p.activa = bool(body["activa"])
    if "ig_user_id" in body:
        p.ig_user_id = body["ig_user_id"] or None
    if "page_token" in body:
        p.page_token = (body["page_token"] or "").strip() or None
    if "nombre" in body:
        nombre = (body["nombre"] or "").strip()
        if nombre:
            p.nombre = nombre
    if "portafolio" in body:
        portafolio = (body["portafolio"] or "").strip()
        p.portafolio = portafolio or "EcoFiver"
    if "vendedor" in body:
        p.vendedor = (body["vendedor"] or "").strip() or None
    db.commit()
    return {
        "ok": True, "page_id": page_id,
        "activa": p.activa, "ig_user_id": p.ig_user_id,
        "page_token_ok": bool(p.page_token),
        "portafolio": getattr(p, "portafolio", None) or "EcoFiver",
        "vendedor": getattr(p, "vendedor", None) or "",
    }


# ─── FEED FACEBOOK ────────────────────────────────────────────────────────────

@router.get("/api/redes/paginas/{page_id}/feed")
async def api_redes_feed(
    page_id: str,
    after: Optional[str] = None,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Posts del feed de Facebook de una página. Usa page_token si está disponible."""
    _check_access(user, db)

    # Preferir page token específico (largo plazo), fallback al system user token
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    token = (pg.page_token if pg and pg.page_token else None) or get_config_value("meta_page_access_token", db)
    if not token:
        return {"posts": [], "has_next": False, "error": "Sin token de Meta configurado. Ir a Configuración → Meta."}

    params = {
        "fields": "id,message,story,created_time,full_picture,permalink_url,likes.summary(true),comments.summary(true),shares",
        "limit": "12",
        "access_token": token,
    }
    if after:
        params["after"] = after

    try:
        data = await _meta_get(f"{META_GRAPH_URL}/{page_id}/feed", params)
    except HTTPException as e:
        return {"posts": [], "has_next": False, "error": e.detail}
    except Exception as e:
        return {"posts": [], "has_next": False, "error": str(e)[:300]}

    paging = data.get("paging", {})
    return {
        "posts": [
            {
                "id": p.get("id"),
                "message": p.get("message") or p.get("story", ""),
                "created_time": p.get("created_time"),
                "picture": p.get("full_picture"),
                "permalink": p.get("permalink_url"),
                "likes": p.get("likes", {}).get("summary", {}).get("total_count", 0),
                "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
                "shares": p.get("shares", {}).get("count", 0),
            }
            for p in data.get("data", [])
        ],
        "next_cursor": paging.get("cursors", {}).get("after"),
        "has_next": bool(paging.get("next")),
    }


# ─── INSTAGRAM ────────────────────────────────────────────────────────────────

@router.get("/api/redes/paginas/{page_id}/ig")
async def api_redes_ig(
    page_id: str,
    after: Optional[str] = None,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Posts de Instagram Business vinculada a la página."""
    _check_access(user, db)
    p = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not p or not p.ig_user_id:
        return {"posts": [], "has_next": False, "error": "Sin Instagram Business Account vinculado a esta página"}

    token = (p.page_token if p.page_token else None) or get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Sin token de Meta configurado")

    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
        "limit": "18",
        "access_token": token,
    }
    if after:
        params["after"] = after

    try:
        data = await _meta_get(f"{META_GRAPH_URL}/{p.ig_user_id}/media", params)
    except HTTPException as e:
        return {"posts": [], "has_next": False, "error": e.detail}

    paging = data.get("paging", {})
    return {
        "posts": data.get("data", []),
        "next_cursor": paging.get("cursors", {}).get("after"),
        "has_next": bool(paging.get("next")),
        "ig_user_id": p.ig_user_id,
    }


# ─── ESTADÍSTICAS ─────────────────────────────────────────────────────────────

@router.get("/api/redes/paginas/{page_id}/stats")
async def api_redes_stats(
    page_id: str,
    periodo: str = "days_28",
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Métricas de la página desde Meta Insights. Devuelve {"error": "..."} en lugar de 400."""
    _check_access(user, db)

    # Insights requiere Page Access Token. Prioridad: page_token del sync → token global.
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    page_token = pg.page_token if pg and pg.page_token else None
    global_token = get_config_value("meta_page_access_token", db)

    # Intentar ambos tokens; el page_token va primero porque tiene read_insights garantizado
    tokens_a_probar = [t for t in [page_token, global_token] if t]
    if not tokens_a_probar:
        return {"error": "Sin token de Meta configurado. Ir a Configuración → Meta."}

    if periodo not in ("day", "week", "days_28"):
        periodo = "days_28"

    days_back = {"day": 1, "week": 7, "days_28": 28}.get(periodo, 28)
    now_ts = int(time.time())
    since_ts = now_ts - days_back * 86400

    # Fallback chain de métricas: v22.0+ elimina page_views_total
    metric_groups = [
        ["page_impressions", "page_reach", "page_total_actions"],
        ["page_impressions", "page_reach"],
        ["page_impressions"],
    ]

    last_error = None
    data = None

    for token in tokens_a_probar:
        base_params = {
            "period": "day",
            "since": since_ts,
            "until": now_ts,
            "access_token": token,
        }
        for group in metric_groups:
            try:
                data = await _meta_get(
                    f"{META_GRAPH_URL}/{page_id}/insights",
                    {"metric": ",".join(group), **base_params},
                )
                break
            except (HTTPException, Exception) as e:
                last_error = e.detail if isinstance(e, HTTPException) else str(e)[:300]
                data = None
        if data is not None:
            break  # salir del loop de tokens si ya funcionó

    if data is None:
        return {"error": last_error or "No se pudo obtener estadísticas"}

    result = {}
    for metric in data.get("data", []):
        name = metric.get("name")
        values = metric.get("values", [])
        result[name] = {
            "title": metric.get("title"),
            "total": sum(v.get("value", 0) for v in values),
            "values": [
                {"date": v.get("end_time", "")[:10], "value": v.get("value", 0)}
                for v in values
            ],
        }

    if not result:
        return {"error": "Sin datos de insights. Sincronizá las páginas y verificá que el token tenga permiso read_insights."}

    return result


# ─── ELIMINAR POST FACEBOOK ───────────────────────────────────────────────────

@router.delete("/api/redes/posts/{post_id:path}")
async def api_redes_delete_post(
    post_id: str,
    page_id: Optional[str] = None,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Elimina un post de Facebook. Solo ADMIN."""
    roles = _check_access(user, db)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar publicaciones")

    token = None
    pg_nombre = page_id or "desconocida"
    if page_id:
        pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
        if pg:
            pg_nombre = pg.nombre
            if pg.page_token:
                token = pg.page_token
    # Borrar posts requiere un Page Access Token específico — user/system tokens no sirven.
    # No hacer fallback al token global porque Facebook rechazará con "page token required".
    if not token:
        raise HTTPException(
            400,
            f'La página "{pg_nombre}" no tiene token de página configurado. '
            "Sincronizá las páginas en la pestaña Config → Conectar con Facebook, "
            "o pegá el Page Access Token manualmente en Config de la página."
        )

    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.delete(
            f"{META_GRAPH_URL}/{post_id}",
            params={"access_token": token},
        )

    if r.status_code not in (200, 204):
        err = r.json().get("error", {}) if r.content else {}
        raise HTTPException(400, err.get("message", r.text[:200] or "Error al eliminar"))

    result = r.json() if r.content else {}
    return {"ok": result.get("success", True)}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATIZACIÓN FACEBOOK — COMENTARIOS + MENSAJES + WEBHOOK
# ═══════════════════════════════════════════════════════════════════════════════

# Palabras que indican comentario negativo → candidato a eliminación
_PALABRAS_NEGATIVAS = {
    "estafa", "mentira", "fraude", "basura", "pésimo", "pesimo", "horrible",
    "mala calidad", "no compren", "cuidado", "robo", "engaño", "enganio", "timo",
    "mentirosos", "vergüenza", "verguenza", "denuncia", "scam", "fake",
    "chorros", "ladrones", "chanta", "no sirve", "arrepiento", "decepción",
    "decepcion", "decepcionante", "boludos", "idiotas", "estafadores",
    "mierda", "porquería", "porqueria", "inútil", "inutil", "inservible",
    "reclamo", "no recomiendo", "no recomend", "no lo compren",
}


_PALABRAS_RECLAMO = {
    "reclamo", "queja", "no funciona", "no funcionó", "no anda", "se rompió", "se rompio",
    "defecto", "falla", "fallo", "garantía", "garantia", "arreglo", "arreglar",
    "postventa", "post venta", "post-venta", "devolución", "devolucion", "reembolso",
    "estafa", "engaño", "engano", "mal servicio", "pésimo", "pesimo", "tardanza",
    "no llegó", "no llego", "no entregaron", "no recibí", "no recibi",
    "problema con", "inconveniente", "daño", "dano", "roto", "rajada", "rajado",
}

WA_RECLAMOS = os.getenv("WA_RECLAMOS", "+5491168733406")


def _es_negativo(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_NEGATIVAS)


def _es_reclamo(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_RECLAMO)


def _wa_url(numero: str) -> str:
    n = numero.strip().replace("+", "").replace("-", "").replace(" ", "")
    if not n.startswith("54"):
        n = "54" + n
    return f"https://wa.me/{n}"


async def _generar_respuesta_ia(mensaje_usuario: str, pagina_nombre: str, numero_wa: str, db=None) -> str:
    """Genera respuesta comercial con IA. Reclamos → WA_RECLAMOS, consultas → numero_wa."""
    es_reclamo = _es_reclamo(mensaje_usuario)
    wa_destino = WA_RECLAMOS if es_reclamo else (numero_wa or WA_RECLAMOS)

    if es_reclamo:
        instruccion_wa = (
            "El usuario parece tener un reclamo o problema postventa. "
            "Respondé con empatía, pedí disculpas por la molestia y derivalo al WhatsApp de atención postventa: "
            f"{_wa_url(wa_destino)} — incluidlo siempre."
        )
    else:
        instruccion_wa = (
            "Debés derivar al WhatsApp para continuar la conversación. "
            f"El link de WhatsApp es: {_wa_url(wa_destino)} — incluidlo siempre."
        )

    try:
        from utils.ai_client import ai_complete
        from utils.contexto_ecofiver import ctx_empresa
        prompt = (
            f"{ctx_empresa()}\n\n"
            f"Sos el asistente comercial de la página de Facebook '{pagina_nombre}'.\n"
            f"Un usuario escribió: «{mensaje_usuario[:300]}»\n\n"
            "Escribí UNA respuesta corta (máximo 3 oraciones), amigable y comercial en español argentino. "
            f"{instruccion_wa} "
            "No inventes precios ni fechas. Sé cálido, profesional y generá interés."
        )
        resp = await ai_complete(db, prompt, max_tokens=200)
        return resp.strip()
    except Exception as e:
        log.warning(f"IA falló, usando template: {e}")
        if es_reclamo:
            return (
                f"¡Hola! Lamentamos la situación. Para resolver tu caso lo antes posible "
                f"comunicate con nuestro equipo de atención postventa por WhatsApp: {_wa_url(wa_destino)}"
            )
        return (
            f"¡Hola! 😊 Gracias por tu mensaje. Para brindarte atención personalizada "
            f"comunicate con nosotros por WhatsApp: {_wa_url(wa_destino)} — ¡Te respondemos al instante!"
        )


async def _responder_comentario(comment_id: str, mensaje: str, token: str) -> bool:
    """Publica una respuesta a un comentario de Facebook."""
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.post(
                f"{META_GRAPH_URL}/{comment_id}/replies",
                params={"access_token": token},
                json={"message": mensaje},
            )
        return r.status_code in (200, 201)
    except Exception as e:
        log.error(f"Error respondiendo comentario {comment_id}: {e}")
        return False


async def _eliminar_comentario(comment_id: str, token: str) -> bool:
    """Elimina un comentario de Facebook."""
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.delete(
                f"{META_GRAPH_URL}/{comment_id}",
                params={"access_token": token},
            )
        return r.status_code in (200, 204)
    except Exception as e:
        log.error(f"Error eliminando comentario {comment_id}: {e}")
        return False


async def _responder_mensaje(sender_id: str, mensaje: str, token: str) -> bool:
    """Envía un mensaje privado vía Messenger."""
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.post(
                f"{META_GRAPH_URL}/me/messages",
                params={"access_token": token},
                json={"recipient": {"id": sender_id}, "message": {"text": mensaje}},
            )
        return r.status_code in (200, 201)
    except Exception as e:
        log.error(f"Error enviando mensaje a {sender_id}: {e}")
        return False


async def _procesar_evento_fb(entry: dict, db: Session):
    """Procesa un evento del webhook de Facebook (comentario o mensaje)."""
    page_id = entry.get("id", "")
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg or not pg.page_token:
        return

    numero_wa = pg.numero_whatsapp or ""

    # ── MENSAJES PRIVADOS (Messenger) ──────────────────────────────────────
    for msg_event in entry.get("messaging", []):
        sender_id = msg_event.get("sender", {}).get("id", "")
        if sender_id == page_id:
            continue  # ignorar eco del propio bot
        msg_text = msg_event.get("message", {}).get("text", "")
        if not msg_text:
            continue

        interaccion = FacebookInteraccion(
            page_id=page_id,
            tipo="mensaje",
            objeto_id=msg_event.get("message", {}).get("mid", ""),
            usuario_id=sender_id,
            usuario_nombre=sender_id,
            contenido=msg_text[:1000],
            sentimiento="negativo" if _es_negativo(msg_text) else "neutro",
            accion="pendiente",
        )
        db.add(interaccion)
        db.flush()

        if pg.auto_reply_mensajes:
            respuesta = await _generar_respuesta_ia(msg_text, pg.nombre, numero_wa, db)
            ok = await _responder_mensaje(sender_id, respuesta, pg.page_token)
            interaccion.accion = "respondido" if ok else "error"
            interaccion.respuesta_enviada = respuesta
        db.commit()

    # ── COMENTARIOS EN POSTS ───────────────────────────────────────────────
    for change in entry.get("changes", []):
        if change.get("field") not in ("feed", "comments"):
            continue
        val = change.get("value", {})
        if val.get("item") not in ("comment", "reply"):
            continue
        if val.get("verb") not in ("add",):
            continue

        comment_id = val.get("comment_id", "")
        post_id = val.get("post_id", "")
        from_info = val.get("from", {})
        autor_nombre = from_info.get("name", "")
        autor_id = from_info.get("id", "")
        msg_text = val.get("message", "")

        es_neg = _es_negativo(msg_text)
        interaccion = FacebookInteraccion(
            page_id=page_id,
            tipo="comentario",
            post_id=post_id,
            objeto_id=comment_id,
            usuario_id=autor_id,
            usuario_nombre=autor_nombre,
            contenido=msg_text[:1000],
            sentimiento="negativo" if es_neg else "neutro",
            accion="pendiente",
        )
        db.add(interaccion)
        db.flush()

        if es_neg and pg.auto_eliminar_negativos:
            ok = await _eliminar_comentario(comment_id, pg.page_token)
            interaccion.accion = "eliminado" if ok else "error"
        elif pg.auto_reply_comentarios:
            respuesta = await _generar_respuesta_ia(msg_text, pg.nombre, numero_wa, db)
            ok = await _responder_comentario(comment_id, respuesta, pg.page_token)
            interaccion.accion = "respondido" if ok else "error"
            interaccion.respuesta_enviada = respuesta

        db.commit()


# ─── WEBHOOK VERIFICACIÓN ─────────────────────────────────────────────────────

@router.get("/api/redes/facebook/webhook")
async def facebook_webhook_verify(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Endpoint de verificación del webhook de Facebook (GET).
    Facebook envía hub.mode=subscribe, hub.verify_token y hub.challenge.
    Responder con el challenge si el token coincide.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")

    verify_token = get_config_value("facebook_webhook_verify_token", db) or os.getenv("FB_WEBHOOK_VERIFY_TOKEN", "ecofiver-webhook-2026")

    if mode == "subscribe" and token == verify_token:
        log.info("[FB-WEBHOOK] Verificación exitosa")
        return PlainTextResponse(challenge)
    else:
        log.warning(f"[FB-WEBHOOK] Verificación fallida — token recibido: {token!r}")
        raise HTTPException(403, "Token inválido")


@router.post("/api/redes/facebook/webhook")
async def facebook_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Recibe eventos del webhook de Facebook (POST).
    Procesa comentarios y mensajes en background.
    Siempre responde 200 a Facebook inmediatamente.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    if body.get("object") != "page":
        return {"ok": True}

    async def _bg():
        _db = SessionLocal()
        try:
            for entry in body.get("entry", []):
                try:
                    await _procesar_evento_fb(entry, _db)
                except Exception as e:
                    log.error(f"[FB-WEBHOOK] Error procesando entry: {e}")
        finally:
            _db.close()

    background_tasks.add_task(_bg)
    return {"ok": True}


# ─── AUTOMATIZACIÓN MASIVA POR PORTAFOLIO / SELECCIÓN ────────────────────────

@router.post("/api/redes/paginas/bulk-automation")
async def api_redes_bulk_automation(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Activa/desactiva automatización en múltiples páginas a la vez."""
    _check_access(user, db)
    body = await request.json()

    page_ids   = body.get("page_ids") or []      # lista explícita (vacío = todos)
    portafolio = body.get("portafolio") or None   # filtrar por portafolio

    campos = {
        k: bool(v) for k, v in body.items()
        if k in ("auto_reply_comentarios", "auto_reply_mensajes", "auto_eliminar_negativos")
    }
    if not campos:
        raise HTTPException(400, "Indicá al menos un campo a actualizar")

    q = db.query(MetaPagina)
    if page_ids:
        q = q.filter(MetaPagina.page_id.in_(page_ids))
    elif portafolio:
        q = q.filter(MetaPagina.portafolio == portafolio)

    pages = q.all()
    for pg in pages:
        for campo, valor in campos.items():
            setattr(pg, campo, valor)
    db.commit()
    return {"ok": True, "updated": len(pages), "campos": campos}


# ─── SINCRONIZAR WHATSAPP DESDE META ─────────────────────────────────────────

@router.post("/api/redes/paginas/sync-whatsapp")
async def api_redes_sync_whatsapp(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Para cada página con page_token, consulta la Graph API buscando
    whatsapp_number y connected_instagram_account.whatsapp_number_id,
    y guarda el número en numero_whatsapp si estaba vacío.
    """
    _check_access(user, db)
    try:
        body = await request.json()
    except Exception:
        body = {}

    solo_vacias = body.get("solo_vacias", True)  # por defecto solo actualiza las que no tienen

    paginas = db.query(MetaPagina).filter(MetaPagina.activa == True).all()
    user_token = get_config_value("meta_page_access_token", db) or ""

    encontrados = []
    no_encontrados = []
    errores = []

    async with httpx.AsyncClient(timeout=20) as hc:
        for pg in paginas:
            if solo_vacias and pg.numero_whatsapp:
                continue  # ya tiene número, omitir

            token = pg.page_token or user_token
            if not token:
                no_encontrados.append({"page_id": pg.page_id, "nombre": pg.nombre, "razon": "sin token"})
                continue

            try:
                r = await hc.get(
                    f"{META_GRAPH_URL}/{pg.page_id}",
                    params={
                        "fields": "whatsapp_number,name",
                        "access_token": token,
                    },
                )
                if r.status_code != 200:
                    errores.append({"page_id": pg.page_id, "nombre": pg.nombre, "error": r.text[:120]})
                    continue

                data = r.json()
                wa = (data.get("whatsapp_number") or "").strip()

                if wa:
                    pg.numero_whatsapp = wa
                    encontrados.append({"page_id": pg.page_id, "nombre": pg.nombre, "whatsapp": wa})
                else:
                    no_encontrados.append({"page_id": pg.page_id, "nombre": pg.nombre, "razon": "no configurado en Meta"})

            except Exception as e:
                errores.append({"page_id": pg.page_id, "nombre": pg.nombre, "error": str(e)[:120]})

    db.commit()
    return {
        "ok": True,
        "encontrados": len(encontrados),
        "no_encontrados": len(no_encontrados),
        "errores": len(errores),
        "detalle": encontrados,
        "sin_numero": no_encontrados,
        "con_error": errores,
    }


# ─── LISTAR WHATSAPP BUSINESS ACCOUNTS DEL BM ────────────────────────────────

@router.get("/api/redes/whatsapp-business-accounts")
async def api_redes_waba_list(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Consulta el Business Manager para listar todos los WhatsApp Business Accounts
    y sus números de teléfono (los usados en Click-to-WhatsApp ads).
    """
    _check_access(user, db)
    token = get_config_value("meta_page_access_token", db) or ""
    if not token:
        raise HTTPException(400, "No hay token Meta configurado")

    resultados = []
    errores = []

    async with httpx.AsyncClient(timeout=30) as hc:
        # Listar WABAs del Business Manager
        r_waba = await hc.get(
            f"{META_GRAPH_URL}/{META_BUSINESS_ID}/whatsapp_business_accounts",
            params={
                "fields": "id,name,currency,timezone_id,message_template_namespace",
                "access_token": token,
                "limit": 50,
            },
        )
        if r_waba.status_code != 200:
            return {
                "ok": False,
                "error": "No se pudo consultar el BM",
                "detalle": r_waba.json(),
                "wabase": [],
            }

        wabas = r_waba.json().get("data", [])

        for waba in wabas:
            waba_id = waba.get("id")
            waba_info = {
                "waba_id": waba_id,
                "nombre": waba.get("name", ""),
                "currency": waba.get("currency", ""),
                "telefones": [],
            }

            # Obtener números de teléfono de cada WABA
            try:
                r_phones = await hc.get(
                    f"{META_GRAPH_URL}/{waba_id}/phone_numbers",
                    params={
                        "fields": "id,display_phone_number,verified_name,quality_rating,status,code_verification_status",
                        "access_token": token,
                        "limit": 50,
                    },
                )
                if r_phones.status_code == 200:
                    phones = r_phones.json().get("data", [])
                    waba_info["telefones"] = [
                        {
                            "phone_number_id": p.get("id"),
                            "display_phone_number": p.get("display_phone_number", ""),
                            "verified_name": p.get("verified_name", ""),
                            "quality_rating": p.get("quality_rating", ""),
                            "status": p.get("status", ""),
                        }
                        for p in phones
                    ]
                else:
                    errores.append({
                        "waba_id": waba_id,
                        "error": r_phones.text[:200],
                    })
            except Exception as e:
                errores.append({"waba_id": waba_id, "error": str(e)[:120]})

            resultados.append(waba_info)

    return {
        "ok": True,
        "total_wabas": len(resultados),
        "wabase": resultados,
        "errores": errores,
    }


# ─── ASIGNAR NÚMERO WABA A UNA PÁGINA ─────────────────────────────────────────

@router.post("/api/redes/paginas/asignar-waba")
async def api_redes_asignar_waba(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Asigna un número de teléfono WABA a una o varias páginas.
    Body: { "page_ids": ["id1",...], "numero_whatsapp": "+54911..." }
    O: { "all": true, "numero_whatsapp": "+54911..." } para todas las páginas.
    """
    _check_access(user, db)
    body = await request.json()
    # Permite vaciar el número pasando null o ""
    numero_raw = body.get("numero_whatsapp")
    numero = None if numero_raw is None else str(numero_raw).strip()
    if numero is not None and numero == "" and not body.get("clear"):
        raise HTTPException(400, "Falta numero_whatsapp (o pasá clear:true para vaciar)")

    page_ids = body.get("page_ids") or []
    all_pages = body.get("all", False)

    q = db.query(MetaPagina)
    if not all_pages:
        if not page_ids:
            raise HTTPException(400, "Falta page_ids o all=true")
        q = q.filter(MetaPagina.page_id.in_(page_ids))

    paginas = q.all()
    for pg in paginas:
        pg.numero_whatsapp = numero or None
    db.commit()

    return {"ok": True, "updated": len(paginas), "numero_whatsapp": numero}


# ─── CONFIGURAR AUTOMATIZACIÓN POR PÁGINA ─────────────────────────────────────

@router.patch("/api/redes/paginas/{page_id}/automation")
async def api_redes_automation_config(
    page_id: str,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Actualiza la configuración de automatización de una página."""
    _check_access(user, db)
    body = await request.json()
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")

    for campo in ("auto_reply_comentarios", "auto_reply_mensajes", "auto_eliminar_negativos"):
        if campo in body:
            setattr(pg, campo, bool(body[campo]))
    if "numero_whatsapp" in body:
        pg.numero_whatsapp = (body["numero_whatsapp"] or "").strip() or None
    if "vendedor" in body:
        pg.vendedor = (body["vendedor"] or "").strip() or None

    db.commit()
    return {
        "ok": True,
        "page_id": page_id,
        "auto_reply_comentarios": pg.auto_reply_comentarios,
        "auto_reply_mensajes": pg.auto_reply_mensajes,
        "auto_eliminar_negativos": pg.auto_eliminar_negativos,
        "numero_whatsapp": pg.numero_whatsapp,
        "vendedor": getattr(pg, "vendedor", None) or "",
    }


# ─── SUSCRIBIR PÁGINA AL WEBHOOK ──────────────────────────────────────────────

@router.post("/api/redes/paginas/{page_id}/subscribe-webhook")
async def api_redes_subscribe_webhook(
    page_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Suscribe la página a los eventos de webhook (feed + messages).
    Requiere que el page_token tenga permisos pages_manage_engagement y pages_messaging.
    """
    _check_access(user, db)
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")

    # Usar page_token propio, o el token global de config como fallback
    token_a_usar = pg.page_token or get_config_value("meta_page_access_token", db) or ""
    if not token_a_usar:
        raise HTTPException(400, "Esta página no tiene page_token cargado y no hay meta_page_access_token global")

    resultados = {}
    async with httpx.AsyncClient(timeout=20) as hc:
        # Suscribir a feed (comentarios) y messages (DMs)
        r = await hc.post(
            f"{META_GRAPH_URL}/{page_id}/subscribed_apps",
            params={
                "access_token": token_a_usar,
                "subscribed_fields": "feed,messages,message_reactions",
            },
        )
        resultados["subscribed_apps"] = r.json()

    if resultados["subscribed_apps"].get("success"):
        pg.webhook_subscribed = True
        db.commit()

    return {
        "ok": resultados["subscribed_apps"].get("success", False),
        "page_id": page_id,
        "detalle": resultados,
    }


# ─── AUDIT: REFRESCAR TOKEN Y SUSCRIBIR WEBHOOK CON USER TOKEN ────────────────

@router.post("/api/redes/audit/refresh-and-subscribe")
async def api_redes_audit_refresh_subscribe(
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Endpoint de auditoría:
    1. Recibe un user_access_token del Graph API Explorer (con scopes correctos)
    2. Para cada page_id en la lista (o para todos en la DB), extrae el page_token
       via GET /{page_id}?fields=access_token usando el user_token
    3. Actualiza el page_token en la DB
    4. Llama a POST /{page_id}/subscribed_apps?subscribed_fields=feed,messages,message_reactions
    5. Devuelve el resultado

    Body JSON: { "user_token": "...", "page_ids": ["id1", "id2"] }
    Si page_ids está vacío, usa todos los registros de meta_paginas.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    user_token = (body.get("user_token") or "").strip()
    page_ids = body.get("page_ids") or []

    # Fallback: usar el token global de la configuración si no se pasa user_token
    if not user_token:
        user_token = get_config_value("meta_page_access_token", db) or ""
    if not user_token:
        raise HTTPException(400, "Falta 'user_token' en el body y no hay meta_page_access_token en configuración")

    # Si no se especifican páginas, procesar todas las de la DB
    if page_ids:
        paginas = db.query(MetaPagina).filter(MetaPagina.page_id.in_(page_ids)).all()
    else:
        paginas = db.query(MetaPagina).all()

    if not paginas:
        return {"ok": False, "error": "No hay páginas en la DB"}

    # Pre-cargar todos los page tokens via /me/accounts (incluye páginas del Business Manager)
    tokens_por_pagina: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        after = None
        for _ in range(10):  # max 10 páginas de paginación
            params: dict = {"fields": "id,access_token,name", "access_token": user_token, "limit": 50}
            if after:
                params["after"] = after
            r_acc = await hc.get(f"{META_GRAPH_URL}/me/accounts", params=params)
            if r_acc.status_code == 200:
                acc_data = r_acc.json()
                for item in acc_data.get("data", []):
                    if item.get("access_token"):
                        tokens_por_pagina[item["id"]] = item["access_token"]
                after = acc_data.get("paging", {}).get("cursors", {}).get("after")
                if not after or not acc_data.get("data"):
                    break
            else:
                break

    resultados = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        for pg in paginas:
            pid = pg.page_id
            resultado_pg = {}

            # 1) Obtener page token: primero /me/accounts, luego /{page_id}?fields=access_token
            page_token = tokens_por_pagina.get(pid)
            if not page_token:
                r_pt = await hc.get(
                    f"{META_GRAPH_URL}/{pid}",
                    params={"fields": "access_token,name", "access_token": user_token},
                )
                if r_pt.status_code == 200 and "access_token" in r_pt.json():
                    page_token = r_pt.json()["access_token"]
                    resultado_pg["page_name"] = r_pt.json().get("name", pid)
            else:
                resultado_pg["page_name"] = pid

            if not page_token:
                resultado_pg["error_token"] = "No se pudo obtener token de página"
                resultados[pid] = resultado_pg
                continue

            resultado_pg["token_ok"] = True

            # 2) Actualizar token en DB
            pg.page_token = page_token
            db.commit()
            resultado_pg["token_actualizado"] = True

            # 3) Suscribir al webhook
            r_sub = await hc.post(
                f"{META_GRAPH_URL}/{pid}/subscribed_apps",
                params={
                    "access_token": page_token,
                    "subscribed_fields": "feed,messages,message_reactions",
                },
            )
            resultado_pg["subscribed_apps"] = r_sub.json()

            if r_sub.json().get("success"):
                pg.webhook_subscribed = True
                db.commit()

            resultados[pid] = resultado_pg

    all_ok = all(r.get("subscribed_apps", {}).get("success") for r in resultados.values())
    return {"ok": all_ok, "resultados": resultados}


# ─── SUSCRIBIR TODAS LAS PÁGINAS (usa page_tokens ya guardados) ───────────────

@router.post("/api/redes/admin/subscribe-all")
async def api_redes_admin_subscribe_all(
    t: str = "",
    db: Session = Depends(get_db),
):
    """Suscribe todas las páginas con token al webhook. Requiere query param ?t=<ML_AUDIT_TOKEN>."""
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    paginas = db.query(MetaPagina).filter(
        MetaPagina.page_token != None, MetaPagina.page_token != ""
    ).all()
    if not paginas:
        return {"ok": False, "error": "No hay páginas con token"}

    global_token = get_config_value("meta_page_access_token", db) or ""

    resultados = {}
    async with httpx.AsyncClient(timeout=20) as hc:
        for pg in paginas:
            token_a_usar = pg.page_token
            r = await hc.post(
                f"{META_GRAPH_URL}/{pg.page_id}/subscribed_apps",
                params={"access_token": token_a_usar, "subscribed_fields": "feed,messages,message_reactions"},
            )
            body = r.json()
            ok = body.get("success", False)

            # Fallback: si falla por permisos (error 200) y hay token global distinto, intentar con él
            if not ok and body.get("error", {}).get("code") == 200 and global_token and global_token != token_a_usar:
                r2 = await hc.post(
                    f"{META_GRAPH_URL}/{pg.page_id}/subscribed_apps",
                    params={"access_token": global_token, "subscribed_fields": "feed,messages,message_reactions"},
                )
                body2 = r2.json()
                if body2.get("success"):
                    body = body2
                    ok = True

            if ok:
                pg.webhook_subscribed = True
            resultados[pg.page_id] = {"nombre": pg.nombre, "ok": ok, "detalle": body}
    db.commit()
    return {"ok": all(v["ok"] for v in resultados.values()), "resultados": resultados}


# ─── SUSCRIBIR TODAS USANDO TOKEN DE SISTEMA (app_id|app_secret) ───────────────

META_BUSINESS_ID = "753481671171165"
META_SYSTEM_USER_ID = "61573476584460"

@router.post("/api/redes/admin/subscribe-via-system-token")
async def api_redes_admin_subscribe_via_system_token(
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Genera un token para el System User 'fly' usando el token de admin del Business Manager
    (Julian, que es BM admin), luego suscribe todas las páginas al webhook.
    Body JSON opcional: { "user_token": "EAAB..." }
    Si no se provee user_token, intenta usar el token global almacenado en config.
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    import hmac as _hmac
    import hashlib as _hashlib

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    app_id = get_config_value("meta_app_id", db) or os.getenv("META_APP_ID", "")
    app_secret = get_config_value("meta_app_secret", db) or os.getenv("META_APP_SECRET", "")
    if not app_id or not app_secret:
        raise HTTPException(400, "Faltan meta_app_id o meta_app_secret en configuración")

    # Token del admin humano del Business Manager (Julian)
    admin_token = (body.get("user_token") or "").strip()
    if not admin_token:
        admin_token = get_config_value("meta_page_access_token", db) or ""
    if not admin_token:
        raise HTTPException(400, "Falta 'user_token' en el body. Hacer OAuth primero.")

    appsecret_proof = _hmac.new(app_secret.encode(), admin_token.encode(), _hashlib.sha256).hexdigest()

    async with httpx.AsyncClient(timeout=30) as hc:
        # 1) Generar token para el system user 'fly' usando el token del admin del BM
        r_st = await hc.post(
            f"{META_GRAPH_URL}/{META_BUSINESS_ID}/system_user_access_tokens",
            params={
                "access_token": admin_token,
                "appsecret_proof": appsecret_proof,
                "system_user_id": META_SYSTEM_USER_ID,
                "scope": "pages_manage_metadata,pages_messaging,pages_read_engagement,pages_show_list",
            },
        )
        if r_st.status_code != 200 or "access_token" not in r_st.json():
            return {"ok": False, "error": "No se pudo generar token de system user", "detalle": r_st.json()}

        system_token = r_st.json()["access_token"]

        # Guardar el system user token en config como meta_page_access_token (permanente)
        stored = encrypt_value(system_token)
        entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "meta_page_access_token").first()
        if entry:
            entry.valor = stored
        else:
            db.add(ConfiguracionSistema(clave="meta_page_access_token", valor=stored, es_secreto=True, categoria="meta"))
        db.commit()

        # 2) Obtener page tokens del system user vía /me/accounts
        tokens_por_pagina: dict[str, str] = {}
        after = None
        for _ in range(10):
            params: dict = {"fields": "id,access_token,name", "access_token": system_token, "limit": 50}
            if after:
                params["after"] = after
            r_acc = await hc.get(f"{META_GRAPH_URL}/me/accounts", params=params)
            if r_acc.status_code == 200:
                acc_data = r_acc.json()
                for item in acc_data.get("data", []):
                    if item.get("access_token"):
                        tokens_por_pagina[item["id"]] = item["access_token"]
                after = acc_data.get("paging", {}).get("cursors", {}).get("after")
                if not after or not acc_data.get("data"):
                    break
            else:
                break

        paginas = db.query(MetaPagina).all()
        resultados = {}
        for pg in paginas:
            pid = pg.page_id
            page_token = tokens_por_pagina.get(pid)
            if not page_token:
                resultados[pid] = {"nombre": pg.nombre, "ok": False, "error": "Sin token de system user para esta página"}
                continue

            pg.page_token = page_token
            r_sub = await hc.post(
                f"{META_GRAPH_URL}/{pid}/subscribed_apps",
                params={"access_token": page_token, "subscribed_fields": "feed,messages,message_reactions"},
            )
            body = r_sub.json()
            ok = body.get("success", False)
            if ok:
                pg.webhook_subscribed = True
            resultados[pid] = {"nombre": pg.nombre, "ok": ok, "detalle": body}

    db.commit()
    return {
        "ok": all(v["ok"] for v in resultados.values()),
        "pages_found_in_system_user": len(tokens_por_pagina),
        "resultados": resultados,
    }


@router.post("/api/redes/admin/sync-pages")
async def api_redes_admin_sync_pages(
    t: str = "",
    user_token: str = "",
    db: Session = Depends(get_db),
):
    """
    Descubre páginas vía GET /me/accounts, crea las que no existen en DB,
    obtiene page tokens, suscribe webhooks y activa auto_reply_mensajes.
    Requiere ?t=<ML_AUDIT_TOKEN>&user_token=<token>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    creadas = []
    actualizadas = []
    errores = []

    # ── Modo A: con user_token → descubrir/actualizar páginas en Facebook ────
    if user_token:
        app_id = get_config_value("meta_app_id", db) or os.getenv("META_APP_ID", "")
        app_secret = get_config_value("meta_app_secret", db) or os.getenv("META_APP_SECRET", "")

        # Intentar canjear por token de larga duración (60 días → page tokens permanentes)
        long_token = user_token
        if app_id and app_secret:
            async with httpx.AsyncClient(timeout=15) as hc:
                r_lt = await hc.get(
                    "https://graph.facebook.com/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "fb_exchange_token": user_token,
                    },
                )
                if r_lt.status_code == 200:
                    long_token = r_lt.json().get("access_token", user_token)

        # Guardar en config (el token de larga duración si pudo, si no el original)
        stored = encrypt_value(long_token)
        entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "meta_page_access_token").first()
        if entry:
            entry.valor = stored
        else:
            db.add(ConfiguracionSistema(clave="meta_page_access_token", valor=stored, es_secreto=True, categoria="meta"))
        db.commit()

        async with httpx.AsyncClient(timeout=60) as hc:
            r = await hc.get(
                f"{META_GRAPH_URL}/me/accounts",
                params={"fields": "id,name", "limit": 200, "access_token": long_token},
            )
            data = r.json()
            if r.status_code != 200 or "error" in data:
                raise HTTPException(400, data.get("error", {}).get("message", "Error al obtener páginas"))

            for p in data.get("data", []):
                pid, nombre = p["id"], p["name"]
                r_pt = await hc.get(
                    f"{META_GRAPH_URL}/{pid}",
                    params={"fields": "access_token", "access_token": long_token},
                )
                data_pt = r_pt.json()
                if r_pt.status_code != 200 or "access_token" not in data_pt:
                    errores.append({"page_id": pid, "nombre": nombre, "error": data_pt.get("error", {}).get("message", "sin token")})
                    continue
                page_token = data_pt["access_token"]
                pg = db.query(MetaPagina).filter(MetaPagina.page_id == pid).first()
                es_nueva = pg is None
                if es_nueva:
                    pg = MetaPagina(
                        page_id=pid, nombre=nombre, activa=True,
                        auto_reply_mensajes=True, auto_reply_comentarios=False,
                        auto_eliminar_negativos=True,
                        numero_whatsapp=os.getenv("WA_DEFAULT", "+5491126036495"),
                    )
                    db.add(pg)
                pg.page_token = page_token
                r_sub = await hc.post(
                    f"{META_GRAPH_URL}/{pid}/subscribed_apps",
                    params={"access_token": page_token, "subscribed_fields": "feed,messages,message_reactions"},
                )
                if r_sub.json().get("success"):
                    pg.webhook_subscribed = True
                db.flush()
                (creadas if es_nueva else actualizadas).append({"page_id": pid, "nombre": nombre})

        db.commit()
        total = len(creadas) + len(actualizadas)

    # ── Modo B: sin user_token → refrescar webhooks con page tokens ya guardados
    else:
        paginas = db.query(MetaPagina).filter(MetaPagina.activa == True).all()
        if not paginas:
            raise HTTPException(400, "No hay páginas activas. Pasá ?user_token=<token> para importar páginas de Facebook.")
        async with httpx.AsyncClient(timeout=60) as hc:
            for pg in paginas:
                if not pg.page_token:
                    errores.append({"page_id": pg.page_id, "nombre": pg.nombre, "error": "sin page_token"})
                    continue
                r_sub = await hc.post(
                    f"{META_GRAPH_URL}/{pg.page_id}/subscribed_apps",
                    params={"access_token": pg.page_token, "subscribed_fields": "feed,messages,message_reactions"},
                )
                if r_sub.json().get("success"):
                    pg.webhook_subscribed = True
                    actualizadas.append({"page_id": pg.page_id, "nombre": pg.nombre})
                else:
                    errores.append({"page_id": pg.page_id, "nombre": pg.nombre, "error": r_sub.text[:100]})
        db.commit()
        total = len(paginas)

    return {
        "ok": True,
        "total": total,
        "creadas": len(creadas),
        "actualizadas": len(actualizadas),
        "errores": len(errores),
        "nuevas": creadas,
        "errores_detalle": errores,
    }


@router.get("/api/redes/admin/subscribe-via-token")
async def api_redes_admin_subscribe_via_token_get(
    t: str = "",
    user_token: str = "",
    db: Session = Depends(get_db),
):
    """
    Suscribe todas las páginas al webhook usando el user_token como token de admin.
    Obtiene page tokens individuales con GET /{page_id}?fields=access_token.
    No requiere app-specific token — funciona con cualquier token de admin del BM.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")
    if not user_token:
        raise HTTPException(400, "Falta user_token")

    # Guardar el user_token como token global para futuros usos
    stored = encrypt_value(user_token)
    entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "meta_page_access_token").first()
    if entry:
        entry.valor = stored
    else:
        db.add(ConfiguracionSistema(clave="meta_page_access_token", valor=stored, es_secreto=True, categoria="meta"))
    db.commit()

    paginas = db.query(MetaPagina).all()
    resultados: dict = {}
    async with httpx.AsyncClient(timeout=60) as hc:
        for pg in paginas:
            pid = pg.page_id
            # Obtener page token individual
            r_pt = await hc.get(
                f"{META_GRAPH_URL}/{pid}",
                params={"fields": "access_token,name", "access_token": user_token},
            )
            data_pt = r_pt.json()
            if r_pt.status_code != 200 or "access_token" not in data_pt:
                resultados[pid] = {
                    "nombre": pg.nombre,
                    "ok": False,
                    "error": data_pt.get("error", {}).get("message", "sin token"),
                }
                continue

            page_token = data_pt["access_token"]
            pg.page_token = page_token

            # Suscribir webhook
            r_sub = await hc.post(
                f"{META_GRAPH_URL}/{pid}/subscribed_apps",
                params={"access_token": page_token, "subscribed_fields": "feed,messages,message_reactions"},
            )
            body_sub = r_sub.json()
            ok_sub = body_sub.get("success", False)
            if ok_sub:
                pg.webhook_subscribed = True
            resultados[pid] = {"nombre": pg.nombre, "ok": ok_sub, "detalle": body_sub}

    db.commit()
    pages_ok = sum(1 for v in resultados.values() if v["ok"])
    return {
        "ok": pages_ok > 0,
        "token_guardado": True,
        "pages_subscribed": pages_ok,
        "pages_error": len(resultados) - pages_ok,
        "resultados": resultados,
    }


@router.post("/api/redes/admin/eliminar-negativos")
async def api_redes_admin_eliminar_negativos(
    t: str = "",
    db: Session = Depends(get_db),
):
    """Elimina en Facebook todos los comentarios negativos pendientes. Requiere ?t=<ML_AUDIT_TOKEN>."""
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    negativos = db.query(FacebookInteraccion).filter(
        FacebookInteraccion.tipo == "comentario",
        FacebookInteraccion.sentimiento == "negativo",
        FacebookInteraccion.accion == "pendiente",
    ).all()

    if not negativos:
        return {"ok": True, "eliminados": 0, "errores": 0, "msg": "No hay comentarios negativos pendientes"}

    tokens_pagina: dict[str, str] = {}
    for pg in db.query(MetaPagina).filter(MetaPagina.page_token != None).all():
        tokens_pagina[pg.page_id] = pg.page_token

    eliminados = 0
    errores = 0
    for item in negativos:
        token = tokens_pagina.get(item.page_id)
        if not token:
            item.accion = "error_sin_token"
            errores += 1
            continue
        ok = await _eliminar_comentario(item.objeto_id, token)
        item.accion = "eliminado" if ok else "error"
        if ok:
            eliminados += 1
        else:
            errores += 1

    db.commit()
    return {"ok": True, "total": len(negativos), "eliminados": eliminados, "errores": errores}


@router.post("/api/redes/admin/generar-borradores")
async def api_redes_admin_generar_borradores(
    t: str = "",
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Genera borradores de respuesta IA para los primeros N mensajes privados pendientes
    (filtrando automáticos de Facebook). No envía nada. Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    # Filtrar mensajes automáticos de Facebook
    SISTEMA_PREFIXES = [
        "Facebook creó este chat",
        "facebook created this conversation",
    ]

    mensajes = db.query(FacebookInteraccion).filter(
        FacebookInteraccion.tipo == "mensaje",
        FacebookInteraccion.accion == "pendiente",
    ).order_by(FacebookInteraccion.created_at.asc()).all()

    genuinos = [
        m for m in mensajes
        if not any(m.contenido.lower().startswith(p.lower()) for p in SISTEMA_PREFIXES)
    ][:limit]

    paginas = {pg.page_id: pg for pg in db.query(MetaPagina).all()}
    borradores = []
    for m in genuinos:
        pg = paginas.get(m.page_id)
        pg_nombre = pg.nombre if pg else m.page_id
        numero_wa = (pg.numero_whatsapp or "") if pg else ""
        es_reclamo = _es_reclamo(m.contenido)
        wa_destino = WA_RECLAMOS if es_reclamo else (numero_wa or WA_RECLAMOS)
        borrador = await _generar_respuesta_ia(m.contenido, pg_nombre, numero_wa, db)
        borradores.append({
            "id": m.id,
            "pagina": pg_nombre,
            "usuario": m.usuario_nombre,
            "mensaje_original": m.contenido,
            "borrador_respuesta": borrador,
            "es_reclamo": es_reclamo,
            "wa_usado": wa_destino,
        })

    return {"total": len(borradores), "borradores": borradores}


@router.post("/api/redes/admin/enviar-consultas")
async def api_redes_admin_enviar_consultas(
    t: str = "",
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """
    Genera y envía respuestas a todos los mensajes pendientes que NO son reclamos.
    Los reclamos se saltan y quedan en accion='pendiente'.
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    SISTEMA_PREFIXES = [
        "Facebook creó este chat",
        "facebook created this conversation",
    ]

    mensajes = db.query(FacebookInteraccion).filter(
        FacebookInteraccion.tipo == "mensaje",
        FacebookInteraccion.accion == "pendiente",
    ).order_by(FacebookInteraccion.created_at.asc()).all()

    genuinos = [
        m for m in mensajes
        if not any(m.contenido.lower().startswith(p.lower()) for p in SISTEMA_PREFIXES)
    ]

    paginas = {pg.page_id: pg for pg in db.query(MetaPagina).all()}

    enviados = 0
    saltados_reclamo = 0
    errores = 0
    resultados = []

    for m in genuinos[:limit]:
        if _es_reclamo(m.contenido):
            saltados_reclamo += 1
            resultados.append({"id": m.id, "status": "saltado_reclamo", "usuario": m.usuario_nombre})
            continue

        pg = paginas.get(m.page_id)
        if not pg or not pg.page_token:
            errores += 1
            resultados.append({"id": m.id, "status": "error_sin_token", "usuario": m.usuario_nombre})
            continue

        pg_nombre = pg.nombre
        numero_wa = pg.numero_whatsapp or ""
        respuesta = await _generar_respuesta_ia(m.contenido, pg_nombre, numero_wa, db)
        ok = await _responder_mensaje(m.usuario_id, respuesta, pg.page_token)

        if ok:
            m.accion = "respondido"
            m.respuesta_enviada = respuesta
            enviados += 1
            resultados.append({"id": m.id, "status": "enviado", "usuario": m.usuario_nombre, "pagina": pg_nombre})
        else:
            m.accion = "error"
            errores += 1
            resultados.append({"id": m.id, "status": "error_envio", "usuario": m.usuario_nombre})

        db.commit()

    return {
        "ok": True,
        "total_procesados": len(genuinos[:limit]),
        "enviados": enviados,
        "saltados_reclamo": saltados_reclamo,
        "errores": errores,
        "resultados": resultados,
    }


@router.post("/api/redes/admin/marcar-expirados")
async def api_redes_admin_marcar_expirados(
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Marca como 'expirado' todos los mensajes con accion='error' (envío fallido por ventana 24h).
    Deja los reclamos (accion='pendiente') intactos.
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    # Mensajes con accion="error" (envío fallido)
    errores = db.query(FacebookInteraccion).filter(
        FacebookInteraccion.accion == "error",
        FacebookInteraccion.tipo == "mensaje",
    ).all()

    # Mensajes automáticos de Facebook que quedaron "pendiente"
    sistema = db.query(FacebookInteraccion).filter(
        FacebookInteraccion.accion == "pendiente",
        FacebookInteraccion.tipo == "mensaje",
    ).all()
    sistema_fb = [m for m in sistema if "facebook cre" in (m.contenido or "").lower()]

    for m in errores + sistema_fb:
        m.accion = "expirado"
    db.commit()
    return {"ok": True, "marcados": len(errores) + len(sistema_fb), "por_error": len(errores), "sistema_fb": len(sistema_fb)}


@router.get("/api/redes/admin/pendientes")
async def api_redes_admin_pendientes(
    t: str = "",
    tipo: Optional[str] = None,
    sentimiento: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """Lista interacciones pendientes (accion=pendiente). Requiere ?t=<ML_AUDIT_TOKEN>.
    Filtra por tipo=comentario|mensaje y/o sentimiento=negativo|neutro.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    q = db.query(FacebookInteraccion).filter(FacebookInteraccion.accion == "pendiente")
    if tipo:
        q = q.filter(FacebookInteraccion.tipo == tipo)
    if sentimiento:
        q = q.filter(FacebookInteraccion.sentimiento == sentimiento)
    items = q.order_by(FacebookInteraccion.created_at.desc()).limit(min(limit, 500)).all()

    paginas = {pg.page_id: pg.nombre for pg in db.query(MetaPagina).all()}

    return {
        "total": len(items),
        "items": [
            {
                "id": i.id,
                "tipo": i.tipo,
                "sentimiento": i.sentimiento,
                "page_id": i.page_id,
                "pagina": paginas.get(i.page_id, i.page_id),
                "objeto_id": i.objeto_id,
                "usuario": i.usuario_nombre,
                "contenido": i.contenido,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in items
        ],
    }


@router.post("/api/redes/admin/importar-inbox-all")
async def api_redes_admin_importar_inbox_all(
    t: str = "",
    db: Session = Depends(get_db),
):
    """Importa mensajes y comentarios de todas las páginas con token. Requiere ?t=<ML_AUDIT_TOKEN>."""
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    paginas_con_token = db.query(MetaPagina).filter(
        MetaPagina.activa == True,
        MetaPagina.page_token != None,
        MetaPagina.page_token != "",
    ).all()

    if not paginas_con_token:
        raise HTTPException(400, "No hay páginas con token. Corré subscribe-via-token primero.")

    total_importados = 0
    resultados = {}
    for pg in paginas_con_token:
        imp, errs = await _importar_inbox_pagina(pg.page_id, pg.page_token, db)
        total_importados += imp
        resultados[pg.page_id] = {"nombre": pg.nombre, "importados": imp, "errores": errs}

    db.commit()
    return {
        "ok": True,
        "total_importados": total_importados,
        "paginas": len(paginas_con_token),
        "resultados": resultados,
    }


# ─── INTERACCIONES — HISTORIAL + GESTIÓN MANUAL ────────────────────────────────

@router.get("/api/redes/interacciones")
async def api_redes_interacciones(
    page_id: Optional[str] = None,
    tipo: Optional[str] = None,
    accion: Optional[str] = None,
    limit: int = 50,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Lista interacciones registradas (comentarios y mensajes procesados)."""
    _check_access(user, db)
    q = db.query(FacebookInteraccion).order_by(FacebookInteraccion.created_at.desc())
    if page_id:
        q = q.filter(FacebookInteraccion.page_id == page_id)
    if tipo:
        q = q.filter(FacebookInteraccion.tipo == tipo)
    if accion:
        q = q.filter(FacebookInteraccion.accion == accion)
    items = q.limit(min(limit, 200)).all()

    return [
        {
            "id": i.id,
            "page_id": i.page_id,
            "tipo": i.tipo,
            "post_id": i.post_id,
            "objeto_id": i.objeto_id,
            "usuario_nombre": i.usuario_nombre,
            "usuario_id": i.usuario_id,
            "contenido": i.contenido,
            "sentimiento": i.sentimiento,
            "accion": i.accion,
            "respuesta_enviada": i.respuesta_enviada,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


@router.post("/api/redes/interacciones/{interaccion_id}/responder")
async def api_redes_responder_interaccion(
    interaccion_id: int,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Responde manualmente a un comentario o mensaje pendiente."""
    _check_access(user, db)
    body = await request.json()
    respuesta = (body.get("respuesta") or "").strip()
    if not respuesta:
        raise HTTPException(400, "El campo 'respuesta' no puede estar vacío")

    interaccion = db.query(FacebookInteraccion).filter(FacebookInteraccion.id == interaccion_id).first()
    if not interaccion:
        raise HTTPException(404, "Interacción no encontrada")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == interaccion.page_id).first()
    if not pg or not pg.page_token:
        raise HTTPException(400, "Página sin token — no se puede responder")

    ok = False
    if interaccion.tipo == "mensaje":
        ok = await _responder_mensaje(interaccion.usuario_id, respuesta, pg.page_token)
    elif interaccion.tipo == "comentario":
        ok = await _responder_comentario(interaccion.objeto_id, respuesta, pg.page_token)

    if ok:
        interaccion.accion = "respondido"
        interaccion.respuesta_enviada = respuesta
        db.commit()

    return {"ok": ok, "interaccion_id": interaccion_id}


@router.delete("/api/redes/interacciones/{interaccion_id}/comentario")
async def api_redes_eliminar_comentario(
    interaccion_id: int,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Elimina el comentario de Facebook y marca la interacción como eliminada."""
    roles = _check_access(user, db)
    interaccion = db.query(FacebookInteraccion).filter(FacebookInteraccion.id == interaccion_id).first()
    if not interaccion:
        raise HTTPException(404, "Interacción no encontrada")
    if interaccion.tipo != "comentario":
        raise HTTPException(400, "Solo se pueden eliminar comentarios")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == interaccion.page_id).first()
    if not pg or not pg.page_token:
        raise HTTPException(400, "Página sin token")

    ok = await _eliminar_comentario(interaccion.objeto_id, pg.page_token)
    if ok:
        interaccion.accion = "eliminado"
        db.commit()

    return {"ok": ok, "interaccion_id": interaccion_id}


@router.get("/api/redes/facebook/config")
async def api_redes_fb_config(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Devuelve configuración del webhook y token de verificación."""
    _check_access(user, db)
    verify_token = get_config_value("facebook_webhook_verify_token", db) or os.getenv("FB_WEBHOOK_VERIFY_TOKEN", "ecofiver-webhook-2026")
    base_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("PUBLIC_URL") or "https://eco-crm-production.up.railway.app"
    return {
        "webhook_url": f"{base_url}/api/redes/facebook/webhook",
        "verify_token": verify_token,
        "instrucciones": [
            "1. En Meta for Developers → Tu App → Webhooks → Add Callback URL",
            f"2. Callback URL: {base_url}/api/redes/facebook/webhook",
            f"3. Verify Token: {verify_token}",
            "4. Suscribirse a: feed, messages, message_reactions",
            "5. En cada página, presionar 'Suscribir al Webhook' desde este panel",
        ],
    }


# ─── GUARDAR TOKEN DE USUARIO DIRECTAMENTE ───────────────────────────────────

@router.post("/api/redes/facebook/save-user-token")
async def api_redes_save_user_token(
    request: Request,
    t: str = "",
    db: Session = Depends(get_db),
):
    """
    Guarda un user_access_token como meta_page_access_token en config y
    llama a /me/accounts para importar todas las páginas del BM.
    Requiere ?t=<ML_AUDIT_TOKEN>.
    """
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    user_token = (body.get("user_token") or "").strip()
    if not user_token:
        raise HTTPException(400, "Falta 'user_token'")

    # Guardar token en config
    entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "meta_page_access_token").first()
    if entry:
        entry.valor = encrypt_value(user_token)
    else:
        db.add(ConfiguracionSistema(
            clave="meta_page_access_token", valor=encrypt_value(user_token),
            es_secreto=True, categoria="meta"
        ))
    db.commit()

    # Importar páginas desde /me/accounts
    synced = []
    errors = []
    async with httpx.AsyncClient(timeout=30) as hc:
        after = None
        for _ in range(10):
            params: dict = {
                "fields": "id,name,access_token,instagram_business_account{id,name}",
                "access_token": user_token, "limit": 50,
            }
            if after:
                params["after"] = after
            r = await hc.get(f"{META_GRAPH_URL}/me/accounts", params=params)
            if r.status_code != 200:
                errors.append(r.json().get("error", {}).get("message", r.text[:200]))
                break
            data = r.json()
            for p in data.get("data", []):
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
                    if not getattr(existing, "portafolio", None):
                        existing.portafolio = "Eco Módulos y Piscinas"
                else:
                    db.add(MetaPagina(
                        page_id=p["id"], nombre=p["name"], ig_user_id=ig_id,
                        page_token=page_tok, activa=True,
                        portafolio="Eco Módulos y Piscinas",
                    ))
                synced.append({"page_id": p["id"], "nombre": p["name"], "token_ok": bool(page_tok)})
            db.commit()
            after = data.get("paging", {}).get("cursors", {}).get("after")
            if not after or not data.get("data"):
                break

    return {
        "ok": len(synced) > 0,
        "synced": len(synced),
        "pages": synced,
        "errors": errors,
    }


# ─── OAUTH FACEBOOK: FLUJO COMPLETO ──────────────────────────────────────────

FB_OAUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
FB_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
FB_SCOPES = "pages_manage_metadata,pages_messaging,pages_read_engagement,pages_show_list,pages_manage_posts,pages_read_user_content,business_management"


def _get_base_url(db: Session) -> str:
    url = (
        os.getenv("RAILWAY_STATIC_URL")
        or os.getenv("PUBLIC_URL")
        or get_config_value("crm_base_url", db)
        or "https://eco-crm-production.up.railway.app"
    )
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


@router.get("/api/redes/facebook/oauth-url")
async def api_redes_fb_oauth_url(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Devuelve la URL de autorización OAuth de Facebook para que el frontend
    la abra en una nueva pestaña. Usa implicit flow (response_type=token)
    para no requerir el app_secret en el servidor.
    """
    _check_access(user, db)
    app_id = get_config_value("meta_app_id", db)
    if not app_id:
        raise HTTPException(400, "No está configurado el meta_app_id. Ir a Configuración → Redes Sociales.")

    base_url = _get_base_url(db)
    redirect_uri = f"{base_url}/redes/facebook/callback"

    import urllib.parse
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": FB_SCOPES,
        "response_type": "token",
        "state": "ecofiver-oauth",
    }
    url = FB_OAUTH_URL + "?" + urllib.parse.urlencode(params)
    return {"url": url, "redirect_uri": redirect_uri}


@router.get("/redes/facebook/callback", response_class=HTMLResponse)
async def redes_fb_callback_page(request: Request, db: Session = Depends(get_db)):
    """
    Página de callback OAuth. El token llega en el hash (#access_token=...) del lado
    del cliente (implicit flow). Esta página lo lee con JS y llama al endpoint
    de refresh-and-subscribe para guardar los page_tokens y suscribir webhooks.
    """
    audit_token = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    base_url = _get_base_url(db)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Conectando Facebook...</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display:flex; align-items:center; justify-content:center;
           min-height:100vh; margin:0; background:#0d1420; color:#dce6f5; text-align:center; }}
    .card {{ background:#192338; border:1px solid #243350; border-radius:12px; padding:32px 40px; max-width:480px; }}
    h2 {{ margin:0 0 12px; font-size:1.3rem; }}
    p {{ color:#647898; font-size:.9rem; margin:0 0 20px; }}
    .spinner {{ width:36px; height:36px; border:3px solid #243350; border-top-color:#60a5fa;
               border-radius:50%; animation:spin .8s linear infinite; margin:0 auto 20px; }}
    @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
    .ok {{ color:#4ade80; font-size:1.1rem; font-weight:600; }}
    .err {{ color:#f87171; font-size:.9rem; }}
    a {{ color:#60a5fa; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="spinner" id="spinner"></div>
    <h2 id="title">Conectando páginas de Facebook...</h2>
    <p id="msg">Importando páginas de tu cuenta de Meta, no cierres esta pestaña.</p>
  </div>
  <script>
    const AUDIT_TOKEN = "{audit_token}";
    const BASE_URL = "{base_url}";

    async function main() {{
      // Leer el access_token del hash de la URL (implicit flow)
      const hash = window.location.hash.substring(1);
      const params = Object.fromEntries(new URLSearchParams(hash));
      const accessToken = params.access_token;

      if (!accessToken) {{
        // Puede que haya un error
        const searchParams = new URLSearchParams(window.location.search);
        const errDesc = searchParams.get('error_description') || searchParams.get('error') || 'No se recibió token de Facebook.';
        setError(errDesc);
        return;
      }}

      try {{
        // PASO 1: Guardar token y sincronizar páginas desde /me/accounts
        setMsg('Paso 1/3: Guardando token e importando páginas de Facebook...');
        const r1 = await fetch(BASE_URL + '/api/redes/facebook/save-user-token?t=' + encodeURIComponent(AUDIT_TOKEN), {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          credentials: 'include',
          body: JSON.stringify({{ user_token: accessToken }})
        }});
        const data1 = await r1.json();
        if (!r1.ok) {{
          setError('Error guardando token: ' + (data1.detail || JSON.stringify(data1)));
          return;
        }}
        const totalPaginas = data1.synced || 0;

        // PASO 2: Suscribir webhooks usando los page tokens recién importados
        setMsg('Paso 2/3: Suscribiendo webhooks en ' + totalPaginas + ' páginas...');
        let okWebhooks = 0;
        try {{
          const r2 = await fetch(BASE_URL + '/api/redes/audit/refresh-and-subscribe?t=' + encodeURIComponent(AUDIT_TOKEN), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            credentials: 'include',
            body: JSON.stringify({{ user_token: accessToken }})
          }});
          const data2 = await r2.json();
          if (r2.ok && data2.resultados) {{
            okWebhooks = Object.values(data2.resultados).filter(v => v.subscribed_apps?.success).length;
          }}
        }} catch(e2) {{ /* no bloquear si falla */ }}

        // PASO 3: Intentar System User Token para cobertura total
        setMsg('Paso 3/3: Intentando token de sistema (cobertura extendida)...');
        try {{
          await fetch(BASE_URL + '/api/redes/admin/subscribe-via-system-token?t=' + encodeURIComponent(AUDIT_TOKEN), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            credentials: 'include',
            body: JSON.stringify({{ user_token: accessToken }})
          }});
        }} catch(e3) {{ /* ignorar */ }}

        document.getElementById('spinner').style.display = 'none';
        if (totalPaginas > 0) {{
          document.getElementById('title').innerHTML = '<span class="ok">✅ ¡Facebook conectado!</span>';
          document.getElementById('msg').innerHTML =
            totalPaginas + ' página' + (totalPaginas !== 1 ? 's' : '') + ' importada' + (totalPaginas !== 1 ? 's' : '') +
            (okWebhooks > 0 ? ' · ' + okWebhooks + ' con webhook activo' : ' · Activá webhooks desde el panel') +
            '<br><br><a href="' + BASE_URL + '/redes">← Volver al panel de Redes Sociales</a>';
        }} else {{
          document.getElementById('title').innerHTML = '<span style="color:#f59e0b">⚠️ Token guardado sin páginas</span>';
          document.getElementById('msg').innerHTML =
            'El token fue guardado pero no se encontraron páginas en tu cuenta.<br>' +
            'Verificá que seas Admin de las páginas en Meta Business Suite.<br><br>' +
            '<a href="' + BASE_URL + '/redes">← Volver al panel</a>';
        }}

        // Redirigir automáticamente en 4s
        setTimeout(() => window.location.href = BASE_URL + '/redes', 4000);

      }} catch(e) {{
        setError(e.message);
      }}
    }}

    function setMsg(m) {{ document.getElementById('msg').textContent = m; }}
    function setError(e) {{
      document.getElementById('spinner').style.display = 'none';
      document.getElementById('title').innerHTML = '❌ Error de conexión';
      document.getElementById('msg').innerHTML = '<span class="err">' + e + '</span><br><br><a href="/redes">← Volver</a>';
    }}

    main();
  </script>
</body>
</html>"""
    return HTMLResponse(html)


# ─── ELIMINAR PÁGINA DEL SISTEMA ─────────────────────────────────────────────

@router.delete("/api/redes/paginas/{page_id}")
async def api_redes_pagina_eliminar(
    page_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Elimina una página de la base de datos (no afecta Meta)."""
    roles = _check_access(user, db)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar páginas")
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")
    nombre = pg.nombre
    db.delete(pg)
    db.commit()
    return {"ok": True, "page_id": page_id, "nombre": nombre}


# ─── AGREGAR PÁGINA MANUALMENTE ──────────────────────────────────────────────

@router.post("/api/redes/paginas")
async def api_redes_pagina_crear(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Agrega una nueva página manualmente con page_id, nombre y opcionalmente page_token e ig_user_id."""
    _check_access(user, db)
    body = await request.json()

    page_id = (body.get("page_id") or "").strip()
    nombre = (body.get("nombre") or "").strip()
    page_token = (body.get("page_token") or "").strip() or None
    ig_user_id = (body.get("ig_user_id") or "").strip() or None
    portafolio = (body.get("portafolio") or "").strip() or "EcoFiver"

    if not page_id or not nombre:
        raise HTTPException(400, "page_id y nombre son requeridos")

    existing = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if existing:
        raise HTTPException(409, f"La página {page_id} ya existe en el sistema")

    pg = MetaPagina(
        page_id=page_id,
        nombre=nombre,
        page_token=page_token,
        ig_user_id=ig_user_id,
        portafolio=portafolio,
        activa=True,
    )
    db.add(pg)
    db.commit()
    db.refresh(pg)
    return {"ok": True, "page_id": pg.page_id, "nombre": pg.nombre, "portafolio": pg.portafolio}


# ─── PUBLICAR EN MÚLTIPLES PÁGINAS ────────────────────────────────────────────

@router.post("/api/redes/publicar")
async def api_redes_publicar(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Publica texto (y opcionalmente imagen) en una o varias páginas de Facebook/Instagram."""
    _check_access(user, db)
    body = await request.json()

    texto = (body.get("texto") or "").strip()
    imagen_url = (body.get("imagen_url") or "").strip()
    page_ids_raw = body.get("page_ids") or "all"
    publicar_ig = bool(body.get("publicar_ig", False))

    if not texto and not imagen_url:
        raise HTTPException(400, "Se requiere al menos texto o imagen_url")

    if page_ids_raw == "all" or not page_ids_raw:
        paginas = db.query(MetaPagina).filter(MetaPagina.activa == True).all()
    else:
        paginas = db.query(MetaPagina).filter(MetaPagina.page_id.in_(page_ids_raw)).all()

    if not paginas:
        raise HTTPException(400, "No hay páginas activas para publicar")

    resultados: dict = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        for pg in paginas:
            pid = pg.page_id
            token = pg.page_token
            if not token:
                resultados[pid] = {"ok": False, "nombre": pg.nombre, "error": "Sin page_token — conectá la página primero"}
                continue

            try:
                if imagen_url:
                    r = await hc.post(
                        f"{META_GRAPH_URL}/{pid}/photos",
                        params={"access_token": token},
                        json={"url": imagen_url, "message": texto, "published": True},
                    )
                else:
                    r = await hc.post(
                        f"{META_GRAPH_URL}/{pid}/feed",
                        params={"access_token": token},
                        json={"message": texto},
                    )

                data_r = r.json() if r.content else {}
                if r.status_code not in (200, 201) or "error" in data_r:
                    err_msg = data_r.get("error", {}).get("message", r.text[:200])
                    resultados[pid] = {"ok": False, "nombre": pg.nombre, "error": err_msg}
                else:
                    post_id_result = data_r.get("post_id") or data_r.get("id")
                    resultados[pid] = {"ok": True, "nombre": pg.nombre, "post_id": post_id_result}

                    # Publicar en Instagram si está vinculado y hay imagen
                    if publicar_ig and pg.ig_user_id and imagen_url:
                        try:
                            r_ig1 = await hc.post(
                                f"{META_GRAPH_URL}/{pg.ig_user_id}/media",
                                params={"access_token": token},
                                json={"image_url": imagen_url, "caption": texto},
                            )
                            ig_data = r_ig1.json()
                            if r_ig1.status_code == 200 and "id" in ig_data:
                                r_ig2 = await hc.post(
                                    f"{META_GRAPH_URL}/{pg.ig_user_id}/media_publish",
                                    params={"access_token": token},
                                    json={"creation_id": ig_data["id"]},
                                )
                                resultados[pid]["ig_ok"] = r_ig2.status_code == 200
                                resultados[pid]["ig_post_id"] = r_ig2.json().get("id")
                            else:
                                resultados[pid]["ig_error"] = ig_data.get("error", {}).get("message", "Error IG")[:200]
                        except Exception as e_ig:
                            resultados[pid]["ig_error"] = str(e_ig)[:200]

            except Exception as e:
                resultados[pid] = {"ok": False, "nombre": pg.nombre, "error": str(e)[:200]}

    ok_count = sum(1 for v in resultados.values() if v.get("ok"))
    return {
        "ok": ok_count > 0,
        "publicados": ok_count,
        "total": len(resultados),
        "resultados": resultados,
    }


# ─── EDITAR POST FACEBOOK ─────────────────────────────────────────────────────

@router.patch("/api/redes/posts/{post_id:path}/editar")
async def api_redes_editar_post(
    post_id: str,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Edita el texto de una publicación de Facebook."""
    roles = _check_access(user, db)
    body = await request.json()
    mensaje = (body.get("mensaje") or "").strip()
    page_id = (body.get("page_id") or "").strip()
    if not mensaje:
        raise HTTPException(400, "El campo 'mensaje' no puede estar vacío")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    token = pg.page_token if pg and pg.page_token else None
    if not token:
        pg_nombre = pg.nombre if pg else page_id
        raise HTTPException(400, f'La página "{pg_nombre}" no tiene token de página configurado. Sincronizá en Config → Conectar con Facebook.')

    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.post(
            f"{META_GRAPH_URL}/{post_id}",
            params={"access_token": token},
            json={"message": mensaje},
        )
    data = r.json() if r.content else {}
    if r.status_code not in (200, 201) or "error" in data:
        raise HTTPException(400, data.get("error", {}).get("message", r.text[:200]))
    return {"ok": data.get("success", True)}


# ─── ELIMINAR POST INSTAGRAM ──────────────────────────────────────────────────

@router.delete("/api/redes/ig/posts/{media_id}")
async def api_redes_delete_ig_post(
    media_id: str,
    page_id: Optional[str] = None,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Elimina un post de Instagram Business."""
    roles = _check_access(user, db)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar publicaciones")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first() if page_id else None
    token = (pg.page_token if pg and pg.page_token else None) or get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Sin token de Meta configurado")

    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.delete(
            f"{META_GRAPH_URL}/{media_id}",
            params={"access_token": token},
        )
    if r.status_code not in (200, 204):
        err = r.json().get("error", {}) if r.content else {}
        raise HTTPException(400, err.get("message", r.text[:200] or "Error al eliminar"))
    result = r.json() if r.content else {}
    return {"ok": result.get("success", True)}


# ─── COMENTARIOS DE UN POST ────────────────────────────────────────────────────

@router.get("/api/redes/paginas/{page_id}/post/{post_id:path}/comentarios")
async def api_redes_post_comentarios(
    page_id: str,
    post_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Obtiene los comentarios de un post de Facebook."""
    _check_access(user, db)
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    token = (pg.page_token if pg and pg.page_token else None) or get_config_value("meta_page_access_token", db)
    if not token:
        return {"comentarios": [], "error": "Sin token de Meta"}

    try:
        data = await _meta_get(
            f"{META_GRAPH_URL}/{post_id}/comments",
            {"fields": "id,message,from,created_time,like_count,can_remove", "access_token": token, "limit": "50"},
        )
    except HTTPException as e:
        return {"comentarios": [], "error": e.detail}

    return {
        "comentarios": [
            {
                "id": c.get("id"),
                "mensaje": c.get("message", ""),
                "autor_nombre": c.get("from", {}).get("name", ""),
                "autor_id": c.get("from", {}).get("id", ""),
                "created_at": c.get("created_time"),
                "likes": c.get("like_count", 0),
                "puede_eliminar": c.get("can_remove", False),
                "es_negativo": _es_negativo(c.get("message", "")),
            }
            for c in data.get("data", [])
        ]
    }


# ─── RESPONDER COMENTARIO DIRECTAMENTE (SIN INTERACCIÓN PREVIA) ──────────────

@router.post("/api/redes/comentario/responder-directo")
async def api_redes_responder_directo(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Responde a cualquier comment_id de Facebook directamente, sin pasar por la tabla de interacciones."""
    _check_access(user, db)
    body = await request.json()
    comment_id = (body.get("comment_id") or "").strip()
    respuesta = (body.get("respuesta") or "").strip()
    page_id = (body.get("page_id") or "").strip()

    if not comment_id or not respuesta:
        raise HTTPException(400, "comment_id y respuesta son requeridos")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    token = (pg.page_token if pg and pg.page_token else None) or get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Sin token de Meta configurado")

    ok = await _responder_comentario(comment_id, respuesta, token)
    return {"ok": ok}


# ─── RESPONDER CON IA (TRIGGER MANUAL) ───────────────────────────────────────

@router.post("/api/redes/interacciones/{interaccion_id}/responder-ia")
async def api_redes_responder_con_ia(
    interaccion_id: int,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Genera respuesta con IA (con link WA) y la envía para una interacción pendiente.
    Permite triggear manualmente la IA aunque el toggle automático esté desactivado.
    """
    _check_access(user, db)
    interaccion = db.query(FacebookInteraccion).filter(FacebookInteraccion.id == interaccion_id).first()
    if not interaccion:
        raise HTTPException(404, "Interacción no encontrada")

    pg = db.query(MetaPagina).filter(MetaPagina.page_id == interaccion.page_id).first()
    if not pg or not pg.page_token:
        raise HTTPException(400, "Página sin token — no se puede responder")

    numero_wa = pg.numero_whatsapp or ""
    if not numero_wa:
        raise HTTPException(400, f'La página "{pg.nombre}" no tiene WhatsApp configurado — configuralo en Automatización.')
    respuesta = await _generar_respuesta_ia(
        interaccion.contenido or "", pg.nombre, numero_wa, db
    )

    ok = False
    if interaccion.tipo == "mensaje":
        ok = await _responder_mensaje(interaccion.usuario_id, respuesta, pg.page_token)
    elif interaccion.tipo == "comentario":
        ok = await _responder_comentario(interaccion.objeto_id, respuesta, pg.page_token)

    if ok:
        interaccion.accion = "respondido"
        interaccion.respuesta_enviada = respuesta
        db.commit()

    return {"ok": ok, "respuesta": respuesta, "interaccion_id": interaccion_id}


# ─── IGNORAR / ARCHIVAR INTERACCIÓN ──────────────────────────────────────────

@router.post("/api/redes/interacciones/{interaccion_id}/ignorar")
async def api_redes_ignorar_interaccion(
    interaccion_id: int,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Marca una interacción como ignorada sin enviar nada a Meta."""
    _check_access(user, db)
    interaccion = db.query(FacebookInteraccion).filter(FacebookInteraccion.id == interaccion_id).first()
    if not interaccion:
        raise HTTPException(404, "Interacción no encontrada")
    interaccion.accion = "ignorado"
    db.commit()
    return {"ok": True, "interaccion_id": interaccion_id}


# ─── IMPORTAR INTERACCIONES DESDE FACEBOOK (mensajes + comentarios existentes) ──

@router.post("/api/redes/paginas/{page_id}/importar-inbox")
async def api_redes_importar_inbox(
    page_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Importa mensajes y comentarios existentes de FB a la tabla de interacciones."""
    _check_access(user, db)
    pg = db.query(MetaPagina).filter(MetaPagina.page_id == page_id).first()
    if not pg:
        raise HTTPException(404, "Página no encontrada")
    token = pg.page_token or get_config_value("meta_page_access_token", db) or os.getenv("META_PAGE_ACCESS_TOKEN", "").strip()
    if not token:
        raise HTTPException(400, f'Sin token para "{pg.nombre}" — configuralo en Config')

    importados, errores = await _importar_inbox_pagina(page_id, token, db)
    db.commit()
    return {"ok": True, "importados": importados, "page_id": page_id, "errores": errores}


# ─── IMPORTAR INBOX DE TODAS LAS PÁGINAS ─────────────────────────────────────

@router.post("/api/redes/importar-inbox-all")
async def api_redes_importar_inbox_all(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Importa mensajes y comentarios de TODAS las páginas que tengan page_token."""
    _check_access(user, db)
    paginas_con_token = db.query(MetaPagina).filter(
        MetaPagina.activa == True,
        MetaPagina.page_token != None,
        MetaPagina.page_token != "",
    ).all()

    if not paginas_con_token:
        raise HTTPException(400, "No hay páginas con token configurado. Sincronizá primero en Config → Conectar con Facebook.")

    total_importados = 0
    resultados = {}
    for pg in paginas_con_token:
        # Reutilizar la misma lógica de importar-inbox por página
        imp, errs = await _importar_inbox_pagina(pg.page_id, pg.page_token, db)
        total_importados += imp
        resultados[pg.page_id] = {"nombre": pg.nombre, "importados": imp, "errores": errs}

    db.commit()
    return {
        "ok": True,
        "total_importados": total_importados,
        "paginas": len(paginas_con_token),
        "resultados": resultados,
    }


async def _importar_inbox_pagina(page_id: str, token: str, db: Session):
    """Lógica compartida de importación de inbox para una página."""
    importados = 0
    errores = []

    async with httpx.AsyncClient(timeout=45) as hc:
        # Mensajes Messenger paginados
        try:
            next_url = None
            convs_fetched = 0
            params_conv = {
                "platform": "messenger",
                "fields": "id,participants,updated_time,messages.limit(25){id,message,from,created_time}",
                "limit": "50",
                "access_token": token,
            }
            while convs_fetched < 5:
                if next_url:
                    r = await hc.get(next_url)
                else:
                    r = await hc.get(f"{META_GRAPH_URL}/{page_id}/conversations", params=params_conv)
                body = r.json()
                if r.status_code != 200:
                    err = body.get("error", {})
                    errores.append(f"Mensajes: {err.get('message', r.text[:200])}")
                    break
                for conv in body.get("data", []):
                    for msg in conv.get("messages", {}).get("data", []):
                        sender = msg.get("from", {})
                        sender_id = sender.get("id", "")
                        if sender_id == page_id:
                            continue
                        msg_id = msg.get("id", "")
                        texto = (msg.get("message") or "").strip()
                        if not msg_id or not texto:
                            continue
                        if not db.query(FacebookInteraccion).filter(FacebookInteraccion.objeto_id == msg_id).first():
                            db.add(FacebookInteraccion(
                                page_id=page_id, tipo="mensaje", objeto_id=msg_id,
                                usuario_id=sender_id, usuario_nombre=sender.get("name", sender_id),
                                contenido=texto[:1000],
                                sentimiento="negativo" if _es_negativo(texto) else "neutro",
                                accion="pendiente",
                            ))
                            importados += 1
                convs_fetched += 1
                next_url = body.get("paging", {}).get("next")
                if not next_url:
                    break
        except Exception as e:
            errores.append(f"Mensajes: {str(e)[:200]}")

        # Comentarios paginados
        try:
            next_url2 = None
            posts_pages = 0
            params_feed = {
                "fields": "id,comments.limit(100){id,message,from,created_time}",
                "limit": "25",
                "access_token": token,
            }
            while posts_pages < 4:
                if next_url2:
                    r2 = await hc.get(next_url2)
                else:
                    r2 = await hc.get(f"{META_GRAPH_URL}/{page_id}/feed", params=params_feed)
                body2 = r2.json()
                if r2.status_code != 200:
                    err = body2.get("error", {})
                    errores.append(f"Comentarios: {err.get('message', r2.text[:200])}")
                    break
                for post in body2.get("data", []):
                    for cmnt in post.get("comments", {}).get("data", []):
                        cmnt_id = cmnt.get("id", "")
                        author = cmnt.get("from", {})
                        author_id = author.get("id", "")
                        texto = (cmnt.get("message") or "").strip()
                        if not cmnt_id or not texto:
                            continue
                        if not db.query(FacebookInteraccion).filter(FacebookInteraccion.objeto_id == cmnt_id).first():
                            es_neg = _es_negativo(texto)
                            db.add(FacebookInteraccion(
                                page_id=page_id, tipo="comentario", objeto_id=cmnt_id,
                                usuario_id=author_id, usuario_nombre=author.get("name", author_id),
                                contenido=texto[:1000],
                                sentimiento="negativo" if es_neg else "neutro",
                                accion="pendiente",
                            ))
                            importados += 1
                posts_pages += 1
                next_url2 = body2.get("paging", {}).get("next")
                if not next_url2:
                    break
        except Exception as e:
            errores.append(f"Comentarios: {str(e)[:200]}")

    return importados, errores


# ─── RESUMEN DE INTERACCIONES PENDIENTES POR PÁGINA ──────────────────────────

@router.get("/api/redes/interacciones/resumen")
async def api_redes_interacciones_resumen(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Cuenta de interacciones pendientes por página."""
    _check_access(user, db)
    from sqlalchemy import func as sqlfunc

    pendientes_q = (
        db.query(FacebookInteraccion.page_id, sqlfunc.count(FacebookInteraccion.id).label("n"))
        .filter(FacebookInteraccion.accion == "pendiente")
        .group_by(FacebookInteraccion.page_id)
        .all()
    )
    return {row.page_id: row.n for row in pendientes_q}


@router.post("/api/redes/facebook/oauth-token")
async def api_redes_fb_oauth_token(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Alternativa: recibe un user_access_token directamente (pegado desde Graph API Explorer)
    y llama al flujo de refresh-and-subscribe. Permite conectar sin OAuth interactivo.
    """
    _check_access(user, db)
    body = await request.json()
    user_token = (body.get("user_token") or "").strip()
    if not user_token:
        raise HTTPException(400, "Falta 'user_token'")

    audit_token = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")

    # Llamar internamente al endpoint de refresh-and-subscribe
    from starlette.testclient import TestClient  # no disponible en prod
    # Hacemos la lógica directamente
    paginas = db.query(MetaPagina).all()
    if not paginas:
        raise HTTPException(400, "No hay páginas en la DB. Sincronizá primero.")

    resultados = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        for pg in paginas:
            pid = pg.page_id
            r_pt = await hc.get(
                f"{META_GRAPH_URL}/{pid}",
                params={"fields": "access_token,name", "access_token": user_token},
            )
            data_pt = r_pt.json()
            if r_pt.status_code != 200 or "access_token" not in data_pt:
                resultados[pid] = {"error": data_pt.get("error", {}).get("message", "sin token"), "nombre": pg.nombre}
                continue

            page_token = data_pt["access_token"]
            pg.page_token = page_token
            db.commit()

            r_sub = await hc.post(
                f"{META_GRAPH_URL}/{pid}/subscribed_apps",
                params={"access_token": page_token, "subscribed_fields": "feed,messages,message_reactions"},
            )
            sub_data = r_sub.json()
            pg.webhook_subscribed = bool(sub_data.get("success"))
            db.commit()
            resultados[pid] = {
                "nombre": pg.nombre,
                "token_ok": True,
                "webhook_subscribed": pg.webhook_subscribed,
                "webhook_resultado": sub_data,
            }

    ok_count = sum(1 for v in resultados.values() if v.get("webhook_subscribed"))
    return {
        "ok": ok_count > 0,
        "paginas_ok": ok_count,
        "paginas_total": len(resultados),
        "resultados": resultados,
    }
