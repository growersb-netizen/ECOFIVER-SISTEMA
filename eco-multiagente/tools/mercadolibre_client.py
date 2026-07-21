"""
Cliente MercadoLibre Argentina — gestión de publicaciones del vendedor.

Cubre OAuth 2.0 + operaciones de seller:
  - Conexión de cuenta (authorization code → access/refresh token)
  - Listado, detalle, creación, edición, pausa/activación de publicaciones
  - Ventas (orders), preguntas, métricas (visitas)

Las credenciales y tokens se guardan en el .env persistente (/data/.env):
  ML_APP_ID         — App ID (client_id) de tu app en developers.mercadolibre.com.ar
  ML_SECRET         — Secret key (client_secret)
  ML_REDIRECT_URI   — Redirect URI configurada en la app
  ML_ACCESS_TOKEN   — token de acceso (se renueva solo)
  ML_REFRESH_TOKEN  — token de refresco
  ML_USER_ID        — ID numérico del vendedor
  ML_TOKEN_EXPIRES  — timestamp epoch de expiración del access token

Si no hay credenciales/conexión, las funciones devuelven {"conectado": False}
para que el panel muestre el estado "conectá tu cuenta" sin romperse.
"""

import os
import time
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

API = "https://api.mercadolibre.com"
AUTH_BASE = "https://auth.mercadolibre.com.ar/authorization"
TOKEN_URL = f"{API}/oauth/token"
SITE = "MLA"  # Argentina

_env_base = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent.parent
_ENV_PATH = _env_base / ".env"


# ── Persistencia de tokens en .env ──────────────────────────────────────────

def _guardar_env(vars: dict) -> None:
    """Escribe/actualiza variables en /data/.env sin borrar el resto."""
    try:
        import re as _re
        contenido = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
        for k, v in vars.items():
            v = str(v)
            os.environ[k] = v
            if _re.search(rf"^{k}=", contenido, _re.MULTILINE):
                contenido = _re.sub(rf"^{k}=.*$", f"{k}={v}", contenido, flags=_re.MULTILINE)
            else:
                contenido = contenido.rstrip("\n") + f"\n{k}={v}\n"
        _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ENV_PATH.write_text(contenido, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[ML] No se pudo guardar tokens: {e}")


def esta_configurado() -> bool:
    """True si hay App ID + Secret cargados (se puede iniciar OAuth)."""
    return bool(os.getenv("ML_APP_ID") and os.getenv("ML_SECRET"))


def esta_conectado() -> bool:
    """True si hay tokens de una cuenta conectada."""
    return bool(os.getenv("ML_ACCESS_TOKEN") and os.getenv("ML_USER_ID"))


# ── OAuth ───────────────────────────────────────────────────────────────────

def url_autorizacion() -> str:
    """Devuelve la URL a la que el usuario debe ir para autorizar la app."""
    app_id   = os.getenv("ML_APP_ID", "")
    redirect = os.getenv("ML_REDIRECT_URI", "")
    return (
        f"{AUTH_BASE}?response_type=code&client_id={app_id}&redirect_uri={redirect}"
    )


async def intercambiar_codigo(code: str) -> dict:
    """Intercambia el authorization code por access/refresh token y los guarda."""
    if not esta_configurado():
        return {"ok": False, "error": "Falta ML_APP_ID / ML_SECRET"}
    data = {
        "grant_type":    "authorization_code",
        "client_id":     os.getenv("ML_APP_ID", ""),
        "client_secret": os.getenv("ML_SECRET", ""),
        "code":          code,
        "redirect_uri":  os.getenv("ML_REDIRECT_URI", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(TOKEN_URL, data=data)
            j = r.json()
            if r.status_code != 200 or "access_token" not in j:
                return {"ok": False, "error": j.get("message", j.get("error_description", str(j)[:200]))}
            _guardar_env({
                "ML_ACCESS_TOKEN":  j["access_token"],
                "ML_REFRESH_TOKEN": j.get("refresh_token", ""),
                "ML_USER_ID":       str(j.get("user_id", "")),
                "ML_TOKEN_EXPIRES": str(int(time.time()) + int(j.get("expires_in", 21600))),
            })
            return {"ok": True, "user_id": j.get("user_id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _refrescar_token() -> bool:
    """Renueva el access token usando el refresh token."""
    refresh = os.getenv("ML_REFRESH_TOKEN", "")
    if not refresh or not esta_configurado():
        return False
    data = {
        "grant_type":    "refresh_token",
        "client_id":     os.getenv("ML_APP_ID", ""),
        "client_secret": os.getenv("ML_SECRET", ""),
        "refresh_token": refresh,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(TOKEN_URL, data=data)
            j = r.json()
            if "access_token" not in j:
                logger.warning(f"[ML] refresh falló: {j}")
                return False
            _guardar_env({
                "ML_ACCESS_TOKEN":  j["access_token"],
                "ML_REFRESH_TOKEN": j.get("refresh_token", refresh),
                "ML_TOKEN_EXPIRES": str(int(time.time()) + int(j.get("expires_in", 21600))),
            })
            return True
    except Exception as e:
        logger.warning(f"[ML] refresh error: {e}")
        return False


async def _token() -> str:
    """Devuelve un access token válido, refrescando si expiró."""
    exp = int(os.getenv("ML_TOKEN_EXPIRES", "0") or "0")
    if exp and time.time() > (exp - 120):
        await _refrescar_token()
    return os.getenv("ML_ACCESS_TOKEN", "")


async def _get(path: str, params: dict | None = None) -> dict:
    tok = await _token()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{API}{path}", params=params or {},
                        headers={"Authorization": f"Bearer {tok}"})
        # Reintento único si el token quedó inválido
        if r.status_code == 401 and await _refrescar_token():
            tok = os.getenv("ML_ACCESS_TOKEN", "")
            r = await c.get(f"{API}{path}", params=params or {},
                            headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> dict:
    tok = await _token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}{path}", json=body,
                         headers={"Authorization": f"Bearer {tok}"})
        return r.json() if r.content else {"status_code": r.status_code}


async def _put(path: str, body: dict) -> dict:
    tok = await _token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(f"{API}{path}", json=body,
                        headers={"Authorization": f"Bearer {tok}"})
        return r.json() if r.content else {"status_code": r.status_code}


# ── Operaciones de vendedor ─────────────────────────────────────────────────

async def info_cuenta() -> dict:
    """Datos de la cuenta conectada."""
    if not esta_conectado():
        return {"conectado": False}
    try:
        me = await _get("/users/me")
        return {
            "conectado":  True,
            "nickname":   me.get("nickname", ""),
            "user_id":    me.get("id", ""),
            "reputacion": (me.get("seller_reputation", {}) or {}).get("level_id", ""),
            "ventas_total": (me.get("seller_reputation", {}) or {})
                            .get("transactions", {}).get("completed", 0),
        }
    except Exception as e:
        logger.warning(f"[ML] info_cuenta: {e}")
        return {"conectado": False, "error": str(e)}


async def metricas() -> dict:
    """Resumen para el panel: publicaciones activas/pausadas, ventas, preguntas."""
    if not esta_conectado():
        return {"conectado": False}
    user_id = os.getenv("ML_USER_ID", "")
    out = {"conectado": True, "activas": 0, "pausadas": 0, "ventas_pagadas": 0,
           "monto_ventas": 0, "preguntas_sin_responder": 0, "visitas_total": 0}
    try:
        act = await _get(f"/users/{user_id}/items/search", {"status": "active", "limit": 1})
        out["activas"] = act.get("paging", {}).get("total", 0)
        pau = await _get(f"/users/{user_id}/items/search", {"status": "paused", "limit": 1})
        out["pausadas"] = pau.get("paging", {}).get("total", 0)
    except Exception as e:
        logger.warning(f"[ML] metricas items: {e}")
    try:
        orders = await _get("/orders/search", {"seller": user_id, "order.status": "paid", "limit": 50})
        results = orders.get("results", [])
        out["ventas_pagadas"] = orders.get("paging", {}).get("total", len(results))
        out["monto_ventas"] = sum(float(o.get("total_amount", 0) or 0) for o in results)
    except Exception as e:
        logger.warning(f"[ML] metricas orders: {e}")
    try:
        q = await _get("/questions/search", {"seller_id": user_id, "status": "UNANSWERED", "limit": 1})
        out["preguntas_sin_responder"] = q.get("total", 0)
    except Exception as e:
        logger.warning(f"[ML] metricas questions: {e}")
    return out


async def listar_publicaciones(status: str = "active", limit: int = 50) -> list:
    """Lista publicaciones del vendedor con datos clave."""
    if not esta_conectado():
        return []
    user_id = os.getenv("ML_USER_ID", "")
    try:
        search = await _get(f"/users/{user_id}/items/search",
                            {"status": status, "limit": limit})
        ids = search.get("results", [])
        if not ids:
            return []
        items = []
        # multiget en lotes de 20
        for i in range(0, len(ids), 20):
            lote = ",".join(ids[i:i+20])
            data = await _get("/items", {"ids": lote,
                "attributes": "id,title,price,available_quantity,sold_quantity,status,permalink,thumbnail"})
            for entry in data:
                body = entry.get("body", {})
                items.append({
                    "id":        body.get("id"),
                    "titulo":    body.get("title"),
                    "precio":    body.get("price"),
                    "stock":     body.get("available_quantity"),
                    "vendidos":  body.get("sold_quantity"),
                    "estado":    body.get("status"),
                    "permalink": body.get("permalink"),
                    "thumbnail": body.get("thumbnail"),
                })
        return items
    except Exception as e:
        logger.warning(f"[ML] listar_publicaciones: {e}")
        return []


async def cambiar_estado(item_id: str, nuevo_estado: str) -> dict:
    """Pausa o activa una publicación. nuevo_estado: 'paused' | 'active'."""
    return await _put(f"/items/{item_id}", {"status": nuevo_estado})


async def actualizar_publicacion(item_id: str, cambios: dict) -> dict:
    """
    Actualiza campos de una publicación.
    cambios admite: price, available_quantity, title (y otros válidos de ML).
    """
    permitidos = {k: v for k, v in cambios.items()
                  if k in ("price", "available_quantity", "title")}
    return await _put(f"/items/{item_id}", permitidos)


async def crear_publicacion(datos: dict) -> dict:
    """
    Crea una publicación nueva.
    datos requeridos: title, category_id, price, available_quantity,
                      condition, listing_type_id, pictures(list de urls), description.
    """
    body = {
        "title":            datos.get("title", "")[:60],
        "category_id":      datos.get("category_id", ""),
        "price":            datos.get("price", 0),
        "currency_id":      "ARS",
        "available_quantity": datos.get("available_quantity", 1),
        "condition":        datos.get("condition", "new"),
        "listing_type_id":  datos.get("listing_type_id", "gold_special"),
        "pictures":         [{"source": u} for u in datos.get("pictures", []) if u],
        "sale_terms":       datos.get("sale_terms", []),
    }
    if datos.get("description"):
        body["description"] = {"plain_text": datos["description"]}
    res = await _post("/items", body)
    return res


async def sugerir_categoria(titulo: str) -> dict:
    """Predice la categoría de MercadoLibre a partir de un título (endpoint público)."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{API}/sites/{SITE}/domain_discovery/search",
                            params={"q": titulo, "limit": 1})
            arr = r.json()
            if arr:
                return {"category_id": arr[0].get("category_id"),
                        "category_name": arr[0].get("category_name")}
    except Exception as e:
        logger.warning(f"[ML] sugerir_categoria: {e}")
    return {}
