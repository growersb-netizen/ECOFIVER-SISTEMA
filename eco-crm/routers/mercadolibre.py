"""
Módulo 13 — MercadoLibre
Publicaciones, creación con IA, sincronización de precios y renovación automática.
Acceso: ADMIN y COORDINADOR_OPERATIVO
"""
import os
import json
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PublicacionML, Usuario, ConfiguracionSistema, BorradorML, MLCategoriaLinea, RespuestaAutoML
from routers.auth import require_auth, get_user_roles, get_current_user
from routers.configuracion import get_config_value, _require_config_access
from database.encryption import encrypt_value
from utils.ai_client import ai_complete
from utils.contexto_ecofiver import ctx_empresa, ctx_preguntas_ml, ctx_seo_ml

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")
ML_BASE = "https://api.mercadolibre.com"
ML_AUTH = "https://auth.mercadolibre.com.ar"
ML_DEFAULT_REDIRECT = "https://eco-crm-production.up.railway.app/mercadolibre/callback"

# Job tracker en memoria para tareas largas (actualización de descripciones, etc.)
_DESC_JOBS: Dict[str, Dict[str, Any]] = {}


def _agregar_condiciones(db: Session, descripcion: str) -> str:
    """Mantiene compatibilidad — usa _armar_descripcion_ml internamente."""
    return _armar_descripcion_ml(db, descripcion)


def _armar_descripcion_ml(db: Session, descripcion: str, tipo: str = "completo") -> str:
    """
    Construye la descripción final para ML según el tipo de publicación:
      - tipo="completo"   → encabezado y pie de precio completo
      - tipo="referencia" → encabezado y pie de precio de referencia/cotización

    Estructura: [Encabezado] + producto + [Palabras clave] + [Condiciones] + [Pie]
    No duplica bloques si ya están presentes en la descripción.
    """
    if tipo == "referencia":
        encabezado = (get_config_value("ml_desc_encabezado_referencia", db) or "").strip()
        pie        = (get_config_value("ml_desc_pie_referencia", db) or "").strip()
    else:
        encabezado = (get_config_value("ml_desc_encabezado", db) or "").strip()
        pie        = (get_config_value("ml_desc_pie", db) or "").strip()

    keywords = (get_config_value("ml_desc_keywords", db) or "").strip()

    try:
        from routers.negocio import _get as _get_negocio
        condiciones = (_get_negocio(db, "negocio_condiciones") or "").strip()
    except Exception:
        condiciones = ""

    descripcion = (descripcion or "").strip()
    partes = []

    if encabezado and encabezado not in descripcion:
        partes.append(encabezado)
    partes.append(descripcion)
    if keywords and keywords not in descripcion:
        partes.append(keywords)
    if condiciones and condiciones not in descripcion:
        partes.append(condiciones)
    if pie and pie not in descripcion:
        partes.append(pie)

    return "\n\n".join(p for p in partes if p)


def _ml_save(db: Session, clave: str, valor: str, secreto: bool = False):
    """Upsert de un valor de config (encripta si es secreto)."""
    stored = encrypt_value(valor) if (secreto and valor) else valor
    e = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if e:
        e.valor = stored
        e.es_secreto = secreto
        e.estado = "activa" if valor else "sin_configurar"
    else:
        db.add(ConfiguracionSistema(clave=clave, valor=stored, es_secreto=secreto,
                                    estado="activa" if valor else "sin_configurar"))
    db.commit()


def _ml_redirect_uri(db: Session) -> str:
    return get_config_value("ml_redirect_uri", db) or ML_DEFAULT_REDIRECT


async def _ml_valid_token(db: Session) -> str:
    """
    Devuelve un access token válido, refrescándolo con el refresh_token si venció.
    Los tokens de ML duran 6 horas; se refrescan automáticamente.
    """
    token = get_config_value("ml_access_token", db)
    expira = get_config_value("ml_token_expira", db)
    vencido = True
    if token and expira:
        try:
            vencido = datetime.fromisoformat(expira) <= datetime.utcnow() + timedelta(minutes=5)
        except Exception:
            vencido = True
    if token and not vencido:
        return token

    # Refrescar
    refresh = get_config_value("ml_refresh_token", db)
    cid = get_config_value("ml_client_id", db)
    csec = get_config_value("ml_client_secret", db)
    if not (refresh and cid and csec):
        if token:
            return token  # sin refresh disponible, probamos con el que hay
        raise HTTPException(400, "MercadoLibre no está conectado. Andá a MercadoLibre → Conectar.")

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{ML_BASE}/oauth/token", data={
            "grant_type": "refresh_token", "client_id": cid,
            "client_secret": csec, "refresh_token": refresh,
        }, headers={"Accept": "application/json"})
    if r.status_code != 200:
        raise HTTPException(400, f"No se pudo refrescar el token de ML: {r.text[:200]}")
    j = r.json()
    _guardar_tokens(db, j)
    return j["access_token"]


def _guardar_tokens(db: Session, j: dict):
    _ml_save(db, "ml_access_token", j.get("access_token", ""), secreto=True)
    if j.get("refresh_token"):
        _ml_save(db, "ml_refresh_token", j["refresh_token"], secreto=True)
    if j.get("user_id"):
        _ml_save(db, "ml_user_id", str(j["user_id"]), secreto=False)
    exp = datetime.utcnow() + timedelta(seconds=int(j.get("expires_in", 21600)))
    _ml_save(db, "ml_token_expira", exp.isoformat(), secreto=False)

# Categorías ML de emergencia (si falla el predictor Y no hay cache en BD)
ML_CATEGORIAS = {
    "PISCINA":              "MLA9226",    # Piletas y Jacuzzis
    "MINIPISCINA":          "MLA9226",
    "HIDROMASAJE":          "MLA9226",    # el predictor refina a Jacuzzis e Hidromasajes
    "MODULO":               "MLA1647",    # Casas Prefabricadas
    "MODULO_DEPOSITO":      "MLA1647",
    "COMBO":                "MLA9226",
    "QUINCHO":              "MLA1647",
    "PERGOLA":              "MLA1647",
}
# Nota: BANIO_QUIMICO, GARITA_SEGURIDAD, CUCHA, REPOSERA_FIBRA, EQUIPO_PISCINA, etc.
# no tienen fallback fijo — el predictor ML los resuelve por título y los cachea en BD.

# Líneas de producto propias con un título de referencia para resolver su
# categoría ML una sola vez (vía category_predictor) y cachearla en BD.
# Las líneas con título_referencia=None son demasiado heterogéneas para una
# categoría fija (ej. "importados varios" puede ser cualquier cosa): para
# esas SIEMPRE se predice en vivo con el título real del producto.
LINEAS_PRODUCTO = {
    # ── Piscinas e hidromasajes ────────────────────────────────────────────
    "PISCINA":              "Pileta de Fibra de Vidrio",
    "MINIPISCINA":          "Pileta Pequeña de Fibra de Vidrio Autoinstalable",
    "HIDROMASAJE":          "Hidromasaje Jacuzzi Spa Acrílico Autoportante",
    "ACCESORIO_HIDROMASAJE": None,       # heterogéneos → predictor usa el título real
    # ── Módulos y estructuras ─────────────────────────────────────────────
    "MODULO":               "Casa Modulo Habitacional Industrializado",
    "MODULO_DEPOSITO":      "Modulo de Chapa para Deposito",
    "QUINCHO":              "Quincho Prefabricado de Madera",
    "PERGOLA":              "Pergola Gazebo de Madera para Jardin",
    "COMBO":                "Combo Pileta de Fibra de Vidrio con Modulo",
    # ── Prefabricados varios ──────────────────────────────────────────────
    "BANIO_QUIMICO":        "Bano Quimico Portatil",
    "GARITA_SEGURIDAD":     "Garita de Seguridad Prefabricada",
    "DEPOSITO_JARDIN":      "Deposito para Jardin de Chapa",
    # ── Accesorios y equipos ──────────────────────────────────────────────
    "ACCESORIO_PISCINA":    "Accesorio para Pileta de Natacion",
    "ILUMINACION_PISCINA":  "Luz LED Sumergible para Pileta",
    "EQUIPO_PISCINA":       "Bomba Filtradora para Piscina",
    "REPUESTO_PISCINA":     None,        # heterogéneos → predictor usa el título real
    # ── Bañeras y receptáculos ────────────────────────────────────────────
    "BANERA":               "Bañera de Acrílico Sanitario Autoportante",
    "RECEPTACULO":          "Receptáculo de Ducha Acrílico",
    # ── Otros productos EcoFiver ─────────────────────────────────────────
    "CUCHA":                "Cucha para Perro de Madera Grande",
    "CUCHA_PERRO":          "Cucha para Perro de Madera Grande",  # alias legacy
    "REPOSERA_FIBRA":       "Reposera de Fibra de Vidrio Reclinable",
    "ACCESORIO_MODULO":     "Placa de PVC para Pared",
    # ── Heterogéneos (sin categoría fija) ────────────────────────────────
    "CAMPING_PESCA":        None,
    "IMPORTADO_VARIOS":     None,
}


async def _ml_predecir_categoria(titulo: str, token: Optional[str] = None, limit: int = 1) -> list:
    """
    Predice la categoría real de ML a partir de un título, vía
    /sites/MLA/domain_discovery/search — /sites/MLA/category_predictor/predict
    (usado antes) empezó a devolver 404 "resource not found" para esta cuenta,
    confirmado en vivo; domain_discovery es el endpoint que sí funciona y de
    hecho da categorías más específicas (ej. "Piletas de Fibra" en vez del
    genérico "Piletas y Jacuzzis"). Ese endpoint no devuelve atributos, así
    que se piden aparte por categoría (solo para el resultado top, para no
    multiplicar llamadas).
    """
    headers = _ml_headers(token) if token else {}
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(
            f"{ML_BASE}/sites/MLA/domain_discovery/search",
            params={"q": titulo, "limit": max(1, min(limit, 8))},
            headers=headers,
        )
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Error prediciendo categoría en ML: {r.text[:200]}")
    predicciones = r.json()
    if isinstance(predicciones, dict):
        predicciones = [predicciones]

    resultado = []
    for i, p in enumerate(predicciones):
        cat_id = p.get("category_id")
        atributos = []
        if cat_id and i == 0:  # atributos solo para el top resultado
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    ra = await c.get(f"{ML_BASE}/categories/{cat_id}/attributes", headers=headers)
                if ra.status_code == 200:
                    for a in ra.json():
                        tags = a.get("tags") or {}
                        if tags.get("hidden") or tags.get("read_only"):
                            continue
                        atributos.append({
                            "id": a.get("id"), "name": a.get("name"),
                            "value_type": a.get("value_type"), "tags": tags,
                            "values": [v.get("name") for v in (a.get("values") or [])][:40],
                        })
            except Exception:
                pass
        resultado.append({
            "category_id": cat_id,
            "category_name": p.get("category_name"),
            "attributes": atributos,
        })
    return resultado


def _ml_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _get_token(db: Session) -> str:
    # Usa el token válido con auto-refresh (los tokens de ML vencen cada 6h)
    return await _ml_valid_token(db)


async def _get_user_id(token: str, db: Session) -> str:
    uid = get_config_value("ml_user_id", db)
    if uid:
        return uid
    # Obtener del API si no está cacheado
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{ML_BASE}/users/me", headers=_ml_headers(token))
    if r.status_code != 200:
        raise HTTPException(400, f"No se pudo obtener usuario ML: {r.status_code}")
    return str(r.json()["id"])


# ─── OAUTH — vinculación de la cuenta ─────────────────────────────────────────

@router.post("/api/ml/credenciales")
async def guardar_credenciales(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Guarda Client ID + Client Secret de la app de MercadoLibre (encriptado)."""
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")
    data = await request.json()
    cid = (data.get("client_id") or "").strip()
    csec = (data.get("client_secret") or "").strip()
    if not cid or not csec:
        raise HTTPException(400, "Faltan client_id o client_secret")
    _ml_save(db, "ml_client_id", cid, secreto=False)
    _ml_save(db, "ml_client_secret", csec, secreto=True)
    if data.get("redirect_uri"):
        _ml_save(db, "ml_redirect_uri", data["redirect_uri"].strip(), secreto=False)
    return {"ok": True, "client_id": cid, "redirect_uri": _ml_redirect_uri(db)}


@router.get("/mercadolibre/conectar")
async def ml_conectar(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Redirige al usuario a MercadoLibre para autorizar la app (OAuth)."""
    cid = get_config_value("ml_client_id", db)
    if not cid:
        raise HTTPException(400, "Primero cargá las credenciales (Client ID/Secret).")
    params = urlencode({
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": _ml_redirect_uri(db),
    })
    return RedirectResponse(url=f"{ML_AUTH}/authorization?{params}", status_code=302)


@router.get("/mercadolibre/callback")
async def ml_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Recibe el código de ML y lo intercambia por access + refresh token."""
    if error or not code:
        return RedirectResponse(url="/mercadolibre?ml=error", status_code=302)
    cid = get_config_value("ml_client_id", db)
    csec = get_config_value("ml_client_secret", db)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{ML_BASE}/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": cid, "client_secret": csec,
            "code": code, "redirect_uri": _ml_redirect_uri(db),
        }, headers={"Accept": "application/json"})
    if r.status_code != 200:
        return RedirectResponse(url="/mercadolibre?ml=error", status_code=302)
    _guardar_tokens(db, r.json())
    return RedirectResponse(url="/mercadolibre?ml=conectado", status_code=302)


@router.get("/api/ml/conexion")
async def ml_conexion(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Estado de la conexión OAuth con MercadoLibre."""
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")
    cid = get_config_value("ml_client_id", db)
    token = get_config_value("ml_access_token", db)
    uid = get_config_value("ml_user_id", db)
    nombre = None
    if token:
        try:
            tok = await _ml_valid_token(db)
            async with httpx.AsyncClient(timeout=8) as c:
                rr = await c.get(f"{ML_BASE}/users/me", headers=_ml_headers(tok))
            if rr.status_code == 200:
                nombre = rr.json().get("nickname")
        except Exception:
            pass
    return {
        "credenciales_cargadas": bool(cid),
        "conectado": bool(token and nombre),
        "user_id": uid,
        "nickname": nombre,
        "redirect_uri": _ml_redirect_uri(db),
    }


@router.post("/mercadolibre/notifications")
async def ml_notifications(request: Request, db: Session = Depends(get_db)):
    """
    Webhook público de MercadoLibre (Notifications callback URL).
    IMPORTANTE: hay que responder 200 rápido (ML reintenta y, si falla
    seguido, desactiva/revoca el permiso de la app). No requiere auth:
    lo llama MercadoLibre, no un usuario logueado.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        _ml_save(db, "ml_ultima_notificacion", json.dumps(data, ensure_ascii=False)[:2000], secreto=False)
    except Exception:
        pass
    return {"ok": True}


# ─── PÁGINAS ──────────────────────────────────────────────────────────────────

@router.get("/mercadolibre", response_class=HTMLResponse)
async def ml_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    roles = get_user_roles(current_user)
    catalogo_data = {"piscinas": {"modelos": [], "colores": [], "fotos": {}},
                      "modulos": {"modelos": [], "fotos": {}},
                      "modulos_deposito": {"tamanos": {}}}
    try:
        from routers.catalogo import load_catalogo, get_all_modelos_piscina, get_all_modelos_modulo
        cat = load_catalogo()
        catalogo_data = {
            "piscinas": {
                "modelos": get_all_modelos_piscina(),
                "colores": cat["piscinas"].get("colores", []),
                "fotos": cat["piscinas"].get("fotos", {}),
                "precios_lista": cat["piscinas"].get("precios_lista", {}),
                "cuotas_max": cat["piscinas"].get("cuotas_max", 36),
                "medidas": cat["piscinas"].get("medidas", {}),
            },
            "modulos": {
                "modelos": get_all_modelos_modulo(),
                "fotos": cat["modulos"].get("fotos", {}),
                "precios_lista": cat["modulos"].get("precios_lista", {}),
                "cuotas_max": cat["modulos"].get("cuotas_max", 60),
                "tecnologia": cat["modulos"].get("tecnologia", ""),
            },
            "modulos_deposito": cat.get("modulos_deposito", {"tamanos": {}}),
        }
    except Exception:
        pass
    return templates.TemplateResponse("mercadolibre.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "catalogo": catalogo_data,
    })


# ─── API — ESTADO ─────────────────────────────────────────────────────────────

@router.get("/api/ml/status")
async def ml_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    token = get_config_value("ml_access_token", db)
    if not token:
        return {"conectado": False, "msg": "Sin Access Token configurado"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{ML_BASE}/users/me", headers=_ml_headers(token))
        if r.status_code == 200:
            d = r.json()
            return {
                "conectado": True,
                "nickname": d.get("nickname"),
                "user_id": d.get("id"),
                "msg": f"Conectado como {d.get('nickname')}",
            }
        return {"conectado": False, "msg": f"Token inválido ({r.status_code})"}
    except Exception as e:
        return {"conectado": False, "msg": str(e)[:80]}


# ─── API — PUBLICACIONES ──────────────────────────────────────────────────────

async def _ml_visitas_items(token: str, item_ids: list) -> dict:
    """
    Visitas reales por publicación (últimos 2 años), vía /visits/items.
    OJO 1: esto NO es lo mismo que sold_quantity (que son ventas).
    OJO 2: ML solo permite UN item por consulta acá ("maximum amount of items
    to query is 1", confirmado con la API real) — antes se mandaban lotes de
    20 y ML devolvía 400 en silencio, por eso siempre daba 0. Se consulta de
    a una pero en paralelo (con límite de concurrencia) para que no sea lento.
    """
    resultado: dict = {}
    if not item_ids:
        return resultado

    sem = asyncio.Semaphore(10)

    async def _uno(iid: str):
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(f"{ML_BASE}/visits/items", headers=_ml_headers(token), params={"ids": iid})
                if r.status_code != 200:
                    return
                data = r.json()
                if isinstance(data, dict) and iid in data:
                    resultado[iid] = data[iid] or 0
            except Exception:
                pass

    await asyncio.gather(*[_uno(iid) for iid in item_ids])
    return resultado


_TIPO_CATALOGO_A_PRODUCTO = {
    "piscinas": ["PISCINA", "COMBO"],
    "modulos": ["MODULO"],
    "modulos_deposito": ["MODULO_DEPOSITO"],
}


async def _sincronizar_fotos_publicaciones(db: Session, tipo: str, clave: str, fotos: list) -> int:
    """
    Al cambiar las fotos de un modelo en el catálogo, actualiza automáticamente
    las fotos de todas las publicaciones ACTIVAS de MercadoLibre vinculadas a
    ese modelo (PublicacionML.modelo_especifico == clave) — para renovar fotos
    sin tener que entrar publicación por publicación. Best-effort por publicación:
    si una falla (ej. borrada en ML), sigue con las demás.
    """
    productos = _TIPO_CATALOGO_A_PRODUCTO.get(tipo)
    if not productos or not fotos:
        return 0
    token = get_config_value("ml_access_token", db)
    if not token:
        return 0

    publicaciones = db.query(PublicacionML).filter(
        PublicacionML.producto.in_(productos),
        PublicacionML.modelo_especifico == clave,
        PublicacionML.estado_ml == "active",
    ).all()
    if not publicaciones:
        return 0

    actualizadas = 0
    payload = {"pictures": [{"source": u} for u in fotos if u]}
    for pub in publicaciones:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.put(f"{ML_BASE}/items/{pub.item_id}", headers=_ml_headers(token), json=payload)
            if r.status_code in (200, 204):
                actualizadas += 1
        except Exception:
            continue
    return actualizadas


async def _fetch_publicaciones_activas(db: Session, token: str, user_id: str, limit: int = 1000) -> list:
    """
    Trae publicaciones activas con detalle + ventas + visitas reales. Compartido
    por el listado y el dashboard. Pagina hasta `limit` (ML devuelve máx 50 por
    página) para que el total no quede recortado — antes el listado mostraba
    solo las primeras 50 mientras el dashboard mostraba el total real de ML,
    lo que daba números inconsistentes entre pestañas.
    """
    item_ids: list = []
    offset = 0
    while len(item_ids) < limit:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{ML_BASE}/users/{user_id}/items/search",
                headers=_ml_headers(token),
                params={"limit": 50, "offset": offset},
            )
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Error ML: {r.text[:200]}")
        data = r.json()
        pagina = data.get("results", [])
        item_ids.extend(pagina)
        total_ml = data.get("paging", {}).get("total", len(item_ids))
        offset += 50
        if not pagina or len(item_ids) >= total_ml:
            break
    item_ids = item_ids[:limit]
    if not item_ids:
        return []

    items = []
    for i in range(0, len(item_ids), 20):
        batch = ",".join(item_ids[i:i + 20])
        async with httpx.AsyncClient(timeout=15) as c:
            r2 = await c.get(f"{ML_BASE}/items", headers=_ml_headers(token), params={"ids": batch})
        if r2.status_code != 200:
            continue
        for entry in r2.json():
            body = entry.get("body", {})
            if body:
                items.append(body)

    visitas_map = await _ml_visitas_items(token, [b.get("id") for b in items if b.get("id")])

    # Nombre de categoría por id, con cache — normalmente son pocas categorías
    # distintas por vendedor, no vale la pena una llamada por publicación.
    categoria_ids = {b.get("category_id") for b in items if b.get("category_id")}
    categoria_nombres: dict = {}
    for cid in categoria_ids:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                rc = await c.get(f"{ML_BASE}/categories/{cid}")
            if rc.status_code == 200:
                categoria_nombres[cid] = rc.json().get("name", cid)
        except Exception:
            pass

    return [{
        "item_id":      body.get("id"),
        "titulo":       body.get("title"),
        "precio":       body.get("price"),
        "estado_ml":    body.get("status"),
        "ventas":       body.get("sold_quantity", 0),
        "visitas":      visitas_map.get(body.get("id"), 0),
        "stock":        body.get("available_quantity", 0),
        "permalink":    body.get("permalink"),
        "thumbnail":    body.get("thumbnail"),
        "fecha_vencimiento": body.get("stop_time"),
        "categoria_id": body.get("category_id"),
        "categoria_nombre": categoria_nombres.get(body.get("category_id"), body.get("category_id")),
    } for body in items]


@router.get("/api/ml/publicaciones")
async def get_publicaciones(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    token = await _get_token(db)
    user_id = await _get_user_id(token, db)
    items = await _fetch_publicaciones_activas(db, token, user_id)

    # Sincronizar cache local
    for item in items:
        pub = db.query(PublicacionML).filter(PublicacionML.item_id == item["item_id"]).first()
        if pub:
            pub.titulo = item["titulo"] or pub.titulo
            pub.precio = item["precio"] or pub.precio
            pub.estado_ml = item["estado_ml"] or pub.estado_ml
        else:
            db.add(PublicacionML(
                item_id=item["item_id"],
                titulo=item["titulo"] or "",
                precio=item["precio"] or 0,
                estado_ml=item["estado_ml"] or "active",
            ))
    try:
        db.commit()
    except Exception:
        db.rollback()

    return items


@router.post("/api/ml/publicaciones/{item_id}/estado")
async def cambiar_estado_publicacion(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Pausa, activa, renueva o cierra (elimina) una publicación."""
    token = await _get_token(db)
    data = await request.json()
    accion = data.get("accion")  # pause | activate | renew | close

    payload: dict = {}
    if accion == "pause":
        payload = {"status": "paused"}
    elif accion == "activate":
        payload = {"status": "active"}
    elif accion == "renew":
        payload = {"status": "active"}
    elif accion == "close":
        # ML no permite borrado real de publicaciones con historial — el
        # equivalente real es cerrarla, que es lo mismo que ve el usuario
        # como "eliminar" (deja de estar activa y de listarse).
        payload = {"status": "closed"}
    else:
        raise HTTPException(400, "Acción inválida. Usar: pause | activate | renew | close")

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.put(
            f"{ML_BASE}/items/{item_id}",
            headers=_ml_headers(token),
            json=payload,
        )
    if r.status_code not in (200, 204):
        raise HTTPException(r.status_code, f"Error ML: {r.text[:200]}")

    # Actualizar cache
    pub = db.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()
    if pub:
        pub.estado_ml = payload.get("status", pub.estado_ml)
        db.commit()

    return {"ok": True, "item_id": item_id, "accion": accion}


@router.put("/api/ml/publicaciones/{item_id}")
async def editar_publicacion(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Edita título/precio/stock/descripción de una publicación ya activa en ML.
    Body: { titulo?, precio?, stock?, descripcion? } — solo se mandan los campos presentes.
    """
    token = await _get_token(db)
    data = await request.json()

    payload: dict = {}
    if "titulo" in data and data["titulo"]:
        payload["title"] = data["titulo"][:60]
    if "precio" in data and data["precio"]:
        payload["price"] = float(data["precio"])
    if "stock" in data and data["stock"] is not None:
        payload["available_quantity"] = int(data["stock"])

    if payload:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(f"{ML_BASE}/items/{item_id}", headers=_ml_headers(token), json=payload)
        if r.status_code not in (200, 204):
            raise HTTPException(r.status_code, f"Error ML al editar: {r.text[:300]}")

    if "descripcion" in data and data["descripcion"] is not None:
        descripcion_final = _agregar_condiciones(db, data["descripcion"])
        async with httpx.AsyncClient(timeout=15) as c:
            rd = await c.post(
                f"{ML_BASE}/items/{item_id}/description",
                headers=_ml_headers(token),
                json={"plain_text": descripcion_final},
            )
        if rd.status_code not in (200, 201):
            raise HTTPException(rd.status_code, f"Se guardaron los otros campos pero la descripción falló: {rd.text[:300]}")

    pub = db.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()
    if pub:
        if "titulo" in data and data["titulo"]:
            pub.titulo = data["titulo"][:60]
        if "precio" in data and data["precio"]:
            pub.precio = float(data["precio"])
        if "descripcion" in data and data["descripcion"] is not None:
            pub.descripcion = data["descripcion"]
        db.commit()

    return {"ok": True, "item_id": item_id}


# ─── API — GENERAR DESCRIPCIÓN CON CLAUDE ────────────────────────────────────

@router.post("/api/ml/generar-descripcion")
async def generar_descripcion(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Genera título + descripción comercial para una publicación de MercadoLibre
    a partir de palabras clave libres del producto. Usa el motor de IA unificado
    del CRM (hoy OpenRouter/gpt-4o-mini, con fallback a Grok/Gemini/Claude).
    """
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")

    data = await request.json()
    palabras = (data.get("palabras_clave") or data.get("keywords") or "").strip()
    # Compatibilidad con el formato viejo (tipo/modelo/color/superficie)
    tipo = data.get("tipo", "")
    modelo = data.get("modelo", "")
    color = data.get("color", "")
    superficie = data.get("superficie_m2", "")
    if not palabras:
        partes = [p for p in [tipo, modelo, color, f"{superficie}m²" if superficie else ""] if p]
        palabras = ", ".join(partes)
    if not palabras:
        raise HTTPException(400, "Ingresá algunas palabras clave del producto")

    prompt = f"""{ctx_seo_ml(descripcion_existente=palabras)}

════════════════════════════════════════════
TAREA: Generá un TÍTULO y una DESCRIPCIÓN para MercadoLibre Argentina.
════════════════════════════════════════════

Datos del producto a publicar:
{palabras}

Respondé EXCLUSIVAMENTE con este JSON válido, sin texto extra ni markdown:
{{"titulo": "...", "descripcion": "..."}}"""

    try:
        texto = await ai_complete(db, prompt, max_tokens=1400, temperature=0.6)
    except Exception as e:
        raise HTTPException(400, f"IA no disponible: {e}")

    try:
        result = json.loads(texto)
    except json.JSONDecodeError:
        import re as _re
        match = _re.search(r'\{.*\}', texto, _re.DOTALL)
        if not match:
            raise HTTPException(500, "La IA no devolvió un JSON válido")
        result = json.loads(match.group())

    return {
        "ok": True,
        "titulo": _sanear_titulo_ml(result.get("titulo") or ""),
        "descripcion": result.get("descripcion", ""),
    }


@router.post("/api/ml/generar-titulo")
async def generar_titulo(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Genera solo el título ML a partir de la descripción ya escrita del producto.
    Mucho más preciso que generarlo desde keywords, porque la IA tiene todo el contexto.
    """
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")

    data = await request.json()
    descripcion = (data.get("descripcion") or "").strip()[:800]
    tipo_producto = (data.get("tipo_producto") or "PISCINA").upper()

    if not descripcion:
        raise HTTPException(400, "Falta la descripción del producto")

    tipo_label = {
        "PISCINA":              "piscina / pileta de fibra de vidrio",
        "MINIPISCINA":          "minipiscina / pileta pequeña de fibra de vidrio",
        "HIDROMASAJE":          "hidromasaje / jacuzzi / spa de acrílico sanitario EcoFiver",
        "ACCESORIO_HIDROMASAJE":"accesorio opcional para hidromasaje / jacuzzi / spa",
        "MODULO":               "vivienda modular wood frame / casa prefabricada",
        "MODULO_DEPOSITO":      "módulo depósito / galpón prefabricado",
        "QUINCHO":              "quincho prefabricado",
        "PERGOLA":              "pérgola / gazebo",
        "COMBO":                "combo piscina y módulo habitacional",
        "BANIO_QUIMICO":        "baño químico portátil",
        "GARITA_SEGURIDAD":     "garita de seguridad prefabricada",
        "DEPOSITO_JARDIN":      "depósito de jardín prefabricado",
        "ACCESORIO_PISCINA":    "accesorio para piscina",
        "ILUMINACION_PISCINA":  "iluminación LED sumergible para piscina",
        "EQUIPO_PISCINA":       "equipo para piscina (filtro / bomba / calentador)",
        "REPUESTO_PISCINA":     "repuesto para piscina",
        "BANERA":               "bañera de acrílico sanitario",
        "RECEPTACULO":          "receptáculo de ducha de acrílico",
        "REPOSERA_FIBRA":       "reposera de fibra de vidrio reclinable",
        "CUCHA":                "cucha / casilla para perro",
        "CUCHA_PERRO":          "cucha / casilla para perro",
    }.get(tipo_producto, tipo_producto.lower())

    prompt = f"""{ctx_seo_ml(tipo_producto=tipo_label, descripcion_existente=descripcion)}

════════════════════════════════════════════
TAREA: Generá UN título optimizado para MercadoLibre Argentina.
════════════════════════════════════════════

Tipo de producto: {tipo_label}

Descripción de referencia:
{descripcion}

Respondé SOLO con el título, sin explicaciones ni comillas. Máximo 60 caracteres."""

    try:
        texto = await ai_complete(db, prompt, max_tokens=80, temperature=0.5)
    except Exception as e:
        raise HTTPException(400, f"IA no disponible: {e}")

    titulo = _sanear_titulo_ml(texto.strip().strip('"').strip("'"))
    return {"ok": True, "titulo": titulo}


def _sanear_titulo_ml(titulo: str) -> str:
    """
    Red de seguridad por si la IA no respeta las reglas al pie de la letra:
    saca signos que ML no indexa bien, corta en 60 caracteres sin partir palabras.
    """
    import re as _re
    limpio = _re.sub(r'[,|:;!?"–—_%]', ' ', titulo)
    limpio = _re.sub(r'\s+', ' ', limpio).strip()
    if len(limpio) <= 60:
        return limpio
    corte = limpio[:60]
    if ' ' in corte:
        corte = corte[:corte.rfind(' ')]
    return corte.strip()


# ─── API — CATEGORÍAS ML ───────────────────────────────────────────────────────

@router.get("/api/ml/categoria-predictor")
async def categoria_predictor(
    titulo: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Predicción en vivo de categoría ML a partir de un título (sin cachear).
    Usar para líneas heterogéneas (CAMPING_PESCA, IMPORTADO_VARIOS) o para
    previsualizar antes de publicar un producto puntual.
    """
    if not titulo or not titulo.strip():
        raise HTTPException(400, "Falta el título")
    token = get_config_value("ml_access_token", db)
    predicciones = await _ml_predecir_categoria(titulo.strip(), token=token, limit=3)
    if not predicciones:
        raise HTTPException(404, "ML no pudo predecir una categoría para ese título")
    return {"ok": True, "predicciones": predicciones}


@router.get("/api/ml/lineas-categoria")
async def listar_lineas_categoria(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Estado actual del cache de categorías por línea de producto."""
    cacheadas = {c.linea: c for c in db.query(MLCategoriaLinea).all()}
    salida = []
    for linea, titulo_ref in LINEAS_PRODUCTO.items():
        c = cacheadas.get(linea)
        salida.append({
            "linea": linea,
            "titulo_referencia": titulo_ref,
            "fija": titulo_ref is not None,
            "categoria_id": c.categoria_id if c else None,
            "categoria_nombre": c.categoria_nombre if c else None,
            "atributos_requeridos": len(json.loads(c.atributos_json)) if c else None,
            "actualizado": c.updated_at.isoformat() if c and c.updated_at else None,
        })
    return {"lineas": salida}


@router.post("/api/ml/resolver-categorias-lineas")
async def resolver_categorias_lineas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Corre el category_predictor de ML para cada línea de producto propia con
    título de referencia fijo, y cachea el resultado en BD. Ejecutar una vez
    al agregar una línea nueva, o cuando ML cambie su árbol de categorías.
    Las líneas sin título de referencia (heterogéneas) se saltean: esas se
    resuelven en vivo por producto en /api/ml/categoria-predictor.
    """
    token = get_config_value("ml_access_token", db)
    resultados = {"ok": [], "error": []}
    for linea, titulo_ref in LINEAS_PRODUCTO.items():
        if not titulo_ref:
            continue
        try:
            predicciones = await _ml_predecir_categoria(titulo_ref, token=token, limit=1)
            if not predicciones:
                resultados["error"].append({"linea": linea, "motivo": "sin predicción"})
                continue
            top = predicciones[0]
            existente = db.query(MLCategoriaLinea).filter(MLCategoriaLinea.linea == linea).first()
            if existente:
                existente.categoria_id = top["category_id"]
                existente.categoria_nombre = top["category_name"] or ""
                existente.atributos_json = json.dumps(top["attributes"], ensure_ascii=False)
                existente.titulo_referencia = titulo_ref
            else:
                db.add(MLCategoriaLinea(
                    linea=linea,
                    categoria_id=top["category_id"],
                    categoria_nombre=top["category_name"] or "",
                    atributos_json=json.dumps(top["attributes"], ensure_ascii=False),
                    titulo_referencia=titulo_ref,
                ))
            db.commit()
            resultados["ok"].append({
                "linea": linea,
                "categoria_id": top["category_id"],
                "categoria_nombre": top["category_name"],
            })
        except Exception as e:
            db.rollback()
            resultados["error"].append({"linea": linea, "motivo": str(e)[:150]})
        await asyncio.sleep(0.2)  # respetar rate limit de ML
    return resultados


async def _resolver_categoria_publicacion(db: Session, token: str, tipo: str, titulo: str) -> dict:
    """
    Resuelve category_id para publicar, en orden de prioridad:
    1. Cache en BD para la línea (MLCategoriaLinea) — el caso normal.
    2. Línea fija sin cachear todavía → predice con el título de referencia y cachea.
    3. Línea heterogénea (CAMPING_PESCA, IMPORTADO_VARIOS) o línea desconocida →
       predice en vivo con el título real del producto (no se cachea, cada
       producto de esa línea puede caer en una categoría distinta).
    4. Si todo lo anterior falla: dict fijo ML_CATEGORIAS como último recurso.
    """
    cache = db.query(MLCategoriaLinea).filter(MLCategoriaLinea.linea == tipo).first()
    if cache:
        return {"category_id": cache.categoria_id, "category_name": cache.categoria_nombre, "fuente": "cache"}

    titulo_ref = LINEAS_PRODUCTO.get(tipo)
    titulo_para_predecir = titulo_ref or titulo
    if titulo_para_predecir:
        try:
            predicciones = await _ml_predecir_categoria(titulo_para_predecir, token=token, limit=1)
            if predicciones:
                top = predicciones[0]
                if titulo_ref:  # línea fija: cachear para la próxima
                    db.add(MLCategoriaLinea(
                        linea=tipo,
                        categoria_id=top["category_id"],
                        categoria_nombre=top["category_name"] or "",
                        atributos_json=json.dumps(top["attributes"], ensure_ascii=False),
                        titulo_referencia=titulo_ref,
                    ))
                    db.commit()
                return {"category_id": top["category_id"], "category_name": top["category_name"], "fuente": "predictor"}
        except Exception:
            pass

    fallback = ML_CATEGORIAS.get(tipo, ML_CATEGORIAS["PISCINA"])
    return {"category_id": fallback, "category_name": None, "fuente": "fallback_fijo"}


async def _atributos_auto_litros(token: str, categoria_id: str, litros: float) -> list:
    """
    Busca entre los atributos de la categoría uno que sea de capacidad/volumen
    (ej. piscinas piden "Capacidad" o "Volumen" en litros) y lo autocompleta
    con el valor calculado a partir de las medidas del modelo, para no
    depender de que el usuario lo busque y lo cargue a mano cada vez.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{ML_BASE}/categories/{categoria_id}/attributes", headers=_ml_headers(token))
        if r.status_code != 200:
            return []
        import re as _re
        for a in r.json():
            nombre = (a.get("name") or "").lower()
            if _re.search(r"litro|capacidad|volumen", nombre):
                return [{"id": a.get("id"), "value_name": str(int(litros))}]
    except Exception:
        pass
    return []


# ─── API — CREAR PUBLICACIÓN ──────────────────────────────────────────────────

@router.post("/api/ml/publicaciones")
async def crear_publicacion(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    token = await _get_token(db)
    data = await request.json()

    tipo = data.get("tipo", "PISCINA")
    categoria_ml_id_explicito = data.get("categoria_ml_id")
    if categoria_ml_id_explicito:
        categoria_resuelta = {"category_id": categoria_ml_id_explicito, "category_name": None, "fuente": "manual"}
    else:
        categoria_resuelta = await _resolver_categoria_publicacion(db, token, tipo, data.get("titulo", ""))

    atributos = [{"id": "BRAND", "value_name": "EcoFiver"}]
    litros = data.get("litros_estimados")
    if litros:
        atributos += await _atributos_auto_litros(token, categoria_resuelta["category_id"], litros)

    payload = {
        "title": data.get("titulo", ""),
        "category_id": categoria_resuelta["category_id"],
        "price": float(data.get("precio", 0)),
        "currency_id": "ARS",
        "available_quantity": int(data.get("stock", 1)),
        "buying_mode": "buy_it_now",
        "item_condition": "new",
        "listing_type_id": "gold_special",
        "description": {
            "plain_text": _agregar_condiciones(db, data.get("descripcion", "")),
        },
        "pictures": [
            {"source": url}
            for url in data.get("fotos_urls", [])
            if url
        ],
        "attributes": atributos,
        # Forzar "acuerdo con el vendedor" — previene asignación automática de
        # MercadoEnvíos por dimensiones. Todos los productos EcoFiver son de gran
        # porte o requieren coordinación directa; ME2 no aplica.
        "shipping": {"mode": "not_specified", "free_shipping": False},
    }

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{ML_BASE}/items",
            headers=_ml_headers(token),
            json=payload,
        )

    if r.status_code not in (200, 201):
        raise HTTPException(r.status_code, f"Error ML al publicar: {r.text[:300]}")

    item = r.json()
    item_id = item.get("id")

    # Guardar en cache local
    db.add(PublicacionML(
        item_id=item_id,
        titulo=data.get("titulo", ""),
        descripcion=data.get("descripcion", ""),
        precio=float(data.get("precio", 0)),
        estado_ml="active",
        producto=tipo,
        modelo_especifico=data.get("modelo", ""),
    ))
    db.commit()

    return {
        "ok": True,
        "item_id": item_id,
        "permalink": item.get("permalink"),
        "categoria_id": categoria_resuelta["category_id"],
        "categoria_nombre": categoria_resuelta["category_name"],
        "categoria_fuente": categoria_resuelta["fuente"],
        "msg": f"Publicación creada: {item_id}",
    }


# ─── API — SINCRONIZAR PRECIOS ────────────────────────────────────────────────

@router.post("/api/ml/sincronizar-precios")
async def sincronizar_precios(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Actualiza el precio en ML de todas las publicaciones en cache."""
    token = await _get_token(db)

    publicaciones = db.query(PublicacionML).filter(
        PublicacionML.estado_ml == "active",
        PublicacionML.precio > 0,
    ).all()

    resultados = {"ok": 0, "error": 0, "detalles": []}

    async with httpx.AsyncClient(timeout=15) as c:
        for pub in publicaciones:
            try:
                r = await c.put(
                    f"{ML_BASE}/items/{pub.item_id}",
                    headers=_ml_headers(token),
                    json={"price": pub.precio},
                )
                if r.status_code in (200, 204):
                    resultados["ok"] += 1
                    resultados["detalles"].append({"item_id": pub.item_id, "status": "ok"})
                else:
                    resultados["error"] += 1
                    resultados["detalles"].append({"item_id": pub.item_id, "status": f"error {r.status_code}"})
            except Exception as e:
                resultados["error"] += 1
                resultados["detalles"].append({"item_id": pub.item_id, "status": str(e)[:50]})

            await asyncio.sleep(0.3)  # Respetar rate limit de ML

    return resultados


# ─── API — CONFIG DESCRIPCIÓN (encabezado / pie / keywords) ──────────────────

@router.get("/api/ml/config/descripcion")
async def get_config_descripcion(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    return {
        "encabezado":            get_config_value("ml_desc_encabezado", db) or "",
        "pie":                   get_config_value("ml_desc_pie", db) or "",
        "encabezado_referencia": get_config_value("ml_desc_encabezado_referencia", db) or "",
        "pie_referencia":        get_config_value("ml_desc_pie_referencia", db) or "",
        "keywords":              get_config_value("ml_desc_keywords", db) or "",
    }


@router.put("/api/ml/config/descripcion")
async def put_config_descripcion(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    data = await request.json()
    campos = [
        ("encabezado",            "ml_desc_encabezado"),
        ("pie",                   "ml_desc_pie"),
        ("encabezado_referencia", "ml_desc_encabezado_referencia"),
        ("pie_referencia",        "ml_desc_pie_referencia"),
        ("keywords",              "ml_desc_keywords"),
    ]
    for campo, clave in campos:
        if campo in data:
            _ml_save(db, clave, data[campo], secreto=False)
    return {"ok": True}


@router.get("/api/ml/fichas")
async def listar_fichas_ml(
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Lista todos los modelos disponibles con ficha pre-escrita."""
    try:
        from utils.ml_fichas_content import FICHAS_PISCINAS, FICHAS_MODULOS
    except ImportError:
        return {"piscinas": [], "modulos": []}

    return {
        "piscinas": list(FICHAS_PISCINAS.keys()),
        "modulos": [f"{k}m2" for k in FICHAS_MODULOS.keys()],
    }


@router.get("/api/ml/ficha/{modelo:path}")
async def get_ficha_ml(
    modelo: str,
    db: Session = Depends(get_db),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Devuelve la ficha pre-escrita (título + descripción) para el modelo dado."""
    try:
        from utils.ml_fichas_content import FICHAS_PISCINAS, FICHAS_MODULOS
    except ImportError:
        raise HTTPException(500, "No se pudo cargar el archivo de fichas de producto")

    # Buscar en piscinas (coincidencia exacta o insensible a acentos/case)
    ficha = FICHAS_PISCINAS.get(modelo)
    if not ficha:
        modelo_norm = modelo.lower().strip()
        for k, v in FICHAS_PISCINAS.items():
            if k.lower().strip() == modelo_norm:
                ficha = v
                break

    # Buscar en módulos (buscar por m2 numérico)
    if not ficha:
        m2_str = modelo.replace("m2", "").replace("m²", "").strip()
        ficha = FICHAS_MODULOS.get(m2_str)

    if not ficha:
        raise HTTPException(404, f"No se encontró ficha para el modelo: {modelo}")

    return {
        "modelo": modelo,
        "titulo_ml": ficha.get("titulo_ml", ""),
        "descripcion_ml": ficha.get("descripcion_ml", ""),
        "atributos_ml": ficha.get("atributos_ml", {}),
    }


# ─── API — ACTUALIZAR DESCRIPCIONES EN LOTE ──────────────────────────────────

async def _actualizar_desc_lote_bg(job_id: str, token: str, pub_data: list, desc_config: dict):
    """
    Worker de fondo: actualiza descripción en ML para cada publicación.
    pub_data: lista de dicts {item_id, descripcion, tipo_precio}
    desc_config: {encabezado, pie, encabezado_ref, pie_ref, keywords, condiciones}
    """
    job = _DESC_JOBS[job_id]
    job["total"] = len(pub_data)
    job["procesados"] = 0
    job["ok"] = 0
    job["error"] = 0
    job["errores_detalle"] = []   # solo errores (no los OK) para mantener el tamaño pequeño

    try:
        for pub in pub_data:
            job["actual"] = pub.get("item_id", "")
            try:
                # Construir descripción completa con encabezado/pie según tipo de precio
                tipo = pub.get("tipo_precio", "completo")
                enc = desc_config["encabezado_ref"] if tipo == "referencia" else desc_config["encabezado"]
                pie = desc_config["pie_ref"] if tipo == "referencia" else desc_config["pie"]
                kw  = desc_config.get("keywords", "")
                cnd = desc_config.get("condiciones", "")

                bloques = []
                if enc: bloques.append(enc.strip())
                body = (pub.get("descripcion") or "").strip()
                if body: bloques.append(body)
                if kw:  bloques.append(kw.strip())
                if cnd: bloques.append(cnd.strip())
                if pie: bloques.append(pie.strip())
                texto = "\n\n".join(b for b in bloques if b)

                async with httpx.AsyncClient(timeout=12) as c:
                    r = await c.put(
                        f"{ML_BASE}/items/{pub['item_id']}/description",
                        headers=_ml_headers(token),
                        json={"plain_text": texto},
                    )
                if r.status_code in (200, 201):
                    job["ok"] += 1
                else:
                    job["error"] += 1
                    if len(job["errores_detalle"]) < 20:
                        job["errores_detalle"].append({"item_id": pub["item_id"], "status": f"HTTP {r.status_code}: {r.text[:80]}"})
            except Exception as e:
                job["error"] += 1
                if len(job["errores_detalle"]) < 20:
                    job["errores_detalle"].append({"item_id": pub.get("item_id","?"), "status": str(e)[:80]})

            job["procesados"] += 1
            await asyncio.sleep(0.4)
    except Exception as e_outer:
        log.error(f"[DESC_BG] Job {job_id} error inesperado: {e_outer}")
        job["errores_detalle"].append({"item_id": "global", "status": str(e_outer)[:120]})
    finally:
        job["status"] = "done"   # siempre marcar done, incluso si hubo excepción


@router.post("/api/ml/publicaciones/actualizar-descripcion-lote")
async def actualizar_descripcion_lote(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Aplica el encabezado/pie/keywords configurados a todas las publicaciones
    activas. Devuelve job_id inmediatamente y procesa en segundo plano.
    """
    from routers.configuracion import get_config_value
    token = await _get_token(db)

    # Actualizamos TODAS las publicaciones con item_id (activas, pausadas o cerradas).
    # ML acepta PUT description en cualquier estado. Los errores se capturan por item.
    pubs = db.query(PublicacionML).filter(
        PublicacionML.item_id.isnot(None),
    ).all()

    if not pubs:
        return {"ok": 0, "error": 0, "total": 0, "detalles": [], "job_id": None, "status": "done"}

    # Snapshot de datos (la sesión DB no se puede usar fuera del request)
    pub_data = [
        {
            "item_id": p.item_id,
            "descripcion": p.descripcion or "",
            "tipo_precio": p.tipo_precio if hasattr(p, "tipo_precio") else "completo",
        }
        for p in pubs
    ]

    # Snapshot de la configuración actual de descripción
    desc_config = {
        "encabezado":     get_config_value("ml_encabezado", db) or "",
        "pie":            get_config_value("ml_pie", db) or "",
        "encabezado_ref": get_config_value("ml_encabezado_ref", db) or "",
        "pie_ref":        get_config_value("ml_pie_ref", db) or "",
        "keywords":       get_config_value("ml_keywords", db) or "",
        "condiciones":    get_config_value("condiciones_generales", db) or "",
    }

    job_id = str(uuid.uuid4())
    _DESC_JOBS[job_id] = {
        "status": "running", "total": len(pub_data), "procesados": 0,
        "ok": 0, "error": 0, "detalles": [], "actual": "",
    }

    background_tasks.add_task(_actualizar_desc_lote_bg, job_id, token, pub_data, desc_config)
    return {"job_id": job_id, "total": len(pub_data), "status": "running"}


@router.get("/api/ml/publicaciones/actualizar-descripcion-lote/estado/{job_id}")
async def estado_actualizar_desc(job_id: str):
    """Consulta el progreso de un job de actualización de descripciones."""
    job = _DESC_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return {
        "status":    job.get("status", "running"),
        "total":     job.get("total", 0),
        "procesados": job.get("procesados", 0),
        "ok":        job.get("ok", 0),
        "error":     job.get("error", 0),
        "actual":    job.get("actual", ""),
        "errores_detalle": job.get("errores_detalle", []),
    }


# ─── API — AGREGAR TEXTO POR TIPO ───────────────────────────────────────────

async def _aplicar_texto_tipo_bg(job_id: str, token: str, pub_data: list, texto: str, posicion: str):
    """Agrega texto al inicio o fin de la descripción ML para publicaciones de tipos seleccionados."""
    job = _DESC_JOBS[job_id]
    try:
        for pub in pub_data:
            job["actual"] = pub.get("item_id", "")
            try:
                desc = (pub.get("descripcion") or "").strip()
                nueva = f"{texto}\n\n{desc}" if posicion == "inicio" else f"{desc}\n\n{texto}" if desc else texto
                async with httpx.AsyncClient(timeout=12) as c:
                    r = await c.put(
                        f"{ML_BASE}/items/{pub['item_id']}/description",
                        headers=_ml_headers(token),
                        json={"plain_text": nueva},
                    )
                if r.status_code in (200, 201):
                    job["ok"] += 1
                else:
                    job["error"] += 1
                    if len(job["errores_detalle"]) < 20:
                        job["errores_detalle"].append({"item_id": pub["item_id"], "status": f"HTTP {r.status_code}: {r.text[:80]}"})
            except Exception as e:
                job["error"] += 1
                if len(job["errores_detalle"]) < 20:
                    job["errores_detalle"].append({"item_id": pub.get("item_id", "?"), "status": str(e)[:80]})
            job["procesados"] += 1
            await asyncio.sleep(0.4)
    except Exception as e_outer:
        job["errores_detalle"].append({"item_id": "global", "status": str(e_outer)[:120]})
    finally:
        job["status"] = "done"


@router.post("/api/ml/catalogo/hidromasajes/seed")
async def seed_borradores_hidromasajes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Crea los borradores ML pre-configurados de la línea completa EcoFiver:
    - 4 hidromasajes / spas (Quadra / Recta / Orbis / Delta) con fotos reales
    - 5 accesorios opcionales para hidromasajes
    - 7 bañeras de acrílico (Lumina / Sensa / Vento / Aqua / Curve / Pure / Vita) con fotos
    - 3 receptáculos de ducha (Clásico / Esquinero / Pequeño) con fotos
    Usa seller_sku como clave de unicidad — no duplica si ya existen.
    """
    import json as _json

    # ── URLs de fotos reales extraídas de ecofiver.site ───────────────────────
    FOTOS_HIDRO = {
        "Spa Quadra": ["https://ecofiver.site/wp-content/uploads/2025/12/1.69x1.17x0.40-HIDRO.jpeg"],
        "Spa Recta":  ["https://ecofiver.site/wp-content/uploads/2025/12/1.65x1.40x0.45-HIDRO.jpeg"],
        "Spa Orbis":  ["https://ecofiver.site/wp-content/uploads/2025/12/1.76x1.76x0.40-HIDRO.jpeg"],
        "Spa Delta":  ["https://ecofiver.site/wp-content/uploads/2025/12/1.97x1.42x0.52-HIDRO.jpeg"],
    }
    FOTOS_BANERA = {
        "Lumina": ["https://ecofiver.site/wp-content/uploads/2025/12/lumina.jpg"],
        "Sensa":  ["https://ecofiver.site/wp-content/uploads/2025/12/sensa.jpg"],
        "Vento":  ["https://ecofiver.site/wp-content/uploads/2025/12/vento.jpg"],
        "Aqua":   ["https://ecofiver.site/wp-content/uploads/2025/12/aquaaa.jpg"],
        "Curve":  ["https://ecofiver.site/wp-content/uploads/2025/12/curve.jpg"],
        "Pure":   ["https://ecofiver.site/wp-content/uploads/2025/12/pure.jpg"],
        "Vita":   ["https://ecofiver.site/wp-content/uploads/2025/12/vita.jpg"],
    }
    FOTOS_RECEP = {
        "Clásico":   ["https://ecofiver.site/wp-content/uploads/2025/12/1.10x1.10x0.10-RECEP.jpeg"],
        "Esquinero": ["https://ecofiver.site/wp-content/uploads/2025/12/99X75-RECEP.jpeg"],
        "Pequeño":   ["https://ecofiver.site/wp-content/uploads/2025/12/90x90x0.90-RECEP.jpeg"],
    }

    # ── Texto base hidromasajes ───────────────────────────────────────────────
    DESC_BASE_HIDRO = (
        "\n\nEquipamiento incluido: jets dirigibles vista cromo, motor según modelo, "
        "pulsador neumático de encendido, reguladores de flujo de aire, "
        "sistema de succión con filtro de pelos, sopapa y desborde conectados. "
        "Estructura autoportante metálica reforzada incluida, sin obra de albañilería."
        "\n\nColores disponibles sin cargo adicional: Blanco, Beige, Negro y Gris. "
        "Indicar el color al comprar o por mensaje antes de la preparación."
        "\n\nOpcionales con cargo (consultar): blower de aire 12 inyectores, cromoterapia LED, "
        "grifería con pico cisne o cascada (cromo/negro mate), ozonizador con sensor de nivel, "
        "revestimiento exterior WPC símil madera."
        "\n\nPago: contado, tarjeta de crédito o débito. Sin financiación en cuotas."
        "\n\nRetiro: San Telmo (CABA) o Zárate (Bs. As.). Envío a domicilio cotizar."
        "\n\nFabricación propia EcoFiver — Zárate, Buenos Aires. Garantía estructural incluida."
    )

    # ── Texto base bañeras ────────────────────────────────────────────────────
    DESC_BASE_BANERA = (
        "\n\nFabricada en acrílico sanitario de alta resistencia reforzado con fibra de vidrio (PRFV). "
        "Superficie suave, fácil limpieza, resistente a productos de limpieza y rayos UV."
        "\n\nColores disponibles: Blanco, Beige, Negro, Gris."
        "\n\nInstalación directa sobre el piso. Conexión a agua fría/caliente y desagüe. "
        "Sin obra de albañilería."
        "\n\nPago: contado, tarjeta de crédito o débito. Sin financiación en cuotas."
        "\n\nRetiro: San Telmo (CABA) o Zárate (Bs. As.). Envío a domicilio cotizar."
        "\n\nFabricación propia EcoFiver — Zárate, Buenos Aires. Garantía incluida."
    )

    # ── Texto base receptáculos ───────────────────────────────────────────────
    DESC_BASE_RECEP = (
        "\n\nFabricado en acrílico sanitario de alta resistencia reforzado con fibra de vidrio (PRFV). "
        "Antideslizante, resistente a químicos de limpieza. Instalación directa sobre el piso."
        "\n\nColores disponibles: Blanco, Beige, Negro, Gris."
        "\n\nPago: contado, tarjeta de crédito o débito. Sin financiación en cuotas."
        "\n\nRetiro: San Telmo (CABA) o Zárate (Bs. As.)."
        "\n\nFabricación propia EcoFiver — Zárate, Buenos Aires. Garantía incluida."
    )

    # ── Datos de hidromasajes ─────────────────────────────────────────────────
    modelos_data = [
        {
            "sku": "ECOF-HIDRO-QUADRA", "modelo": "Spa Quadra", "precio": 1220000,
            "titulo": "Hidromasaje Esquinero Spa Quadra 110x110 Acrílico EcoFiver",
            "descripcion": (
                "Hidromasaje esquinero modelo Spa Quadra de EcoFiver. "
                "Fabricado en acrílico sanitario reforzado con fibra de vidrio. "
                "Diseño esquinero compacto de 1,10 m × 1,10 m, ideal para baños y espacios reducidos. "
                "Profundidad 0,10 m. Conexión directa a agua fría/caliente, desagüe y electricidad."
                "\n\nEspecificaciones: 1,10 × 1,10 × 0,10 m · 4 jets dirigibles · "
                "Motor 1/2 HP o 3/4 HP · 1 pulsador neumático · 1 regulador de aire."
                + DESC_BASE_HIDRO
            ),
        },
        {
            "sku": "ECOF-HIDRO-RECTA", "modelo": "Spa Recta", "precio": 1520000,
            "titulo": "Hidromasaje Rectangular Spa Recta 165x140 Acrílico EcoFiver",
            "descripcion": (
                "Hidromasaje rectangular modelo Spa Recta de EcoFiver. "
                "Acrílico sanitario reforzado con fibra de vidrio. "
                "Formato rectangular doble de 1,65 m × 1,40 m con 0,45 m de profundidad, "
                "ideal para baños amplios, suites o instalación sobre deck exterior."
                "\n\nEspecificaciones: 1,65 × 1,40 × 0,45 m · 6 jets dirigibles · "
                "Motor 3/4 HP · 1 pulsador neumático · 2 reguladores de aire."
                + DESC_BASE_HIDRO
            ),
        },
        {
            "sku": "ECOF-HIDRO-ORBIS", "modelo": "Spa Orbis", "precio": 1620000,
            "titulo": "Hidromasaje Circular Spa Orbis 176x176 Acrílico EcoFiver",
            "descripcion": (
                "Hidromasaje circular panorámico modelo Spa Orbis de EcoFiver. "
                "Acrílico sanitario reforzado con fibra de vidrio. "
                "Diseño circular de 1,76 m × 1,76 m con 0,40 m de profundidad, "
                "ideal para baños de lujo, terrazas o ambientes spa."
                "\n\nEspecificaciones: 1,76 × 1,76 × 0,40 m · 6 a 8 jets dirigibles · "
                "Motor 3/4 HP · 1 pulsador neumático · 2 reguladores de aire."
                + DESC_BASE_HIDRO
            ),
        },
        {
            "sku": "ECOF-HIDRO-DELTA", "modelo": "Spa Delta", "precio": 1890000,
            "titulo": "Mini Spa Hidromasaje Spa Delta 197x142 Acrílico EcoFiver",
            "descripcion": (
                "Mini spa modelo Spa Delta de EcoFiver. El hidromasaje de mayor capacidad de la línea. "
                "Acrílico sanitario reforzado con fibra de vidrio. "
                "Formato rectangular XL de 1,97 m × 1,42 m con 0,52 m de profundidad."
                "\n\nEspecificaciones: 1,97 × 1,42 × 0,52 m · 8 jets dirigibles · "
                "Motor 1 HP · 1 pulsador neumático · 2 reguladores de aire."
                + DESC_BASE_HIDRO
            ),
        },
    ]

    accesorios_data = [
        {
            "sku": "ECOF-HIDRO-ACC-BLOWER", "modelo": "Kit Blower de Aire", "precio": 0,
            "titulo": "Kit Blower Burbujas para Hidromasaje 12 Inyectores EcoFiver",
            "descripcion": (
                "Kit blower de aire para hidromasajes y spas EcoFiver. "
                "Motor blower independiente + 12 inyectores en piso para efecto burbujas. "
                "Compatible con Spa Quadra, Recta, Orbis y Delta. Consultar precio."
                "\n\nFabricación EcoFiver · Retiro: San Telmo (CABA) o Zárate (Bs. As.)."
            ),
        },
        {
            "sku": "ECOF-HIDRO-ACC-LED", "modelo": "Kit Cromoterapia LED", "precio": 0,
            "titulo": "Kit Cromoterapia LED Sumergible Hidromasaje Spa EcoFiver",
            "descripcion": (
                "Kit de cromoterapia LED para hidromasajes y spas EcoFiver. "
                "Spot LED multicolor sumergible, secuencias programables. "
                "Compatible con todos los modelos Spa EcoFiver. Consultar precio."
                "\n\nFabricación EcoFiver · Retiro: San Telmo (CABA) o Zárate (Bs. As.)."
            ),
        },
        {
            "sku": "ECOF-HIDRO-ACC-GRIF", "modelo": "Kit Grifería y Cascada", "precio": 0,
            "titulo": "Kit Grifería Cascada Hidromasaje Spa Cromo Negro Mate EcoFiver",
            "descripcion": (
                "Kit de grifería y cascada para hidromasajes EcoFiver. "
                "Pico cisne o cascada ovalada en cromo o negro mate. "
                "Compatible con todos los modelos Spa EcoFiver. Consultar precio."
                "\n\nFabricación EcoFiver · Retiro: San Telmo (CABA) o Zárate (Bs. As.)."
            ),
        },
        {
            "sku": "ECOF-HIDRO-ACC-OZON", "modelo": "Sistema de Desinfección", "precio": 0,
            "titulo": "Kit Desinfección Ozonizador Sensor Nivel Hidromasaje EcoFiver",
            "descripcion": (
                "Sistema de desinfección para hidromasajes EcoFiver. "
                "Ozonizador + sensor electrónico de nivel. "
                "Protege el motor y mantiene el agua en óptimas condiciones. "
                "Compatible con todos los modelos. Consultar precio."
                "\n\nFabricación EcoFiver · Retiro: San Telmo (CABA) o Zárate (Bs. As.)."
            ),
        },
        {
            "sku": "ECOF-HIDRO-ACC-WPC", "modelo": "Revestimiento Exterior WPC", "precio": 0,
            "titulo": "Revestimiento WPC Símil Madera Faldón Hidromasaje Spa EcoFiver",
            "descripcion": (
                "Revestimiento exterior WPC símil madera para hidromasajes EcoFiver. "
                "Faldones de WPC (madera+polímero) resistentes a humedad y UV. "
                "Ideal para instalaciones en deck exterior o jardín. A medida. Consultar precio."
                "\n\nFabricación EcoFiver · Retiro: San Telmo (CABA) o Zárate (Bs. As.)."
            ),
        },
    ]

    # ── Datos de bañeras ──────────────────────────────────────────────────────
    baneras_data = [
        {
            "sku": "ECOF-BAN-LUMINA", "modelo": "Lumina", "precio": 0,
            "titulo": "Bañera Acrílica Lumina 190x90 EcoFiver Fabricación Propia",
            "descripcion": (
                "Bañera modelo Lumina de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato rectangular, ideal para baños estándar. 1,90 m × 0,90 m × 0,50 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-SENSA", "modelo": "Sensa", "precio": 0,
            "titulo": "Bañera Acrílica Sensa 170x118 Angular EcoFiver Fabricación Propia",
            "descripcion": (
                "Bañera modelo Sensa de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato angular doble asiento. 1,18 m × 1,70 m × 0,45 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-VENTO", "modelo": "Vento", "precio": 0,
            "titulo": "Bañera Acrílica Vento 140x77 Compacta EcoFiver Fabricación Propia",
            "descripcion": (
                "Bañera modelo Vento de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato compacto rectangular. 1,40 m × 0,77 m × 0,49 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-AQUA", "modelo": "Aqua", "precio": 0,
            "titulo": "Bañera Acrílica Aqua 165x140 Doble Asiento EcoFiver",
            "descripcion": (
                "Bañera modelo Aqua de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato doble asiento XL. 1,40 m × 1,65 m × 0,50 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-CURVE", "modelo": "Curve", "precio": 0,
            "titulo": "Bañera Acrílica Curve 140x140 Esquinera EcoFiver",
            "descripcion": (
                "Bañera esquinera modelo Curve de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato esquinero cuadrado. 1,40 m × 1,40 m × 0,55 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-PURE", "modelo": "Pure", "precio": 0,
            "titulo": "Bañera Acrílica Pure 184x96 Clásica EcoFiver Fabricación Propia",
            "descripcion": (
                "Bañera modelo Pure de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato rectangular clásico. 1,84 m × 0,96 m × 0,45 m."
                + DESC_BASE_BANERA
            ),
        },
        {
            "sku": "ECOF-BAN-VITA", "modelo": "Vita", "precio": 0,
            "titulo": "Bañera Acrílica Vita 180x90 Estándar EcoFiver Fabricación Propia",
            "descripcion": (
                "Bañera modelo Vita de EcoFiver. Acrílico sanitario reforzado con PRFV. "
                "Formato rectangular estándar. 1,80 m × 0,90 m × 0,50 m."
                + DESC_BASE_BANERA
            ),
        },
    ]

    # ── Datos de receptáculos ─────────────────────────────────────────────────
    receptaculos_data = [
        {
            "sku": "ECOF-RECEP-CLASICO", "modelo": "Receptáculo Clásico", "precio": 0,
            "titulo": "Receptáculo Ducha Clásico 110x110 Acrílico EcoFiver",
            "descripcion": (
                "Receptáculo de ducha modelo Clásico de EcoFiver. "
                "Acrílico sanitario reforzado con PRFV. Cuadrado de 1,10 m × 1,10 m × 0,10 m. "
                "Antideslizante. Conexión a desagüe estándar."
                + DESC_BASE_RECEP
            ),
        },
        {
            "sku": "ECOF-RECEP-ESQUINERO", "modelo": "Receptáculo Esquinero", "precio": 0,
            "titulo": "Receptáculo Ducha Esquinero 99x75 Acrílico EcoFiver",
            "descripcion": (
                "Receptáculo de ducha esquinero modelo Esquinero de EcoFiver. "
                "Acrílico sanitario reforzado con PRFV. 99 cm × 75 cm × 10 cm. "
                "Diseño aprovecha el rincón. Antideslizante."
                + DESC_BASE_RECEP
            ),
        },
        {
            "sku": "ECOF-RECEP-PEQUENO", "modelo": "Receptáculo Pequeño", "precio": 0,
            "titulo": "Receptáculo Ducha Pequeño 90x90 Acrílico EcoFiver",
            "descripcion": (
                "Receptáculo de ducha modelo Pequeño de EcoFiver. "
                "Acrílico sanitario reforzado con PRFV. 90 cm × 90 cm × 9 cm. "
                "Formato compacto, ideal para baños de servicio o espacios reducidos. Antideslizante."
                + DESC_BASE_RECEP
            ),
        },
    ]

    creados = []
    omitidos = []

    def _crear_borrador(item: dict, producto: str, fotos_map: dict | None = None) -> None:
        sku = item["sku"]
        existe = db.query(BorradorML).filter(BorradorML.seller_sku == sku).first()
        if existe:
            # Actualizar fotos si el borrador existe pero no tiene fotos cargadas
            if fotos_map and existe.fotos_json in (None, "[]", ""):
                fotos_urls = fotos_map.get(item["modelo"], [])
                if fotos_urls:
                    existe.fotos_json = _json.dumps(fotos_urls)
                    omitidos.append({"sku": sku, "razon": "ya existe (fotos actualizadas)", "id": existe.id})
                    return
            omitidos.append({"sku": sku, "razon": "ya existe", "id": existe.id})
            return
        fotos_urls = (fotos_map or {}).get(item["modelo"], [])
        b = BorradorML(
            origen            = "catalogo",
            titulo            = item["titulo"][:200],
            descripcion       = item["descripcion"],
            producto          = producto,
            precio            = item["precio"],
            seller_sku        = sku,
            modelo_nombre     = item["modelo"],
            condicion         = "new",
            listing_type      = "gold_special",
            cuotas_sin_interes= 0,
            fotos_json        = _json.dumps(fotos_urls),
            estado            = "borrador",
            created_by_id     = current_user.id,
        )
        db.add(b)
        db.flush()
        creados.append({"sku": sku, "titulo": item["titulo"], "id": b.id, "fotos": len(fotos_urls)})

    for m in modelos_data:
        _crear_borrador(m, "HIDROMASAJE", FOTOS_HIDRO)
    for a in accesorios_data:
        _crear_borrador(a, "ACCESORIO_HIDROMASAJE", None)
    for b in baneras_data:
        _crear_borrador(b, "BANERA", FOTOS_BANERA)
    for r in receptaculos_data:
        _crear_borrador(r, "RECEPTACULO", FOTOS_RECEP)

    db.commit()
    return {
        "ok": True,
        "creados": len(creados),
        "omitidos": len(omitidos),
        "detalle_creados": creados,
        "detalle_omitidos": omitidos,
    }


@router.get("/api/ml/publicaciones/con-item-id")
async def listar_pubs_con_item_id(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lista todas las publicaciones con item_id para el selector de texto-por-tipo."""
    pubs = db.query(PublicacionML).filter(
        PublicacionML.item_id.isnot(None),
    ).order_by(PublicacionML.titulo).all()
    return [
        {
            "item_id":   p.item_id,
            "titulo":    p.titulo or p.item_id,
            "producto":  p.producto or "",
            "estado_ml": p.estado_ml or "",
        }
        for p in pubs
    ]


@router.post("/api/ml/publicaciones/aplicar-texto-tipo")
async def aplicar_texto_tipo(
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Agrega un bloque de texto al inicio o fin de la descripción ML
    de todas las publicaciones con item_id de los tipos seleccionados.
    """
    data     = await request.json()
    texto    = (data.get("texto") or "").strip()
    posicion = data.get("posicion", "fin")        # "inicio" | "fin"
    item_ids = [i for i in (data.get("item_ids") or []) if i]   # lista directa de item_ids

    if not texto:
        raise HTTPException(400, "Falta el texto a agregar")
    if not item_ids:
        raise HTTPException(400, "No se recibieron publicaciones seleccionadas")

    token = await _get_token(db)

    pubs = db.query(PublicacionML).filter(
        PublicacionML.item_id.in_(item_ids),
    ).all()

    if not pubs:
        return {"ok": 0, "total": 0, "job_id": None, "status": "done",
                "msg": "No se encontraron las publicaciones seleccionadas en la base de datos"}

    pub_data = [{"item_id": p.item_id, "descripcion": p.descripcion or ""} for p in pubs]

    job_id = str(uuid.uuid4())
    _DESC_JOBS[job_id] = {
        "status": "running", "total": len(pub_data), "procesados": 0,
        "ok": 0, "error": 0, "errores_detalle": [], "actual": "",
    }
    background_tasks.add_task(_aplicar_texto_tipo_bg, job_id, token, pub_data, texto, posicion)
    return {"job_id": job_id, "total": len(pub_data), "status": "running"}


# ─── API — PREGUNTAS ──────────────────────────────────────────────────────────

@router.get("/api/ml/preguntas")
async def get_preguntas(
    estado: Optional[str] = "UNANSWERED",   # UNANSWERED | ANSWERED | BANNED | DELETED | CLOSED_UNANSWERED
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Trae preguntas de ML filtradas por estado."""
    token = await _get_token(db)
    user_id = await _get_user_id(token, db)

    params = {
        "seller_id": user_id,
        "status": estado,
        "limit": 50,
        "sort_fields": "date_created",
        "sort_types": "DESC",
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ML_BASE}/questions/search", headers=_ml_headers(token), params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Error ML preguntas: {r.text[:200]}")

    data = r.json()
    preguntas = data.get("questions", [])

    # Enriquecer con título del item
    item_ids = list({p.get("item_id") for p in preguntas if p.get("item_id")})
    titulos = {}
    if item_ids:
        try:
            batch = ",".join(item_ids[:20])
            async with httpx.AsyncClient(timeout=10) as c:
                r2 = await c.get(f"{ML_BASE}/items", headers=_ml_headers(token), params={"ids": batch})
            if r2.status_code == 200:
                for entry in r2.json():
                    body = entry.get("body", {})
                    if body:
                        titulos[body.get("id")] = body.get("title", "")
        except Exception:
            pass

    result = []
    for p in preguntas:
        item_id = p.get("item_id", "")
        result.append({
            "id": p.get("id"),
            "item_id": item_id,
            "item_titulo": titulos.get(item_id, item_id),
            "texto": p.get("text", ""),
            "fecha": p.get("date_created", ""),
            "estado": p.get("status", ""),
            "respuesta": p.get("answer", {}).get("text", "") if p.get("answer") else "",
        })

    return {"total": data.get("total", 0), "preguntas": result}


@router.post("/api/ml/preguntas/{qid}/responder")
async def responder_pregunta(
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Responde una pregunta de ML.
    - sugerir_solo=true → genera texto con IA y lo devuelve sin publicar (no necesita token ML)
    - respuesta_manual  → publica ese texto directamente sin llamar IA
    - (vacío)           → genera con IA y publica
    """
    data  = await request.json()

    sugerir_solo     = data.get("sugerir_solo", False)
    pregunta_texto   = data.get("pregunta_texto", data.get("texto_pregunta", "")).strip()
    item_titulo      = data.get("item_titulo", "").strip()
    item_id_data     = data.get("item_id", "").strip()
    comprador_nick   = data.get("comprador_nick", data.get("from_nickname", "")).strip()
    respuesta_manual = data.get("respuesta_manual", data.get("respuesta", ""))

    # ── Buscar descripción local para enriquecer el contexto ────────────────
    descripcion_pub = ""
    pub_local = None
    if item_id_data:
        pub_local = db.query(PublicacionML).filter(PublicacionML.item_id == item_id_data).first()
        if pub_local:
            descripcion_pub = pub_local.descripcion or ""
            if not item_titulo and pub_local.titulo:
                item_titulo = pub_local.titulo

    es_generada_por_ia = False

    # ── Generar respuesta con IA si no se proveyó una manual ────────────────
    if not respuesta_manual:
        if not pregunta_texto:
            raise HTTPException(400, "No se recibió el texto de la pregunta del comprador.")

        prompt = ctx_preguntas_ml(
            item_titulo=item_titulo or "producto EcoFiver",
            pregunta=pregunta_texto,
            descripcion_pub=descripcion_pub,
            comprador=comprador_nick,
        )
        try:
            respuesta_manual = await ai_complete(db, prompt, max_tokens=400, temperature=0.6)
            respuesta_manual = " ".join(respuesta_manual.split())
            es_generada_por_ia = True
        except Exception as e:
            raise HTTPException(502, f"Error generando respuesta con IA: {e}. Configurá un proveedor en Configuración → API Keys.")

    # ── Solo sugerir: devolver sin publicar ─────────────────────────────────
    if sugerir_solo:
        return {"ok": True, "respuesta_sugerida": respuesta_manual}

    # ── Publicar en ML (solo aquí necesitamos el token) ─────────────────────
    token = await _get_token(db)
    body = {"question_id": qid, "text": respuesta_manual[:2000]}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{ML_BASE}/answers", headers=_ml_headers(token), json=body)

    if r.status_code not in (200, 201):
        raise HTTPException(r.status_code, f"Error ML al responder: {r.text[:200]}")

    # ── Guardar registro histórico ───────────────────────────────────────────
    try:
        registro = RespuestaAutoML(
            question_id     = str(qid),
            item_id         = item_id_data or (pub_local.item_id if pub_local else None),
            item_titulo     = item_titulo[:499] if item_titulo else None,
            comprador_nick  = comprador_nick[:199] if comprador_nick else None,
            pregunta_texto  = pregunta_texto,
            respuesta_texto = respuesta_manual,
            respondida_por  = "auto-manual" if es_generada_por_ia else "manual",
        )
        db.add(registro)
        db.commit()
    except Exception as e_db:
        db.rollback()  # no es fatal — la respuesta ya se envió a ML

    return {"ok": True, "respuesta": respuesta_manual, "question_id": qid}


@router.post("/api/ml/preguntas/{qid}/crear-lead")
async def crear_lead_desde_pregunta(
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Crea un lead en el CRM a partir de una pregunta de ML.
    Recibe: { nombre, telefono, item_titulo, texto_pregunta, producto_tipo }
    """
    from database.models import Lead
    from routers.leads import asignar_asesor_round_robin

    data = await request.json()
    nombre = data.get("nombre", "Comprador MercadoLibre")
    telefono = data.get("telefono", "")
    item_titulo = data.get("item_titulo", "")
    texto = data.get("texto_pregunta", "")
    producto_tipo = data.get("producto_tipo", "SIN_DEFINIR")

    # Verificar si ya existe un lead con ese teléfono (o misma fuente ML)
    if telefono:
        existente = db.query(Lead).filter(Lead.telefono == telefono).first()
        if existente:
            return {"ok": True, "lead_id": existente.id, "ya_existia": True}

    asesor_id = asignar_asesor_round_robin(db)
    notas = f"[MERCADOLIBRE] Pregunta #{qid}\nProducto: {item_titulo}\nPregunta: {texto}"

    lead = Lead(
        nombre=nombre,
        telefono=telefono,
        producto_interes=producto_tipo,
        modelo_especifico=item_titulo[:200] if item_titulo else "",
        forma_pago="SIN_DEFINIR",
        estado="NUEVO",
        origen="MERCADOLIBRE",
        notas=notas,
        asesor_apertura_id=asesor_id,
        utm_source="mercadolibre",
        utm_medium="organic",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Notificar al asesor asignado
    if asesor_id:
        asesor = db.query(db.get_bind().engine.__class__).filter_by(id=asesor_id).first() if False else None
        try:
            from routers.leads import _notificar_asesor_lead_nuevo
            from database.models import Usuario as U
            u = db.query(U).filter(U.id == asesor_id).first()
            if u:
                _notificar_asesor_lead_nuevo(db, u, lead)
        except Exception:
            pass

    return {"ok": True, "lead_id": lead.id, "ya_existia": False}


# ─── API — ESTADÍSTICAS POR PUBLICACIÓN ──────────────────────────────────────

@router.get("/api/ml/stats/{item_id}")
async def get_stats_publicacion(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Visitas, ventas y preguntas de una publicación."""
    token = await _get_token(db)

    async with httpx.AsyncClient(timeout=12) as c:
        item_r = await c.get(f"{ML_BASE}/items/{item_id}", headers=_ml_headers(token))

    if item_r.status_code != 200:
        raise HTTPException(item_r.status_code, "Error obteniendo item")

    item = item_r.json()

    return {
        "item_id":   item_id,
        "titulo":    item.get("title", ""),
        "precio":    item.get("price", 0),
        "estado":    item.get("status", ""),
        "visitas":   item.get("sold_quantity", 0),
        "stock":     item.get("available_quantity", 0),
        "permalink": item.get("permalink", ""),
        "thumbnail": item.get("thumbnail", ""),
        "fecha_creacion": item.get("date_created", ""),
        "fecha_vencimiento": item.get("stop_time", ""),
        "salud": item.get("health", None),
    }


# ─── API — DASHBOARD RESUMEN ML ───────────────────────────────────────────────

async def _ml_visitas_usuario_rango(token: str, user_id: str, date_from: str, date_to: str) -> int:
    """Visitas totales de todas las publicaciones del vendedor en un rango de fechas."""
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(
                f"{ML_BASE}/users/{user_id}/items_visits",
                headers=_ml_headers(token),
                params={"date_from": date_from, "date_to": date_to},
            )
        if r.status_code != 200:
            return 0
        data = r.json()
        if isinstance(data, dict):
            return data.get("total_visits", 0) or 0
        if isinstance(data, list):
            return sum(d.get("total_visits", 0) or 0 for d in data)
    except Exception:
        pass
    return 0


@router.get("/api/ml/dashboard")
async def get_dashboard_ml(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Dashboard real: publicaciones activas, preguntas sin responder, visitas de
    hoy, y ranking de publicaciones por visitas y por ventas (con % de
    conversión). El ranking cubre hasta 50 publicaciones activas — si hay más,
    es un recorte representativo, no el total exacto.
    """
    token = get_config_value("ml_access_token", db)
    if not token:
        return {"conectado": False}

    try:
        user_id = await _get_user_id(token, db)

        async with httpx.AsyncClient(timeout=12) as c:
            r_items = await c.get(
                f"{ML_BASE}/users/{user_id}/items/search",
                headers=_ml_headers(token),
                params={"limit": 1},
            )
            r_q = await c.get(
                f"{ML_BASE}/questions/search",
                headers=_ml_headers(token),
                params={"seller_id": user_id, "status": "UNANSWERED", "limit": 1},
            )
            r_user = await c.get(f"{ML_BASE}/users/{user_id}", headers=_ml_headers(token))

        total_pubs = r_items.json().get("paging", {}).get("total", 0) if r_items.status_code == 200 else 0
        total_q    = r_q.json().get("total", 0) if r_q.status_code == 200 else 0

        # Reputación del vendedor — factor #1 confirmado del algoritmo de
        # ranking de ML (a más nivel, más exposición y más conversión).
        reputacion = None
        if r_user.status_code == 200:
            rep = (r_user.json().get("seller_reputation") or {})
            metrics = rep.get("metrics") or {}
            transactions = rep.get("transactions") or {}
            reputacion = {
                "nivel": rep.get("level_id"),  # ej "5_green", "4_light_green", "3_yellow", "2_orange", "1_red", None
                "power_seller_status": rep.get("power_seller_status"),  # None | silver | gold | platinum
                "transacciones_completadas": transactions.get("completed"),
                "transacciones_totales": transactions.get("total"),
                "reclamos_pct": ((metrics.get("claims") or {}).get("rate") or 0) * 100,
                "cancelaciones_pct": ((metrics.get("cancellations") or {}).get("rate") or 0) * 100,
            }

        # /users/{id}/items_visits solo acepta fecha simple YYYY-MM-DD (sin
        # hora) — confirmado con la API real, cualquier otro formato ISO da
        # 400. ML interpreta la fecha en horario de Argentina (UTC-3), no UTC
        # — usar datetime.utcnow() da el día equivocado durante varias horas
        # cada día (confirmado en vivo: con fecha UTC daba 0 visitas, con
        # fecha Argentina daba las visitas reales).
        hoy_str = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")
        visitas_hoy = await _ml_visitas_usuario_rango(token, user_id, hoy_str, hoy_str)

        publicaciones = await _fetch_publicaciones_activas(db, token, user_id, limit=50)

        def _resumen(p: dict) -> dict:
            conv = round(p["ventas"] / p["visitas"] * 100, 1) if p["visitas"] else 0.0
            return {
                "item_id": p["item_id"], "titulo": p["titulo"],
                "visitas": p["visitas"], "ventas": p["ventas"],
                "conversion_pct": conv, "permalink": p["permalink"],
            }

        top_visitas = sorted(publicaciones, key=lambda p: p["visitas"], reverse=True)[:5]
        top_ventas = sorted(publicaciones, key=lambda p: p["ventas"], reverse=True)[:5]

        return {
            "conectado": True,
            "publicaciones_activas": total_pubs,
            "preguntas_sin_responder": total_q,
            "visitas_hoy_total": visitas_hoy,
            "reputacion": reputacion,
            "top_por_visitas": [_resumen(p) for p in top_visitas],
            "top_por_ventas": [_resumen(p) for p in top_ventas],
        }
    except Exception as e:
        return {"conectado": False, "error": str(e)[:80]}


@router.get("/api/ml/listing-types")
async def ml_listing_types(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Diagnóstico: tipos de publicación disponibles en MLA (con el token de la cuenta)."""
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")
    tok = await _ml_valid_token(db)
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(f"{ML_BASE}/sites/MLA/listing_types", headers=_ml_headers(tok))
    if r.status_code != 200:
        return {"status": r.status_code, "error": r.text[:300]}
    return {"status": 200, "listing_types": [{"id": x.get("id"), "name": x.get("name")} for x in r.json()]}


@router.get("/api/ml/precio-mercado")
async def ml_precio_mercado(
    q: str,
    categoria: Optional[str] = None,
    limite: int = 5,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Devuelve las publicaciones más baratas del sitio para un término (referencia de mercado)."""
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")
    tok = await _ml_valid_token(db)
    params = {"q": q, "sort": "price_asc", "limit": max(1, min(limite, 20))}
    if categoria:
        params["category"] = categoria
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ML_BASE}/sites/MLA/search", params=params, headers=_ml_headers(tok))
        if r.status_code == 200:
            d = r.json()
            res = [{"titulo": x.get("title"), "precio": x.get("price"),
                    "link": x.get("permalink")} for x in d.get("results", [])[:limite]]
            precios = [x["precio"] for x in res if x.get("precio")]
            return {"fuente": "search", "status": 200, "total": d.get("paging", {}).get("total"),
                    "mas_barato": min(precios) if precios else None, "resultados": res}
        # Fallback: API de catálogo (productos)
        rc = await c.get(f"{ML_BASE}/products/search",
                         params={"site_id": "MLA", "status": "active", "q": q},
                         headers=_ml_headers(tok))
        if rc.status_code != 200:
            return {"fuente": "ninguna", "search_status": r.status_code,
                    "catalogo_status": rc.status_code, "error": rc.text[:200]}
        dc = rc.json()
        prods = dc.get("results", [])[:limite]
        salida = []
        for p in prods:
            pid = p.get("id")
            precio = None
            try:
                rp = await c.get(f"{ML_BASE}/products/{pid}", headers=_ml_headers(tok))
                if rp.status_code == 200:
                    precio = (rp.json().get("buy_box_winner") or {}).get("price")
            except Exception:
                pass
            salida.append({"titulo": p.get("name"), "precio": precio, "product_id": pid})
    precios = [x["precio"] for x in salida if x.get("precio")]
    return {"fuente": "catalogo", "status": 200, "total": dc.get("paging", {}).get("total"),
            "mas_barato": min(precios) if precios else None, "resultados": salida}
