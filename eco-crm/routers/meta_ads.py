"""
Meta Ads API — portafolios, campañas y dashboard de rendimiento.
Endpoints: /api/meta/portafolios  /api/meta/campanas/dashboard  etc.
"""
import json
import logging
import os
from datetime import date, timedelta
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database.database import get_db
from database.models import MetaPortafolio, MetaCampanaSnapshot, MetaPagina, Usuario, Lead
from database.encryption import encrypt_value, decrypt_value
from routers.auth import require_auth, get_user_roles

router = APIRouter()
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

META_GRAPH = "https://graph.facebook.com/v19.0"


# ── PÁGINA META ADS ───────────────────────────────────────────────────────────

@router.get("/ads", response_class=HTMLResponse, include_in_schema=False)
@router.get("/meta-ads", response_class=HTMLResponse, include_in_schema=False)
async def meta_ads_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("meta_ads.html", {
        "request": request, "user": current_user, "roles": roles,
    })


# ── helpers ──────────────────────────────────────────────────────────────────

def _check_access(user: Usuario, db: Session):
    roles = get_user_roles(user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Sin acceso al módulo de Ads")
    return roles


def _portafolio_dict(p: MetaPortafolio) -> dict:
    return {
        "id": p.id,
        "nombre": p.nombre,
        "slug": p.slug,
        "ad_account_id": p.ad_account_id,
        "tiene_token": bool(p.system_token_enc),
        "activo": p.activo,
        "color": p.color or "#4f46e5",
    }


async def _ads_get(token: str, path: str, params: dict, timeout: int = 20) -> dict:
    url = f"{META_GRAPH}/{path.lstrip('/')}"
    params["access_token"] = token
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.get(url, params=params)
    body = r.json() if r.content else {}
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", f"Meta API error: {r.text[:200]}"))
    return body


def _date_range(periodo: str):
    """Devuelve (date_start, date_end) para la Ads API según el periodo."""
    hoy = date.today()
    if periodo == "hoy":
        return hoy.isoformat(), hoy.isoformat()
    elif periodo == "semana":
        lun = hoy - timedelta(days=hoy.weekday())
        return lun.isoformat(), hoy.isoformat()
    elif periodo == "mes":
        return hoy.replace(day=1).isoformat(), hoy.isoformat()
    elif periodo == "maximo":
        return None, None   # se usa lifetime en la API
    return hoy.isoformat(), hoy.isoformat()


# ── PORTAFOLIOS CRUD ─────────────────────────────────────────────────────────

@router.get("/api/meta/portafolios")
async def list_portafolios(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pfs = db.query(MetaPortafolio).order_by(MetaPortafolio.nombre).all()
    return {"portafolios": [_portafolio_dict(p) for p in pfs]}


@router.post("/api/meta/portafolios")
async def crear_portafolio(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    nombre = (data.get("nombre") or "").strip()
    slug = (data.get("slug") or nombre.lower().replace(" ", "_")).strip()
    if not nombre or not slug:
        raise HTTPException(400, "nombre y slug son requeridos")
    if db.query(MetaPortafolio).filter_by(slug=slug).first():
        raise HTTPException(409, f"Ya existe un portafolio con slug '{slug}'")
    p = MetaPortafolio(
        nombre=nombre,
        slug=slug,
        ad_account_id=data.get("ad_account_id") or None,
        activo=True,
        color=data.get("color") or "#4f46e5",
    )
    token_raw = (data.get("system_token") or "").strip()
    if token_raw:
        p.system_token_enc = encrypt_value(token_raw)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"ok": True, "portafolio": _portafolio_dict(p)}


@router.put("/api/meta/portafolios/{portafolio_id}")
async def actualizar_portafolio(
    portafolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    p = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not p:
        raise HTTPException(404, "Portafolio no encontrado")
    data = await request.json()
    if "nombre" in data:
        p.nombre = data["nombre"].strip()
    if "ad_account_id" in data:
        p.ad_account_id = (data["ad_account_id"] or "").strip() or None
    if "color" in data:
        p.color = data["color"]
    if "activo" in data:
        p.activo = bool(data["activo"])
    token_raw = (data.get("system_token") or "").strip()
    if token_raw:
        p.system_token_enc = encrypt_value(token_raw)
    elif data.get("borrar_token"):
        p.system_token_enc = None
    db.commit()
    return {"ok": True, "portafolio": _portafolio_dict(p)}


# ── INIT TOKEN DESDE ENV (uso único) ─────────────────────────────────────────

@router.post("/api/meta/admin/init-tokens-from-env")
async def init_tokens_from_env(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Copia WA_TOKEN del env a system_token_enc en portafolios sin token. Solo ADMIN."""
    _check_access(current_user, db)
    wa_token = os.getenv("WA_TOKEN", "").strip()
    if not wa_token:
        raise HTTPException(400, "WA_TOKEN no configurado en entorno")
    pfs = db.query(MetaPortafolio).all()
    actualizados = []
    for p in pfs:
        if not p.system_token_enc:
            p.system_token_enc = encrypt_value(wa_token)
            actualizados.append(p.nombre)
    db.commit()
    return {"ok": True, "actualizados": actualizados, "total": len(actualizados)}


# ── EXCHANGE TOKEN (corto → larga duración 60 días) ──────────────────────────

@router.post("/api/meta/portafolios/{portafolio_id}/exchange-token")
async def exchange_token(
    portafolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Recibe un token corto de usuario, lo convierte a long-lived (60 días) y lo guarda."""
    _check_access(current_user, db)
    p = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not p:
        raise HTTPException(404, "Portafolio no encontrado")
    data = await request.json()
    short_token = (data.get("token") or "").strip()
    if not short_token:
        raise HTTPException(400, "Se requiere 'token'")
    app_id = os.getenv("META_APP_ID", "").strip()
    app_secret = os.getenv("META_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise HTTPException(500, "META_APP_ID / META_APP_SECRET no configurados")
    # Intercambio por long-lived token
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(
            "https://graph.facebook.com/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
        )
    body = r.json() if r.content else {}
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, f"Exchange fallido: {err.get('message', r.text[:200])}")
    long_token = body.get("access_token", "")
    expires_in = body.get("expires_in", 0)
    if not long_token:
        raise HTTPException(500, "Meta no devolvió token")
    # Guardar
    p.system_token_enc = encrypt_value(long_token)
    if data.get("ad_account_id"):
        p.ad_account_id = (data["ad_account_id"] or "").strip() or None
    db.commit()
    return {"ok": True, "expires_in_days": round(expires_in / 86400), "portafolio": _portafolio_dict(p)}


# ── LISTAR AD ACCOUNTS DEL TOKEN (helper diagnóstico) ────────────────────────

@router.get("/api/meta/portafolios/{portafolio_id}/adaccounts")
async def list_adaccounts(
    portafolio_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    p = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not p:
        raise HTTPException(404, "Portafolio no encontrado")
    if not p.system_token_enc:
        raise HTTPException(400, "Portafolio sin token")
    token = decrypt_value(p.system_token_enc)
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(
            "https://graph.facebook.com/v19.0/me/adaccounts",
            params={"fields": "name,account_id,account_status,currency,business", "access_token": token, "limit": 50},
        )
    body = r.json() if r.content else {}
    if r.status_code != 200 or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, f"Error Meta: {err.get('message', r.text[:200])}")
    return body


# ── BALANCE DE CUENTA PUBLICITARIA ───────────────────────────────────────────

@router.get("/api/meta/portafolios/{portafolio_id}/balance")
async def portafolio_balance(
    portafolio_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    p = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not p:
        raise HTTPException(404, "Portafolio no encontrado")
    if not p.ad_account_id or not p.system_token_enc:
        return {"ok": False, "error": "Portafolio sin cuenta publicitaria o token configurado"}
    token = decrypt_value(p.system_token_enc)
    acc_id = p.ad_account_id if p.ad_account_id.startswith("act_") else f"act_{p.ad_account_id}"
    try:
        data = await _ads_get(token, acc_id, {
            "fields": "name,balance,amount_spent,currency,spend_cap,account_status"
        })
        return {
            "ok": True,
            "nombre_cuenta": data.get("name"),
            "balance": float(data.get("balance") or 0) / 100,
            "gastado": float(data.get("amount_spent") or 0) / 100,
            "moneda": data.get("currency", "ARS"),
            "estado": data.get("account_status"),
        }
    except HTTPException as e:
        return {"ok": False, "error": e.detail}


# ── CAMPAÑAS CON INSIGHTS ─────────────────────────────────────────────────────

@router.get("/api/meta/portafolios/{portafolio_id}/campanas")
async def portafolio_campanas(
    portafolio_id: int,
    periodo: str = "hoy",   # hoy | semana | mes | maximo
    solo_activas: bool = True,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    p = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not p:
        raise HTTPException(404, "Portafolio no encontrado")
    if not p.ad_account_id or not p.system_token_enc:
        return {"ok": False, "campanas": [], "error": "Token o cuenta no configurada"}

    token = decrypt_value(p.system_token_enc)
    acc_id = p.ad_account_id if p.ad_account_id.startswith("act_") else f"act_{p.ad_account_id}"

    # Filtro de estado
    status_filter = "ACTIVE" if solo_activas else "ACTIVE,PAUSED,ARCHIVED"
    date_start, date_end = _date_range(periodo)

    insight_fields = (
        "spend,impressions,clicks,actions,cost_per_action_type,"
        "reach,frequency"
    )
    _ins_mod = (
        "date_preset(maximum)"
        if periodo == "maximo"
        else f'time_range({{"since":"{date_start}","until":"{date_end}"}})'
    )
    params: dict = {
        "fields": (
            f"id,name,status,daily_budget,lifetime_budget,objective,"
            f"insights.{_ins_mod}{{{insight_fields}}}"
        ),
        "effective_status": '["' + status_filter.replace(",", '","') + '"]',
        "limit": 100,
    }

    try:
        raw = await _ads_get(token, f"{acc_id}/campaigns", params)
    except HTTPException as e:
        return {"ok": False, "campanas": [], "error": e.detail}

    campanas = []
    for c in raw.get("data", []):
        insights = (c.get("insights") or {}).get("data", [{}])[0] if c.get("insights") else {}
        spend = float(insights.get("spend") or 0)
        impressions = int(insights.get("impressions") or 0)
        clicks = int(insights.get("clicks") or 0)

        # Extraer leads (messaging_conversation_started o lead action)
        actions = insights.get("actions") or []
        leads = 0
        for act in actions:
            if act.get("action_type") in (
                "messaging_conversation_started_7d",
                "onsite_conversion.messaging_conversation_started_7d",
                "lead",
            ):
                leads += int(act.get("value") or 0)

        cpl = round(spend / leads, 2) if leads > 0 else None
        daily_budget = float(c.get("daily_budget") or 0) / 100
        lifetime_budget = float(c.get("lifetime_budget") or 0) / 100

        campanas.append({
            "campaign_id": c["id"],
            "nombre": c["name"],
            "status": c.get("status"),
            "objetivo": c.get("objective"),
            "daily_budget": daily_budget or None,
            "lifetime_budget": lifetime_budget or None,
            "spend": spend,
            "impressions": impressions,
            "clicks": clicks,
            "leads": leads,
            "cpl": cpl,
        })

    return {
        "ok": True,
        "portafolio": p.nombre,
        "periodo": periodo,
        "campanas": campanas,
        "totales": {
            "spend": round(sum(c["spend"] for c in campanas), 2),
            "leads": sum(c["leads"] for c in campanas),
            "campanas_activas": sum(1 for c in campanas if c["status"] == "ACTIVE"),
        },
    }


# ── DASHBOARD UNIFICADO (todos los portafolios) ────────────────────────────

@router.get("/api/meta/campanas/dashboard")
async def campanas_dashboard(
    periodo: str = "hoy",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    portafolios = db.query(MetaPortafolio).filter_by(activo=True).all()

    # Índice de páginas para cruzar page_id → vendedor + whatsapp
    paginas_idx = {
        pg.page_id: pg
        for pg in db.query(MetaPagina).all()
    }

    resultado = []
    for pf in portafolios:
        if not pf.ad_account_id or not pf.system_token_enc:
            resultado.append({
                "portafolio_id": pf.id,
                "portafolio": pf.nombre,
                "color": pf.color,
                "error": "Sin token configurado",
                "campanas": [],
            })
            continue
        token = decrypt_value(pf.system_token_enc)
        acc_id = pf.ad_account_id if pf.ad_account_id.startswith("act_") else f"act_{pf.ad_account_id}"
        date_start, date_end = _date_range(periodo)

        insight_fields = "spend,impressions,clicks,actions"
        _ins_mod = (
            "date_preset(maximum)"
            if periodo == "maximo"
            else f'time_range({{"since":"{date_start}","until":"{date_end}"}})'
        )
        params: dict = {
            "fields": (
                f"id,name,status,daily_budget,lifetime_budget,"
                f"adsets{{name,promoted_object}},"
                f"insights.{_ins_mod}{{{insight_fields}}}"
            ),
            "effective_status": '["ACTIVE"]',
            "limit": 100,
        }
        try:
            raw = await _ads_get(token, f"{acc_id}/campaigns", params)
        except HTTPException as e:
            resultado.append({
                "portafolio_id": pf.id,
                "portafolio": pf.nombre,
                "color": pf.color,
                "error": e.detail,
                "campanas": [],
            })
            continue

        campanas_pf = []
        for c in raw.get("data", []):
            insights = (c.get("insights") or {}).get("data", [{}])[0] if c.get("insights") else {}
            spend = float(insights.get("spend") or 0)
            clicks = int(insights.get("clicks") or 0)
            actions = insights.get("actions") or []
            leads = sum(
                int(a.get("value") or 0) for a in actions
                if a.get("action_type") in (
                    "messaging_conversation_started_7d",
                    "onsite_conversion.messaging_conversation_started_7d",
                    "lead",
                )
            )
            cpl = round(spend / leads, 2) if leads > 0 else None

            # Intentar asociar página a un vendedor
            page_id = None
            adsets_data = (c.get("adsets") or {}).get("data", [])
            for ads in adsets_data:
                po = ads.get("promoted_object") or {}
                if po.get("page_id"):
                    page_id = po["page_id"]
                    break

            pagina = paginas_idx.get(page_id) if page_id else None
            vendedor = (pagina.vendedor if pagina else None) or (pagina.nombre if pagina else None)
            whatsapp = pagina.numero_whatsapp if pagina else None

            campanas_pf.append({
                "campaign_id": c["id"],
                "nombre": c["name"],
                "status": c.get("status"),
                "page_id": page_id,
                "pagina_nombre": pagina.nombre if pagina else None,
                "vendedor": vendedor,
                "whatsapp": whatsapp,
                "spend": spend,
                "clicks": clicks,
                "leads": leads,
                "cpl": cpl,
                "daily_budget": float(c.get("daily_budget") or 0) / 100 or None,
            })

        resultado.append({
            "portafolio_id": pf.id,
            "portafolio": pf.nombre,
            "color": pf.color,
            "slug": pf.slug,
            "campanas": campanas_pf,
            "totales": {
                "spend": round(sum(x["spend"] for x in campanas_pf), 2),
                "leads": sum(x["leads"] for x in campanas_pf),
                "activas": len(campanas_pf),
            },
        })

    return {"ok": True, "periodo": periodo, "portafolios": resultado}


# ── LEADS DEL DÍA POR PÁGINA/VENDEDOR ────────────────────────────────────────

@router.get("/api/meta/leads-stats")
async def leads_stats_por_pagina(
    periodo: str = "hoy",   # hoy | semana | mes
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    from datetime import datetime
    import pytz

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    ahora = datetime.now(tz)
    hoy = ahora.date()

    if periodo == "hoy":
        desde = datetime(hoy.year, hoy.month, hoy.day, tzinfo=tz)
    elif periodo == "semana":
        lun = hoy - timedelta(days=hoy.weekday())
        desde = datetime(lun.year, lun.month, lun.day, tzinfo=tz)
    elif periodo == "mes":
        desde = datetime(hoy.year, hoy.month, 1, tzinfo=tz)
    else:
        desde = datetime(hoy.year, hoy.month, hoy.day, tzinfo=tz)

    # Agrupar leads por página Meta y por asesor
    from sqlalchemy import and_
    leads = (
        db.query(Lead)
        .filter(Lead.created_at >= desde)
        .all()
    )

    paginas_idx = {pg.page_id: pg for pg in db.query(MetaPagina).all()}
    # Índice asesor_id → nombre
    from database.models import Usuario as U
    asesores = {u.id: u.nombre for u in db.query(U).all()}

    por_pagina: dict = {}
    sin_pagina = []
    for lead in leads:
        pid = getattr(lead, "meta_pagina_id", None)
        if pid and pid in paginas_idx:
            pg = paginas_idx[pid]
            key = pid
            if key not in por_pagina:
                por_pagina[key] = {
                    "page_id": pid,
                    "pagina": pg.nombre,
                    "vendedor": pg.vendedor or pg.nombre,
                    "whatsapp": pg.numero_whatsapp,
                    "portafolio": pg.portafolio,
                    "leads": 0,
                }
            por_pagina[key]["leads"] += 1
        else:
            asesor_id = lead.asesor_apertura_id
            asesor_nom = asesores.get(asesor_id, f"Asesor #{asesor_id}") if asesor_id else "Sin asignar"
            sin_pagina.append(asesor_nom)

    return {
        "ok": True,
        "periodo": periodo,
        "total_leads": len(leads),
        "por_pagina": list(por_pagina.values()),
        "sin_pagina": len(sin_pagina),
    }


# ── ASOCIAR PÁGINA META A UN LEAD ────────────────────────────────────────────

@router.patch("/api/leads/{lead_id}/meta-pagina")
async def asignar_pagina_a_lead(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    page_id = (data.get("page_id") or "").strip()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    lead.meta_pagina_id = page_id or None
    # Rellenar utm_campaign si viene
    if data.get("utm_campaign"):
        lead.utm_campaign = data["utm_campaign"]
    db.commit()
    return {"ok": True}


# ── SYNC DIARIO DE SNAPSHOTS (llamado por cron vía API key) ──────────────────

_API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


def _require_api_key_meta(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    key = auth.removeprefix("Bearer ").strip()
    if key != _API_KEY:
        raise HTTPException(401, "API key inválida")
    return True


@router.post("/api/meta/sync-snapshots")
async def sync_snapshots(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key_meta),
):
    """
    Recorre todos los portafolios activos, obtiene métricas del día
    de cada campaña activa y guarda/actualiza un snapshot diario.
    Llamado por el cron de eco-multiagente a las 23:55 ARG.
    """
    hoy = date.today()
    hoy_str = hoy.isoformat()
    guardados = 0
    errores = []

    portafolios = db.query(MetaPortafolio).filter_by(activo=True).all()

    for pf in portafolios:
        if not pf.ad_account_id or not pf.system_token_enc:
            continue
        try:
            token = decrypt_value(pf.system_token_enc)
            acc_id = pf.ad_account_id if pf.ad_account_id.startswith("act_") else f"act_{pf.ad_account_id}"
            params = {
                "fields": (
                    "id,name,status,daily_budget,lifetime_budget,"
                    f'insights.time_range({{"since":"{hoy_str}","until":"{hoy_str}"}})'
                    "{spend,impressions,clicks,actions}"
                ),
                "effective_status": '["ACTIVE","PAUSED"]',
                "limit": 100,
            }
            raw = await _ads_get(token, f"{acc_id}/campaigns", params)
        except Exception as e:
            errores.append(f"{pf.nombre}: {e}")
            continue

        for c in raw.get("data", []):
            try:
                insights = (c.get("insights") or {}).get("data", [{}])[0] if c.get("insights") else {}
                spend = float(insights.get("spend") or 0)
                impressions = int(insights.get("impressions") or 0)
                clicks = int(insights.get("clicks") or 0)
                actions = insights.get("actions") or []
                leads = sum(
                    int(a.get("value") or 0) for a in actions
                    if a.get("action_type") in (
                        "messaging_conversation_started_7d",
                        "onsite_conversion.messaging_conversation_started_7d",
                        "lead",
                    )
                )
                cpl = round(spend / leads, 2) if leads > 0 else None
                daily_budget = float(c.get("daily_budget") or 0) / 100 or None
                lifetime_budget = float(c.get("lifetime_budget") or 0) / 100 or None

                snap = (
                    db.query(MetaCampanaSnapshot)
                    .filter_by(campaign_id=c["id"], fecha=hoy)
                    .first()
                )
                if snap is None:
                    snap = MetaCampanaSnapshot(
                        portafolio_slug=pf.slug or str(pf.id),
                        campaign_id=c["id"],
                        campaign_name=c["name"],
                        fecha=hoy,
                    )
                    db.add(snap)

                snap.campaign_name = c["name"]
                snap.status = c.get("status", "ACTIVE")
                snap.spend = spend
                snap.impressions = impressions
                snap.clicks = clicks
                snap.leads = leads
                snap.cpl = cpl
                snap.daily_budget = daily_budget
                snap.lifetime_budget = lifetime_budget
                snap.raw_json = json.dumps(insights)
                guardados += 1
            except Exception as e:
                errores.append(f"campaña {c.get('id')}: {e}")

    db.commit()
    log.info(f"[MetaSync] {guardados} snapshots guardados para {hoy_str}, {len(errores)} errores")
    return {"ok": True, "fecha": hoy_str, "guardados": guardados, "errores": errores}


# ── ADS FRONTEND (/api/ads/...) ───────────────────────────────────────────────
# Endpoints que consume el template meta_ads.html

async def _ads_post(token: str, path: str, payload: dict, timeout: int = 20) -> dict:
    url = f"{META_GRAPH}/{path.lstrip('/')}"
    payload = {**payload, "access_token": token}
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.post(url, data=payload)
    body = r.json() if r.content else {}
    if r.status_code not in (200, 201) or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", f"Meta API error: {r.text[:200]}"))
    return body


async def _ads_delete(token: str, object_id: str, timeout: int = 20) -> dict:
    url = f"{META_GRAPH}/{object_id}"
    async with httpx.AsyncClient(timeout=timeout) as hc:
        r = await hc.delete(url, params={"access_token": token})
    body = r.json() if r.content else {}
    if r.status_code not in (200, 204) or "error" in body:
        err = body.get("error", {})
        raise HTTPException(400, err.get("message", f"Meta API error: {r.text[:200]}"))
    return body


def _fmt_ars(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


def _resolver_portafolio(db: "Session", portafolio_id: Optional[int], campaign_id: Optional[str]) -> Optional["MetaPortafolio"]:
    if portafolio_id:
        return db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if campaign_id:
        snap = (
            db.query(MetaCampanaSnapshot)
            .filter_by(campaign_id=campaign_id)
            .order_by(MetaCampanaSnapshot.fecha.desc())
            .first()
        )
        if snap:
            return db.query(MetaPortafolio).filter_by(slug=snap.portafolio_slug).first()
    return None


@router.get("/api/ads/resumen")
async def ads_resumen(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    from sqlalchemy import extract
    hoy = date.today()
    # Intentar snapshots de hoy; si no hay, usar el mes actual agrupado por campaña
    snaps = db.query(MetaCampanaSnapshot).filter_by(fecha=hoy).all()
    if not snaps:
        todos = db.query(MetaCampanaSnapshot).filter(
            extract("year", MetaCampanaSnapshot.fecha) == hoy.year,
            extract("month", MetaCampanaSnapshot.fecha) == hoy.month,
        ).all()
        best: dict = {}
        for s in todos:
            if s.campaign_id not in best or s.fecha > best[s.campaign_id].fecha:
                best[s.campaign_id] = s
        snaps = list(best.values())
    gasto = sum(s.spend or 0 for s in snaps)
    return {
        "gasto_total_mes": _fmt_ars(gasto),
        "campanas_activas": sum(1 for s in snaps if s.status == "ACTIVE"),
        "campanas_pausadas": sum(1 for s in snaps if s.status == "PAUSED"),
    }


@router.get("/api/ads/cuentas")
async def ads_cuentas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    portafolios = db.query(MetaPortafolio).filter_by(activo=True).order_by(MetaPortafolio.nombre).all()
    STATUS_LABEL = {1: "Activa", 2: "Desactivada", 3: "Sin saldo", 7: "Inactiva", 101: "Liquidación", 201: "Pendiente"}
    cuentas = []
    for pf in portafolios:
        if not pf.ad_account_id or not pf.system_token_enc:
            cuentas.append({
                "id": pf.id,
                "name": pf.nombre,
                "currency": "ARS",
                "account_status": 0,
                "status_label": "Sin configurar",
                "gasto_display": "—",
            })
            continue
        token = decrypt_value(pf.system_token_enc)
        acc_id = pf.ad_account_id if pf.ad_account_id.startswith("act_") else f"act_{pf.ad_account_id}"
        try:
            data = await _ads_get(token, acc_id, {"fields": "name,amount_spent,currency,account_status"})
            status = int(data.get("account_status") or 0)
            gastado = float(data.get("amount_spent") or 0) / 100
            cuentas.append({
                "id": pf.id,
                "name": data.get("name") or pf.nombre,
                "currency": data.get("currency", "ARS"),
                "account_status": status,
                "status_label": STATUS_LABEL.get(status, str(status)),
                "gasto_display": _fmt_ars(gastado),
                "meta_account_id": pf.ad_account_id,
            })
        except HTTPException as e:
            cuentas.append({
                "id": pf.id,
                "name": pf.nombre,
                "currency": "ARS",
                "account_status": 0,
                "status_label": "Error al conectar",
                "gasto_display": "—",
                "error": e.detail,
            })
    return {"cuentas": cuentas}


@router.get("/api/ads/cuentas/{portafolio_id}/campanias")
async def ads_campanas_por_portafolio(
    portafolio_id: int,
    periodo: str = "mes",
    solo_activas: bool = False,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = db.query(MetaPortafolio).filter_by(id=portafolio_id, activo=True).first()
    if not pf:
        raise HTTPException(404, "Portafolio no encontrado")
    if not pf.ad_account_id or not pf.system_token_enc:
        return {"ok": False, "campanas": [], "error": "Portafolio sin cuenta o token configurado"}
    token = decrypt_value(pf.system_token_enc)
    acc_id = pf.ad_account_id if pf.ad_account_id.startswith("act_") else f"act_{pf.ad_account_id}"
    date_start, date_end = _date_range(periodo)
    insight_fields = "spend,impressions,clicks,reach,actions"
    _ins_mod = (
        "date_preset(maximum)"
        if periodo == "maximo"
        else f'time_range({{"since":"{date_start}","until":"{date_end}"}})'
    )
    status_filter = '["ACTIVE"]' if solo_activas else '["ACTIVE","PAUSED","ARCHIVED"]'
    params: dict = {
        "fields": f"id,name,status,daily_budget,lifetime_budget,objective,insights.{_ins_mod}{{{insight_fields}}}",
        "effective_status": status_filter,
        "limit": 100,
    }
    try:
        raw = await _ads_get(token, f"{acc_id}/campaigns", params)
    except HTTPException as e:
        return {"ok": False, "campanas": [], "error": e.detail}
    campanas = []
    for c in raw.get("data", []):
        ins = (c.get("insights") or {}).get("data", [{}])[0] if c.get("insights") else {}
        spend = float(ins.get("spend") or 0)
        imp = int(ins.get("impressions") or 0)
        reach = int(ins.get("reach") or 0)
        clicks = int(ins.get("clicks") or 0)
        actions = ins.get("actions") or []
        leads = sum(
            int(a.get("value") or 0) for a in actions
            if a.get("action_type") in (
                "messaging_conversation_started_7d",
                "onsite_conversion.messaging_conversation_started_7d",
                "lead",
            )
        )
        cpl = round(spend / leads, 2) if leads > 0 else None
        ctr = round(clicks / imp * 100, 2) if imp > 0 else 0
        campanas.append({
            "id": c["id"],
            "nombre": c["name"],
            "status": c.get("status"),
            "objetivo": c.get("objective"),
            "daily_budget": float(c.get("daily_budget") or 0) / 100 or None,
            "lifetime_budget": float(c.get("lifetime_budget") or 0) / 100 or None,
            "metricas": {
                "gasto": _fmt_ars(spend),
                "impresiones": imp,
                "alcance": reach,
                "clics": clicks,
                "leads": leads,
                "cpl": _fmt_ars(cpl) if cpl else None,
                "ctr": f"{ctr:.1f}%",
                "spend_raw": spend,
            },
        })
    return {"ok": True, "campanas": campanas}


@router.patch("/api/ads/campanias/{campaign_id}/estado")
async def ads_toggle_campana(
    campaign_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    status = data.get("status")
    if not status or status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(400, "status debe ser ACTIVE o PAUSED")
    pf = _resolver_portafolio(db, data.get("portafolio_id"), campaign_id)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio. Incluí portafolio_id en el body.")
    token = decrypt_value(pf.system_token_enc)
    await _ads_post(token, campaign_id, {"status": status})
    return {"ok": True}


@router.get("/api/ads/campanias/{campaign_id}/conjuntos")
async def ads_conjuntos(
    campaign_id: str,
    portafolio_id: Optional[int] = None,
    periodo: str = "mes",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, campaign_id)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio para esta campaña")
    token = decrypt_value(pf.system_token_enc)
    date_start, date_end = _date_range(periodo)
    _ins_mod = f'time_range({{"since":"{date_start}","until":"{date_end}"}})'
    params: dict = {
        "fields": f"id,name,status,optimization_goal,insights.{_ins_mod}{{spend,impressions,clicks,reach}}",
        "limit": 100,
    }
    try:
        raw = await _ads_get(token, f"{campaign_id}/adsets", params)
    except HTTPException as e:
        return {"ok": False, "conjuntos": [], "error": e.detail}
    conjuntos = []
    for cs in raw.get("data", []):
        ins = (cs.get("insights") or {}).get("data", [{}])[0] if cs.get("insights") else {}
        spend = float(ins.get("spend") or 0)
        conjuntos.append({
            "id": cs["id"],
            "name": cs["name"],
            "status": cs.get("status"),
            "optimization_goal": cs.get("optimization_goal"),
            "metricas": {
                "gasto": _fmt_ars(spend),
                "impresiones": int(ins.get("impressions") or 0),
                "alcance": int(ins.get("reach") or 0),
                "clics": int(ins.get("clicks") or 0),
            },
        })
    return {"ok": True, "conjuntos": conjuntos}


@router.patch("/api/ads/conjuntos/{adset_id}/estado")
async def ads_toggle_conjunto(
    adset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    status = data.get("status")
    if not status or status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(400, "status debe ser ACTIVE o PAUSED")
    pf = _resolver_portafolio(db, data.get("portafolio_id"), None)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "Incluí portafolio_id en el body")
    token = decrypt_value(pf.system_token_enc)
    await _ads_post(token, adset_id, {"status": status})
    return {"ok": True}


@router.get("/api/ads/campanias/{campaign_id}/anuncios")
async def ads_anuncios(
    campaign_id: str,
    portafolio_id: Optional[int] = None,
    periodo: str = "mes",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, campaign_id)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio para esta campaña")
    token = decrypt_value(pf.system_token_enc)
    date_start, date_end = _date_range(periodo)
    _ins_mod = f'time_range({{"since":"{date_start}","until":"{date_end}"}})'
    params: dict = {
        "fields": f"id,name,status,creative{{thumbnail_url,title}},insights.{_ins_mod}{{spend,impressions,clicks,reach,ctr,cpc}}",
        "limit": 100,
    }
    try:
        raw = await _ads_get(token, f"{campaign_id}/ads", params)
    except HTTPException as e:
        return {"ok": False, "anuncios": [], "error": e.detail}
    anuncios = []
    for ad in raw.get("data", []):
        ins = (ad.get("insights") or {}).get("data", [{}])[0] if ad.get("insights") else {}
        spend = float(ins.get("spend") or 0)
        anuncios.append({
            "id": ad["id"],
            "name": ad["name"],
            "status": ad.get("status"),
            "creative": ad.get("creative"),
            "metricas": {
                "gasto": _fmt_ars(spend),
                "impresiones": int(ins.get("impressions") or 0),
                "alcance": int(ins.get("reach") or 0),
                "clics": int(ins.get("clicks") or 0),
                "ctr": ins.get("ctr"),
                "cpc": ins.get("cpc"),
            },
        })
    return {"ok": True, "anuncios": anuncios}


@router.get("/api/ads/campanias/{campaign_id}/comentarios")
async def ads_comentarios(
    campaign_id: str,
    portafolio_id: Optional[int] = None,
    solo_negativos: bool = False,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    # Los comentarios requieren token de página (page access token) — stub por ahora
    return {"ok": True, "comentarios": []}


@router.delete("/api/ads/comentarios/{comment_id}")
async def ads_eliminar_comentario(
    comment_id: str,
    portafolio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, None)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "Pasá portafolio_id como query param")
    token = decrypt_value(pf.system_token_enc)
    await _ads_post(token, comment_id, {"method": "delete"})
    return {"ok": True}


# ── CREAR CAMPAÑA ─────────────────────────────────────────────────────────────

@router.post("/api/ads/campanias")
async def ads_crear_campana(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    portafolio_id = data.get("portafolio_id")
    if not portafolio_id:
        raise HTTPException(400, "Se requiere portafolio_id")
    pf = db.query(MetaPortafolio).filter_by(id=portafolio_id).first()
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "Portafolio no encontrado o sin token")
    if not pf.ad_account_id:
        raise HTTPException(400, "El portafolio no tiene ad_account_id configurado")
    token = decrypt_value(pf.system_token_enc)
    payload = {
        "name": data.get("name", "").strip(),
        "objective": data.get("objective", "OUTCOME_LEADS"),
        "status": data.get("status", "PAUSED"),
        "special_ad_categories": "[]",
    }
    if not payload["name"]:
        raise HTTPException(400, "Se requiere name")
    if data.get("daily_budget"):
        payload["daily_budget"] = int(float(data["daily_budget"]) * 100)
    elif data.get("lifetime_budget"):
        payload["lifetime_budget"] = int(float(data["lifetime_budget"]) * 100)
    result = await _ads_post(token, f"{pf.ad_account_id}/campaigns", payload)
    return {"ok": True, "id": result.get("id")}


# ── ELIMINAR CAMPAÑA ──────────────────────────────────────────────────────────

@router.delete("/api/ads/campanias/{campaign_id}")
async def ads_eliminar_campana(
    campaign_id: str,
    portafolio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, campaign_id)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio. Incluí portafolio_id.")
    token = decrypt_value(pf.system_token_enc)
    await _ads_delete(token, campaign_id)
    return {"ok": True}


# ── CREAR CONJUNTO DE ANUNCIOS ────────────────────────────────────────────────

@router.post("/api/ads/campanias/{campaign_id}/conjuntos")
async def ads_crear_conjunto(
    campaign_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    portafolio_id = data.get("portafolio_id")
    pf = _resolver_portafolio(db, portafolio_id, campaign_id)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio")
    if not pf.ad_account_id:
        raise HTTPException(400, "El portafolio no tiene ad_account_id configurado")
    token = decrypt_value(pf.system_token_enc)
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Se requiere name")
    targeting = data.get("targeting") or {"geo_locations": {"countries": ["AR"]}}
    payload = {
        "name": name,
        "campaign_id": campaign_id,
        "optimization_goal": data.get("optimization_goal", "LEAD_GENERATION"),
        "billing_event": data.get("billing_event", "IMPRESSIONS"),
        "bid_strategy": data.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
        "targeting": json.dumps(targeting),
        "status": data.get("status", "PAUSED"),
    }
    if data.get("daily_budget"):
        payload["daily_budget"] = int(float(data["daily_budget"]) * 100)
    if data.get("start_time"):
        payload["start_time"] = data["start_time"]
    if data.get("end_time"):
        payload["end_time"] = data["end_time"]
    result = await _ads_post(token, f"{pf.ad_account_id}/adsets", payload)
    return {"ok": True, "id": result.get("id")}


# ── ELIMINAR CONJUNTO ─────────────────────────────────────────────────────────

@router.delete("/api/ads/conjuntos/{adset_id}")
async def ads_eliminar_conjunto(
    adset_id: str,
    portafolio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, None)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "Pasá portafolio_id como query param")
    token = decrypt_value(pf.system_token_enc)
    await _ads_delete(token, adset_id)
    return {"ok": True}


# ── ELIMINAR ANUNCIO ──────────────────────────────────────────────────────────

@router.delete("/api/ads/anuncios/{ad_id}")
async def ads_eliminar_anuncio(
    ad_id: str,
    portafolio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    pf = _resolver_portafolio(db, portafolio_id, None)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "Pasá portafolio_id como query param")
    token = decrypt_value(pf.system_token_enc)
    await _ads_delete(token, ad_id)
    return {"ok": True}


# ── PÁGINAS DEL PORTAFOLIO (para selector en crear anuncio) ───────────────────

@router.get("/api/ads/portafolios/{portafolio_id}/paginas")
async def ads_paginas_portafolio(
    portafolio_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    paginas = db.query(MetaPagina).filter_by(activa=True).order_by(MetaPagina.nombre).all()
    return {"ok": True, "paginas": [
        {"page_id": p.page_id, "nombre": p.nombre, "portafolio": p.portafolio or ""}
        for p in paginas
    ]}


# ── CREAR ANUNCIO (creative + ad en un paso) ──────────────────────────────────

@router.post("/api/ads/conjuntos/{adset_id}/anuncios")
async def ads_crear_anuncio(
    adset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_access(current_user, db)
    data = await request.json()
    portafolio_id = data.get("portafolio_id")
    pf = _resolver_portafolio(db, portafolio_id, None)
    if not pf or not pf.system_token_enc:
        raise HTTPException(400, "No se pudo determinar el portafolio. Incluí portafolio_id.")
    if not pf.ad_account_id:
        raise HTTPException(400, "El portafolio no tiene ad_account_id configurado")
    token = decrypt_value(pf.system_token_enc)

    name      = (data.get("name") or "").strip()
    page_id   = (data.get("page_id") or "").strip()
    message   = (data.get("message") or "").strip()
    headline  = (data.get("headline") or "").strip()
    description = (data.get("description") or "").strip()
    link      = (data.get("link") or "").strip()
    cta_type  = data.get("cta_type") or "LEARN_MORE"
    status    = data.get("status") or "PAUSED"
    image_url = (data.get("image_url") or "").strip()
    image_b64 = (data.get("image_b64") or "").strip()

    if not name:     raise HTTPException(400, "Se requiere name")
    if not page_id:  raise HTTPException(400, "Se requiere page_id")
    if not link:     raise HTTPException(400, "Se requiere link (URL de destino)")
    if not message:  raise HTTPException(400, "Se requiere message (texto principal)")
    if not image_url and not image_b64:
        raise HTTPException(400, "Se requiere imagen (image_url o image_b64)")

    # 1. Subir imagen si viene en base64
    image_hash = None
    if image_b64:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        async with httpx.AsyncClient(timeout=60) as hc:
            r = await hc.post(
                f"{META_GRAPH}/{pf.ad_account_id}/adimages",
                data={"bytes": image_b64, "access_token": token},
            )
        body = r.json() if r.content else {}
        if r.status_code not in (200, 201) or "error" in body:
            err = body.get("error", {})
            raise HTTPException(400, f"Error subiendo imagen a Meta: {err.get('message', r.text[:200])}")
        for _fname, img_info in (body.get("images") or {}).items():
            image_hash = img_info.get("hash")
            break
        if not image_hash:
            raise HTTPException(500, "Meta no devolvió hash de imagen")

    # 2. Armar link_data
    link_data: dict = {
        "link": link,
        "message": message,
        "call_to_action": {"type": cta_type, "value": {"link": link}},
    }
    if headline:    link_data["name"] = headline
    if description: link_data["description"] = description
    if image_hash:  link_data["image_hash"] = image_hash
    elif image_url: link_data["picture"] = image_url

    # 3. Crear adcreative
    creative_result = await _ads_post(token, f"{pf.ad_account_id}/adcreatives", {
        "name": f"Creative — {name}",
        "object_story_spec": json.dumps({"page_id": page_id, "link_data": link_data}),
    })
    creative_id = creative_result.get("id")
    if not creative_id:
        raise HTTPException(500, "Meta no devolvió creative_id")

    # 4. Crear anuncio
    ad_result = await _ads_post(token, f"{pf.ad_account_id}/ads", {
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": status,
    })
    return {"ok": True, "id": ad_result.get("id"), "creative_id": creative_id}
