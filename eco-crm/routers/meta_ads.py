"""
Módulo Meta Ads — gestión de campañas publicitarias de Facebook/Instagram.
Endpoints: /api/ads/...
"""
import logging
import os
from datetime import datetime, timedelta

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

BM_ID = "753481671171165"


def _check_access(user: Usuario, db: Session):
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin acceso al módulo de campañas")
    return roles


def _audit_auth(t: str):
    expected = os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")


def _get_token(db: Session) -> str:
    token = get_config_value("meta_page_access_token", db) or ""
    if not token:
        raise HTTPException(400, "No hay token de usuario Meta guardado. Sincronizá páginas primero desde el panel de Redes.")
    return token


async def _graph_get(path: str, params: dict, timeout: int = 30) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.get(f"{META_GRAPH_URL}/{path}", params=params)
    body = r.json() if r.content else {}
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", r.text[:300]))
    return body


async def _graph_post(path: str, data: dict, timeout: int = 20) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.post(f"{META_GRAPH_URL}/{path}", data=data)
    body = r.json() if r.content else {}
    if r.status_code not in (200, 201) or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", r.text[:300]))
    return body


# ─── HTML PAGE ────────────────────────────────────────────────────────────────

@router.get("/ads", response_class=HTMLResponse)
async def ads_page(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    return templates.TemplateResponse("meta_ads.html", {"request": request, "user": user})


# ─── CUENTAS PUBLICITARIAS ───────────────────────────────────────────────────

@router.get("/api/ads/cuentas")
async def api_ads_cuentas(
    t: str = "",
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Lista las cuentas publicitarias accesibles."""
    _check_access(user, db)
    token = _get_token(db)

    # Intentar cuentas del BM primero
    try:
        data = await _graph_get(
            f"{BM_ID}/owned_ad_accounts",
            {"fields": "id,name,account_status,currency,spend_cap,amount_spent", "limit": 50, "access_token": token},
        )
        cuentas = data.get("data", [])
    except HTTPException:
        cuentas = []

    # Si BM no devuelve nada, intentar /me/adaccounts
    if not cuentas:
        try:
            data2 = await _graph_get(
                "me/adaccounts",
                {"fields": "id,name,account_status,currency,amount_spent", "limit": 50, "access_token": token},
            )
            cuentas = data2.get("data", [])
        except HTTPException:
            cuentas = []

    status_map = {1: "ACTIVA", 2: "DESHABILITADA", 3: "SIN PAGAR", 7: "ARCHIVADA", 9: "EN REVISIÓN"}
    for c in cuentas:
        c["status_label"] = status_map.get(c.get("account_status"), str(c.get("account_status", "?")))
        spent = c.get("amount_spent")
        c["gasto_display"] = f"${int(spent)/100:.2f} {c.get('currency','')}" if spent else "—"

    return {"ok": True, "cuentas": cuentas, "total": len(cuentas)}


# ─── CAMPAÑAS ────────────────────────────────────────────────────────────────

@router.get("/api/ads/cuentas/{account_id}/campanias")
async def api_ads_campanias(
    account_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Lista campañas de una cuenta publicitaria con métricas básicas."""
    _check_access(user, db)
    token = _get_token(db)
    acc = account_id if account_id.startswith("act_") else f"act_{account_id}"

    data = await _graph_get(
        f"{acc}/campaigns",
        {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time,created_time",
            "limit": 100,
            "access_token": token,
        },
    )
    campanias = data.get("data", [])

    # Insights del último mes para cada campaña (en batch si hubiera muchas)
    date_from = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = datetime.utcnow().strftime("%Y-%m-%d")

    for c in campanias:
        try:
            ins = await _graph_get(
                f"{c['id']}/insights",
                {
                    "fields": "spend,impressions,reach,clicks,cpm,cpc,ctr,actions",
                    "date_preset": "last_30d",
                    "access_token": token,
                },
            )
            metrics = ins.get("data", [{}])[0] if ins.get("data") else {}
            c["metricas"] = {
                "gasto": f"${float(metrics.get('spend', 0)):.2f}",
                "impresiones": int(metrics.get("impressions", 0)),
                "alcance": int(metrics.get("reach", 0)),
                "clics": int(metrics.get("clicks", 0)),
                "cpm": f"${float(metrics.get('cpm', 0)):.2f}",
                "cpc": f"${float(metrics.get('cpc', 0)):.2f}",
                "ctr": f"{float(metrics.get('ctr', 0)):.2f}%",
            }
            # Extraer conversaciones/mensajes de actions
            actions = metrics.get("actions", [])
            for a in actions:
                if a.get("action_type") in ("onsite_conversion.messaging_conversation_started_7d", "lead"):
                    c["metricas"]["leads"] = int(a.get("value", 0))
        except Exception:
            c["metricas"] = {}

        # Presupuesto legible
        if c.get("daily_budget"):
            c["presupuesto"] = f"${int(c['daily_budget'])/100:.0f}/día"
        elif c.get("lifetime_budget"):
            c["presupuesto"] = f"${int(c['lifetime_budget'])/100:.0f} total"
        else:
            c["presupuesto"] = "—"

    status_order = {"ACTIVE": 0, "PAUSED": 1, "ARCHIVED": 2, "DELETED": 3}
    campanias.sort(key=lambda x: status_order.get(x.get("status", ""), 9))

    return {"ok": True, "campanias": campanias, "total": len(campanias), "account_id": acc}


# ─── INSIGHTS DE CUENTA ───────────────────────────────────────────────────────

@router.get("/api/ads/cuentas/{account_id}/insights")
async def api_ads_cuenta_insights(
    account_id: str,
    periodo: str = "last_30d",
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Métricas agregadas de una cuenta publicitaria."""
    _check_access(user, db)
    token = _get_token(db)
    acc = account_id if account_id.startswith("act_") else f"act_{account_id}"

    data = await _graph_get(
        f"{acc}/insights",
        {
            "fields": "spend,impressions,reach,clicks,cpm,cpc,ctr,actions,account_name,account_id",
            "date_preset": periodo,
            "level": "account",
            "access_token": token,
        },
    )
    metrics = data.get("data", [{}])[0] if data.get("data") else {}

    leads = 0
    for a in metrics.get("actions", []):
        if a.get("action_type") in (
            "onsite_conversion.messaging_conversation_started_7d",
            "lead",
            "omni_initiated_checkout",
        ):
            leads += int(a.get("value", 0))

    return {
        "ok": True,
        "periodo": periodo,
        "gasto": float(metrics.get("spend", 0)),
        "impresiones": int(metrics.get("impressions", 0)),
        "alcance": int(metrics.get("reach", 0)),
        "clics": int(metrics.get("clicks", 0)),
        "cpm": float(metrics.get("cpm", 0)),
        "cpc": float(metrics.get("cpc", 0)),
        "ctr": float(metrics.get("ctr", 0)),
        "leads": leads,
    }


# ─── INSIGHTS DE CAMPAÑA ──────────────────────────────────────────────────────

@router.get("/api/ads/campanias/{campaign_id}/insights")
async def api_ads_campania_insights(
    campaign_id: str,
    periodo: str = "last_30d",
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)

    data = await _graph_get(
        f"{campaign_id}/insights",
        {
            "fields": "campaign_name,spend,impressions,reach,clicks,cpm,cpc,ctr,actions,date_start,date_stop",
            "date_preset": periodo,
            "breakdowns": "age,gender",
            "access_token": token,
        },
    )
    return {"ok": True, "periodo": periodo, "data": data.get("data", [])}


# ─── CONJUNTOS DE ANUNCIOS ────────────────────────────────────────────────────

@router.get("/api/ads/campanias/{campaign_id}/conjuntos")
async def api_ads_conjuntos(
    campaign_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)

    data = await _graph_get(
        f"{campaign_id}/adsets",
        {
            "fields": "id,name,status,daily_budget,lifetime_budget,optimization_goal,billing_event,targeting,start_time,end_time",
            "limit": 100,
            "access_token": token,
        },
    )
    conjuntos = data.get("data", [])

    for cs in conjuntos:
        try:
            ins = await _graph_get(
                f"{cs['id']}/insights",
                {"fields": "spend,impressions,reach,clicks,cpm,cpc", "date_preset": "last_30d", "access_token": token},
            )
            m = ins.get("data", [{}])[0] if ins.get("data") else {}
            cs["metricas"] = {
                "gasto": f"${float(m.get('spend', 0)):.2f}",
                "impresiones": int(m.get("impressions", 0)),
                "alcance": int(m.get("reach", 0)),
                "clics": int(m.get("clicks", 0)),
            }
        except Exception:
            cs["metricas"] = {}

    return {"ok": True, "conjuntos": conjuntos, "total": len(conjuntos)}


# ─── ANUNCIOS ────────────────────────────────────────────────────────────────

@router.get("/api/ads/campanias/{campaign_id}/anuncios")
async def api_ads_anuncios(
    campaign_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)

    data = await _graph_get(
        f"{campaign_id}/ads",
        {
            "fields": "id,name,status,creative{id,name,thumbnail_url,object_story_spec},adset_id",
            "limit": 100,
            "access_token": token,
        },
    )
    anuncios = data.get("data", [])

    for ad in anuncios:
        try:
            ins = await _graph_get(
                f"{ad['id']}/insights",
                {"fields": "spend,impressions,reach,clicks,cpm,cpc,ctr", "date_preset": "last_30d", "access_token": token},
            )
            m = ins.get("data", [{}])[0] if ins.get("data") else {}
            ad["metricas"] = {
                "gasto": f"${float(m.get('spend', 0)):.2f}",
                "impresiones": int(m.get("impressions", 0)),
                "alcance": int(m.get("reach", 0)),
                "clics": int(m.get("clicks", 0)),
                "ctr": f"{float(m.get('ctr', 0)):.2f}%",
                "cpc": f"${float(m.get('cpc', 0)):.2f}",
            }
        except Exception:
            ad["metricas"] = {}

    return {"ok": True, "anuncios": anuncios, "total": len(anuncios)}


# ─── PAUSA / ACTIVA CAMPAÑA ───────────────────────────────────────────────────

@router.patch("/api/ads/campanias/{campaign_id}/estado")
async def api_ads_campania_estado(
    campaign_id: str,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)
    body = await request.json()
    nuevo_estado = body.get("status", "").upper()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        raise HTTPException(400, "status debe ser ACTIVE o PAUSED")

    data = await _graph_post(campaign_id, {"status": nuevo_estado, "access_token": token})
    return {"ok": True, "campaign_id": campaign_id, "nuevo_estado": nuevo_estado, "success": data.get("success", False)}


# ─── PAUSA / ACTIVA CONJUNTO ──────────────────────────────────────────────────

@router.patch("/api/ads/conjuntos/{adset_id}/estado")
async def api_ads_adset_estado(
    adset_id: str,
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)
    body = await request.json()
    nuevo_estado = body.get("status", "").upper()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        raise HTTPException(400, "status debe ser ACTIVE o PAUSED")

    data = await _graph_post(adset_id, {"status": nuevo_estado, "access_token": token})
    return {"ok": True, "adset_id": adset_id, "nuevo_estado": nuevo_estado, "success": data.get("success", False)}


# ─── COMENTARIOS EN ANUNCIOS ──────────────────────────────────────────────────

@router.get("/api/ads/campanias/{campaign_id}/comentarios")
async def api_ads_comentarios(
    campaign_id: str,
    solo_negativos: bool = False,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Obtiene comentarios de todos los anuncios de una campaña."""
    _check_access(user, db)
    token = _get_token(db)

    # Primero obtener los ads de la campaña
    ads_data = await _graph_get(
        f"{campaign_id}/ads",
        {"fields": "id,name,creative{object_story_id}", "limit": 100, "access_token": token},
    )
    todos_comentarios = []

    for ad in ads_data.get("data", []):
        story_id = (ad.get("creative") or {}).get("object_story_id")
        if not story_id:
            continue
        try:
            com_data = await _graph_get(
                f"{story_id}/comments",
                {
                    "fields": "id,message,from,created_time,can_remove,sentiment",
                    "limit": 100,
                    "access_token": token,
                    "filter": "stream",
                },
            )
            for c in com_data.get("data", []):
                c["ad_id"] = ad["id"]
                c["ad_name"] = ad.get("name", "")
                todos_comentarios.append(c)
        except Exception:
            pass

    if solo_negativos:
        negativos_keywords = ["trucho", "estafa", "caro", "malo", "pésimo", "nunca", "robo", "mentira", "cagan"]
        todos_comentarios = [
            c for c in todos_comentarios
            if any(kw in (c.get("message") or "").lower() for kw in negativos_keywords)
        ]

    todos_comentarios.sort(key=lambda x: x.get("created_time", ""), reverse=True)
    return {"ok": True, "comentarios": todos_comentarios, "total": len(todos_comentarios)}


# ─── ELIMINAR COMENTARIO DE ANUNCIO ──────────────────────────────────────────

@router.delete("/api/ads/comentarios/{comment_id}")
async def api_ads_eliminar_comentario(
    comment_id: str,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_access(user, db)
    token = _get_token(db)

    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.delete(f"{META_GRAPH_URL}/{comment_id}", params={"access_token": token})
    body = r.json() if r.content else {}
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", r.text[:200]))
    return {"ok": True, "comment_id": comment_id, "eliminado": body.get("success", True)}


# ─── RESUMEN GLOBAL ───────────────────────────────────────────────────────────

@router.get("/api/ads/resumen")
async def api_ads_resumen(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Dashboard: gasto total, campañas activas, mejores y peores."""
    _check_access(user, db)
    token = _get_token(db)

    # Obtener todas las cuentas
    cuentas = []
    try:
        bm_data = await _graph_get(
            f"{BM_ID}/owned_ad_accounts",
            {"fields": "id,name,account_status,currency,amount_spent", "limit": 50, "access_token": token},
        )
        cuentas = bm_data.get("data", [])
    except Exception:
        pass

    if not cuentas:
        try:
            me_data = await _graph_get(
                "me/adaccounts",
                {"fields": "id,name,account_status,currency,amount_spent", "limit": 50, "access_token": token},
            )
            cuentas = me_data.get("data", [])
        except Exception:
            pass

    total_gasto = 0.0
    campanias_activas = 0
    campanias_pausadas = 0
    mejor_campania = None
    peor_campania = None
    mejor_spend = 0.0
    mejor_clics = 0

    for cuenta in cuentas:
        acc_id = cuenta["id"]
        if not acc_id.startswith("act_"):
            acc_id = f"act_{acc_id}"
        spent = cuenta.get("amount_spent")
        if spent:
            total_gasto += int(spent) / 100

        # Campañas activas
        try:
            c_data = await _graph_get(
                f"{acc_id}/campaigns",
                {"fields": "id,name,status", "filtering": '[{"field":"effective_status","operator":"IN","value":["ACTIVE","PAUSED"]}]', "limit": 50, "access_token": token},
            )
            for c in c_data.get("data", []):
                if c.get("status") == "ACTIVE":
                    campanias_activas += 1
                elif c.get("status") == "PAUSED":
                    campanias_pausadas += 1
        except Exception:
            pass

    return {
        "ok": True,
        "gasto_total_mes": total_gasto,
        "cuentas": len(cuentas),
        "campanias_activas": campanias_activas,
        "campanias_pausadas": campanias_pausadas,
    }


# ─── ADMIN: VERIFICAR TOKEN PARA ADS ─────────────────────────────────────────

@router.get("/api/ads/admin/verificar-token")
async def api_ads_verificar_token(
    t: str = "",
    db: Session = Depends(get_db),
):
    """Verifica si el token guardado tiene permisos para Ads API."""
    _audit_auth(t)
    token = _get_token(db)

    result = {"token_ok": False, "permisos": [], "cuentas": 0, "error": None}

    try:
        perm_data = await _graph_get(
            "me/permissions",
            {"access_token": token},
        )
        permisos = [p["permission"] for p in perm_data.get("data", []) if p.get("status") == "granted"]
        result["permisos"] = permisos
        result["token_ok"] = True

        ads_permisos = [p for p in permisos if "ads" in p.lower()]
        result["ads_permisos"] = ads_permisos
        result["tiene_ads_read"] = "ads_read" in permisos
        result["tiene_ads_management"] = "ads_management" in permisos
    except HTTPException as e:
        result["error"] = str(e.detail)

    try:
        me_data = await _graph_get("me", {"fields": "id,name", "access_token": token})
        result["usuario"] = me_data.get("name", "")
        result["user_id"] = me_data.get("id", "")
    except Exception:
        pass

    return result
