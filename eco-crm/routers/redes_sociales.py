"""
Panel unificado de gestión de redes sociales.
Endpoints: /redes (HTML) + /api/redes/...
"""
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import MetaPagina, Usuario
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

    if not token:
        return [
            {
                "page_id": p.page_id, "nombre": p.nombre,
                "ig_user_id": p.ig_user_id, "activa": p.activa,
                "fan_count": None, "ig_followers": None, "picture": None,
            }
            for p in pages
        ]

    async with httpx.AsyncClient(timeout=15) as hc:
        for p in pages:
            item = {
                "page_id": p.page_id, "nombre": p.nombre,
                "ig_user_id": p.ig_user_id, "activa": p.activa,
                "fan_count": None, "ig_followers": None, "picture": None,
            }
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
    db.commit()
    return {"ok": True, "page_id": page_id, "activa": p.activa, "ig_user_id": p.ig_user_id}


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
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Elimina un post de Facebook. Solo ADMIN."""
    roles = _check_access(user, db)
    if "ADMIN" not in roles:
        raise HTTPException(403, "Solo ADMIN puede eliminar publicaciones")

    token = get_config_value("meta_page_access_token", db)
    if not token:
        raise HTTPException(400, "Sin token de Meta configurado")

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
