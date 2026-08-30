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
from database.models import MetaPagina, Usuario, FacebookInteraccion
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

    def _pg_base(p):
        return {
            "page_id": p.page_id, "nombre": p.nombre,
            "ig_user_id": p.ig_user_id, "activa": p.activa,
            "auto_reply_comentarios": bool(p.auto_reply_comentarios),
            "auto_reply_mensajes": bool(p.auto_reply_mensajes),
            "auto_eliminar_negativos": bool(p.auto_eliminar_negativos),
            "webhook_subscribed": bool(p.webhook_subscribed),
            "numero_whatsapp": p.numero_whatsapp or "1144498854",
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


def _es_negativo(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_NEGATIVAS)


def _wa_url(numero: str) -> str:
    n = numero.strip().replace("+", "").replace("-", "").replace(" ", "")
    if not n.startswith("54"):
        n = "54" + n
    return f"https://wa.me/{n}"


async def _generar_respuesta_ia(mensaje_usuario: str, pagina_nombre: str, numero_wa: str) -> str:
    """Genera respuesta comercial con IA derivando a WhatsApp."""
    try:
        from utils.ai_client import ai_complete
        from utils.contexto_ecofiver import ctx_empresa
        prompt = (
            f"{ctx_empresa()}\n\n"
            f"Sos el asistente comercial de la página de Facebook '{pagina_nombre}'.\n"
            f"Un usuario escribió: «{mensaje_usuario[:300]}»\n\n"
            "Escribí UNA respuesta corta (máximo 3 oraciones), amigable y comercial en español argentino. "
            "Debés derivar al WhatsApp para continuar la conversación. "
            f"El link de WhatsApp es: {_wa_url(numero_wa)} — incluidlo siempre. "
            "No inventes precios ni fechas. Sé cálido, profesional y generá interés."
        )
        resp = await ai_complete(prompt, max_tokens=200)
        return resp.strip()
    except Exception as e:
        log.warning(f"IA falló, usando template: {e}")
        return (
            f"¡Hola! 😊 Gracias por tu mensaje. Para brindarte atención personalizada "
            f"comunicate con nosotros por WhatsApp: {_wa_url(numero_wa)} — ¡Te respondemos al instante!"
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

    numero_wa = pg.numero_whatsapp or "1144498854"

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
            respuesta = await _generar_respuesta_ia(msg_text, pg.nombre, numero_wa)
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
            respuesta = await _generar_respuesta_ia(msg_text, pg.nombre, numero_wa)
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
        pg.numero_whatsapp = (body["numero_whatsapp"] or "1144498854").strip()

    db.commit()
    return {
        "ok": True,
        "page_id": page_id,
        "auto_reply_comentarios": pg.auto_reply_comentarios,
        "auto_reply_mensajes": pg.auto_reply_mensajes,
        "auto_eliminar_negativos": pg.auto_eliminar_negativos,
        "numero_whatsapp": pg.numero_whatsapp,
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

    resultados = {}
    async with httpx.AsyncClient(timeout=30) as hc:
        for pg in paginas:
            pid = pg.page_id
            resultado_pg = {}

            # 1) Obtener page token desde el user token
            r_pt = await hc.get(
                f"{META_GRAPH_URL}/{pid}",
                params={"fields": "access_token,name", "access_token": user_token},
            )
            if r_pt.status_code != 200 or "access_token" not in r_pt.json():
                resultado_pg["error_token"] = r_pt.json()
                resultados[pid] = resultado_pg
                continue

            page_token = r_pt.json()["access_token"]
            resultado_pg["page_name"] = r_pt.json().get("name", pid)
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
