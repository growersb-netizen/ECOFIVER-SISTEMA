"""
Módulo 13 — MercadoLibre
Publicaciones, creación con IA, sincronización de precios y renovación automática.
Acceso: ADMIN y COORDINADOR_OPERATIVO
"""
import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PublicacionML, Usuario, ConfiguracionSistema
from routers.auth import require_auth, get_user_roles, get_current_user
from routers.configuracion import get_config_value, _require_config_access
from database.encryption import encrypt_value
from utils.ai_client import ai_complete

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")
ML_BASE = "https://api.mercadolibre.com"
ML_AUTH = "https://auth.mercadolibre.com.ar"
ML_DEFAULT_REDIRECT = "https://eco-crm-production.up.railway.app/mercadolibre/callback"


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

# Categorías ML para cada tipo de producto
ML_CATEGORIAS = {
    "PISCINA": "MLA9226",    # Piletas y Jacuzzis
    "MODULO":  "MLA1647",    # Casas Prefabricadas
    "COMBO":   "MLA9226",
}


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


# ─── PÁGINAS ──────────────────────────────────────────────────────────────────

@router.get("/mercadolibre", response_class=HTMLResponse)
async def ml_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    roles = get_user_roles(current_user)
    catalogo_data = None
    try:
        from routers.catalogo import get_catalogo_data
        catalogo_data = get_catalogo_data(db)
    except Exception:
        pass
    return templates.TemplateResponse("mercadolibre.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "catalogo": catalogo_data or {"piscinas": {"modelos": [], "colores": []}, "modulos": {"modelos": []}},
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

@router.get("/api/ml/publicaciones")
async def get_publicaciones(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    token = await _get_token(db)
    user_id = await _get_user_id(token, db)

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{ML_BASE}/users/{user_id}/items/search",
            headers=_ml_headers(token),
            params={"limit": 50, "offset": 0},
        )
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Error ML: {r.text[:200]}")

    item_ids = r.json().get("results", [])
    if not item_ids:
        return []

    # Obtener detalles de cada item en paralelo (máx 20 por llamada)
    batch = ",".join(item_ids[:20])
    async with httpx.AsyncClient(timeout=15) as c:
        r2 = await c.get(
            f"{ML_BASE}/items",
            headers=_ml_headers(token),
            params={"ids": batch},
        )
    if r2.status_code != 200:
        raise HTTPException(r2.status_code, "Error al obtener detalles de publicaciones")

    items = []
    for entry in r2.json():
        body = entry.get("body", {})
        if not body:
            continue
        items.append({
            "item_id":      body.get("id"),
            "titulo":       body.get("title"),
            "precio":       body.get("price"),
            "estado_ml":    body.get("status"),
            "visitas":      body.get("sold_quantity", 0),
            "stock":        body.get("available_quantity", 0),
            "permalink":    body.get("permalink"),
            "thumbnail":    body.get("thumbnail"),
            "fecha_vencimiento": body.get("stop_time"),
        })

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
    """Pausa, activa o renueva una publicación."""
    token = await _get_token(db)
    data = await request.json()
    accion = data.get("accion")  # pause | activate | renew

    payload: dict = {}
    if accion == "pause":
        payload = {"status": "paused"}
    elif accion == "activate":
        payload = {"status": "active"}
    elif accion == "renew":
        payload = {"status": "active"}
    else:
        raise HTTPException(400, "Acción inválida. Usar: pause | activate | renew")

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


# ─── API — GENERAR DESCRIPCIÓN CON CLAUDE ────────────────────────────────────

@router.post("/api/ml/generar-descripcion")
async def generar_descripcion(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    claude_key = get_config_value("claude_api_key", db)
    if not claude_key:
        raise HTTPException(400, "Claude API Key no configurada. Ir a Configuración → API Keys.")

    data = await request.json()
    tipo = data.get("tipo", "PISCINA")
    modelo = data.get("modelo", "")
    color = data.get("color", "")
    superficie = data.get("superficie_m2", "")

    detalles_producto = f"Tipo: {tipo}\nModelo: {modelo}"
    if color:
        detalles_producto += f"\nColor: {color}"
    if superficie:
        detalles_producto += f"\nSuperficie: {superficie}m²"

    prompt = f"""Generá un anuncio de MercadoLibre Argentina optimizado para SEO para este producto de Eco Módulos & Piscinas.

IDIOMA Y TONO OBLIGATORIO: escribís siempre en castellano de Argentina — no en español neutro.
Usás "vos", "acá", "querés", "podés", "tenés". Tono cálido, cercano y profesional: como un experto que le habla de igual a igual al comprador, genera confianza y lo invita a dar el paso, sin ser informal.

Producto:
{detalles_producto}

Necesito:

1. TÍTULO (máximo 60 caracteres, incluir palabras clave de búsqueda como "piscina", "módulo", "instalación", etc.)

2. DESCRIPCIÓN COMPLETA (mínimo 400 palabras) con esta estructura:
   - Presentación del producto con características técnicas
   - {'Tecnología de fibra de vidrio de alta resistencia, proceso de laminación manual' if tipo == 'PISCINA' else 'Tecnología NCE (Núcleo de Celulosa Estructural), paneles termoacústicos'}
   - Dimensiones y capacidades según el modelo
   - Beneficios principales (durabilidad, bajo mantenimiento, garantía)
   - Proceso de instalación incluida con cobertura nacional
   - Financiación disponible: hasta 24 cuotas sin banco
   - Fabricación propia en Zárate, Buenos Aires
   - CTA final: "Consultá ahora por WhatsApp para más información y visitar nuestro showroom en CABA"
   - Palabras clave SEO integradas naturalmente

Respondé EXACTAMENTE con este JSON (sin markdown, sin texto extra):
{{"titulo": "...", "descripcion": "..."}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": claude_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-20240307",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Claude API error: {r.text[:200]}")

        texto = r.json()["content"][0]["text"].strip()
        # Intentar parsear JSON
        try:
            result = json.loads(texto)
        except json.JSONDecodeError:
            # Intentar extraer JSON con regex como fallback
            import re
            match = re.search(r'\{.*\}', texto, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                raise HTTPException(500, "Claude no devolvió JSON válido")

        return {
            "ok": True,
            "titulo": result.get("titulo", ""),
            "descripcion": result.get("descripcion", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error generando descripción: {str(e)[:200]}")


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
    categoria_id = ML_CATEGORIAS.get(tipo, ML_CATEGORIAS["PISCINA"])

    payload = {
        "title": data.get("titulo", ""),
        "category_id": data.get("categoria_ml_id") or categoria_id,
        "price": float(data.get("precio", 0)),
        "currency_id": "ARS",
        "available_quantity": int(data.get("stock", 1)),
        "buying_mode": "buy_it_now",
        "item_condition": "new",
        "listing_type_id": "gold_special",
        "description": {
            "plain_text": data.get("descripcion", ""),
        },
        "pictures": [
            {"source": url}
            for url in data.get("fotos_urls", [])
            if url
        ],
        "attributes": [
            {"id": "BRAND", "value_name": "Eco Módulos"},
        ],
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
    - sugerir_solo=true → genera texto con IA y lo devuelve sin publicar
    - respuesta_manual  → publica ese texto directamente sin llamar IA
    - (vacío)           → genera con IA y publica
    """
    token = await _get_token(db)
    data  = await request.json()

    sugerir_solo   = data.get("sugerir_solo", False)
    pregunta_texto = data.get("pregunta_texto", data.get("texto_pregunta", ""))
    item_titulo    = data.get("item_titulo", "")
    respuesta_manual = data.get("respuesta_manual", data.get("respuesta", ""))

    # ── Necesitamos texto de respuesta ──────────────────────────────────────
    if not respuesta_manual:

        prompt = (
            f"Sos asesor de ventas de Eco Módulos & Piscinas Argentina.\n"
            f"Escribís siempre en castellano de Argentina — no en español neutro. "
            f"Usás 'vos', 'acá', 'podés', 'tenés'. Tu tono es cálido, cercano y profesional: "
            f"como alguien que conoce el producto y le habla de igual a igual al comprador, sin ser informal.\n"
            f"Producto: {item_titulo}\n"
            f"Pregunta del comprador: {pregunta_texto}\n\n"
            f"Respondé de forma CORTA (máximo 3 oraciones), con el tono indicado.\n"
            f"Incluí siempre: instalación incluida, fabricamos en Zárate, ofrecemos financiación propia.\n"
            f"Si preguntan por precio: 'Consultá por WhatsApp para una cotización personalizada según tu localidad.'\n"
            f"NO uses markdown. Solo texto plano."
        )
        try:
            respuesta_manual = await ai_complete(db, prompt, max_tokens=400, temperature=0.7)
            respuesta_manual = " ".join(respuesta_manual.split())
        except Exception as e:
            raise HTTPException(502, f"Error generando respuesta con IA: {e}. Configurar Grok, Gemini o Claude en Configuración → API Keys.")

    # ── Solo sugerir: devolver sin publicar ─────────────────────────────────
    if sugerir_solo:
        return {"ok": True, "respuesta_sugerida": respuesta_manual}

    # ── Publicar en ML ──────────────────────────────────────────────────────
    body = {"question_id": qid, "text": respuesta_manual[:2000]}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{ML_BASE}/answers", headers=_ml_headers(token), json=body)

    if r.status_code not in (200, 201):
        raise HTTPException(r.status_code, f"Error ML al responder: {r.text[:200]}")

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

@router.get("/api/ml/dashboard")
async def get_dashboard_ml(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Resumen rápido: publicaciones activas, preguntas sin responder, ventas."""
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

        total_pubs = r_items.json().get("paging", {}).get("total", 0) if r_items.status_code == 200 else 0
        total_q    = r_q.json().get("total", 0) if r_q.status_code == 200 else 0

        return {
            "conectado": True,
            "publicaciones_activas": total_pubs,
            "preguntas_sin_responder": total_q,
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
