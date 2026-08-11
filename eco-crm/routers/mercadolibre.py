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
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PublicacionML, Usuario, ConfiguracionSistema, BorradorML, MLCategoriaLinea, RespuestaAutoML, FotoML, SetFotosML
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
# Verificadas en ML Argentina 2025-2026:
#   MLA373513 → Piletas y Piscinas de Fibra
#   MLA88471  → Jacuzzis e Hidromasajes
#   MLA413502 → Cabañas y Casas Prefabricadas (classified)
#   MLA1647   → Casas Prefabricadas (alternativa)
ML_CATEGORIAS = {
    # ── Piscinas ──────────────────────────────────────────────────────────────
    "PISCINA":              "MLA373513",  # Piletas de Fibra de Vidrio
    "MINIPISCINA":          "MLA373513",
    # ── Hidromasajes y baños ──────────────────────────────────────────────────
    "HIDROMASAJE":          "MLA88471",   # Jacuzzis e Hidromasajes ✓
    "BANERA":               "MLA88471",   # en ML AR las bañeras van en la misma cat
    "ACCESORIO_HIDROMASAJE": "",          # predictor por título
    # ── Módulos y viviendas ───────────────────────────────────────────────────
    "MODULO":               "MLA413502",  # Cabañas y Casas Prefabricadas (classified)
    "MODULO_HABITACIONAL":  "MLA413502",  # 6-18 m² — espacio habitacional auxiliar
    "VIVIENDA_MODULAR":     "MLA413502",  # 24+ m² — vivienda completa
    "MODULO_DEPOSITO":      "MLA413502",
    "COMBO":                "MLA413502",
    "QUINCHO":              "MLA413502",
    "PERGOLA":              "MLA413502",
    "GARITA_SEGURIDAD":     "MLA413502",
    # ── Predictor por título (heterogéneos o sin categoría fija confirmada) ───
    "BANIO_QUIMICO":        "",
    "RECEPTACULO":          "",
    "REPOSERA_FIBRA":       "",
    "CUCHA":                "",
    "CUCHA_PERRO":          "",
    "DEPOSITO_JARDIN":      "",
    "ACCESORIO_PISCINA":    "",
    "EQUIPO_PISCINA":       "",
}
# Las entradas con "" usan el predictor ML en vivo al publicar (más preciso pero
# requiere token). Las entradas con MLA* son fallback si el predictor falla.

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


# ─── MIGRACIÓN DE CUENTA ──────────────────────────────────────────────────────

@router.get("/api/ml/migracion/status")
async def migracion_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Estadísticas del estado actual para planificar la migración de cuenta ML."""
    pubs_activas  = db.query(PublicacionML).filter(PublicacionML.estado_ml == "active").count()
    pubs_total    = db.query(PublicacionML).filter(PublicacionML.estado_ml != "migrada").count()
    bors_pub      = db.query(BorradorML).filter(BorradorML.estado == "publicada").count()
    bors_total    = db.query(BorradorML).count()
    fotos_bib     = db.query(FotoML).count()
    sets          = db.query(SetFotosML).count()
    uid           = get_config_value("ml_user_id", db)
    return {
        "publicaciones_activas":  pubs_activas,
        "publicaciones_total":    pubs_total,
        "borradores_publicados":  bors_pub,
        "borradores_total":       bors_total,
        "fotos_biblioteca":       fotos_bib,
        "sets_fotos":             sets,
        "usuario_ml":             uid or "—",
    }


@router.get("/api/ml/migracion/backup")
async def migracion_backup(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Descarga un JSON completo con todo lo necesario para recrear la cuenta en ML nueva:
    publicaciones actuales (MLA IDs + datos), borradores publicados, biblioteca de
    fotos y sets. Guardar ANTES de ejecutar 'preparar'.
    """
    publicaciones = [
        {
            "item_id":          p.item_id,
            "titulo":           p.titulo,
            "descripcion":      p.descripcion,
            "precio":           p.precio,
            "estado_ml":        p.estado_ml,
            "producto":         p.producto,
            "modelo_especifico": p.modelo_especifico,
            "created_at":       p.created_at.isoformat() if p.created_at else None,
        }
        for p in db.query(PublicacionML).filter(PublicacionML.estado_ml != "migrada").all()
    ]

    borradores = [
        {
            "id":             b.id,
            "titulo":         b.titulo,
            "descripcion":    b.descripcion,
            "precio":         b.precio,
            "costo":          b.costo,
            "categoria":      b.categoria,
            "producto":       b.producto,
            "seller_sku":     b.seller_sku,
            "fotos_json":     b.fotos_json,
            "atributos_json": b.atributos_json,
            "listing_type":   b.listing_type,
            "item_id":        b.item_id,
            "permalink":      b.permalink,
            "modelo_nombre":  b.modelo_nombre,
            "estado":         b.estado,
        }
        for b in db.query(BorradorML).filter(BorradorML.estado == "publicada").all()
    ]

    fotos = [
        {
            "id":            f.id,
            "nombre":        f.nombre,
            "url":           f.url,
            "tipo_producto": f.tipo_producto,
            "modelo":        f.modelo,
            "tag":           f.tag,
            "orden":         f.orden,
        }
        for f in db.query(FotoML).order_by(FotoML.orden).all()
    ]

    sets_fotos = [
        {
            "id":            s.id,
            "nombre":        s.nombre,
            "tipo_producto": s.tipo_producto,
            "modelo":        s.modelo,
            "foto_ids_json": s.foto_ids_json,
        }
        for s in db.query(SetFotosML).all()
    ]

    uid   = get_config_value("ml_user_id", db) or "ML"
    fecha = datetime.now().strftime("%Y%m%d_%H%M")

    data = {
        "backup_version": "1.0",
        "fecha":          datetime.now().isoformat(),
        "cuenta_ml":      uid,
        "resumen": {
            "publicaciones":        len(publicaciones),
            "borradores_publicados": len(borradores),
            "fotos_biblioteca":     len(fotos),
            "sets_fotos":           len(sets_fotos),
        },
        "publicaciones":        publicaciones,
        "borradores_publicados": borradores,
        "foto_biblioteca":      fotos,
        "sets_fotos":           sets_fotos,
    }

    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="backup-ml-{uid}-{fecha}.json"'},
    )


@router.post("/api/ml/migracion/preparar")
async def migracion_preparar(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Prepara el sistema para operar con una cuenta ML nueva:
    1. Resetea borradores publicados → estado 'borrador' (limpia item_id / permalink).
    2. Archiva PublicacionML actuales marcándolas como 'migrada' (no se borran).

    IRREVERSIBLE — descargar backup primero con GET /api/ml/migracion/backup.
    """
    data = await request.json()
    if not data.get("confirmar"):
        raise HTTPException(400, "Requerido: {\"confirmar\": true}")

    # 1. Resetear borradores publicados
    bors = db.query(BorradorML).filter(BorradorML.estado == "publicada").all()
    for b in bors:
        b.estado    = "borrador"
        b.item_id   = None
        b.permalink = None
        b.error_msg = ""

    # 2. Archivar publicaciones de la cuenta vieja (sin borrar → referencia histórica)
    pubs = db.query(PublicacionML).filter(PublicacionML.estado_ml != "migrada").all()
    for p in pubs:
        p.estado_ml = "migrada"

    db.commit()

    log.info(f"[MIGRACION] {len(bors)} borradores reseteados, {len(pubs)} publicaciones archivadas")
    return {
        "ok":                     True,
        "borradores_reseteados":  len(bors),
        "publicaciones_archivadas": len(pubs),
        "mensaje": (
            "Sistema listo para la cuenta nueva. "
            "Próximo paso: vincular la cuenta nueva desde Configuración → Conectar."
        ),
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
                      "modulos_deposito": {"tamanos": {}},
                      "hidromasajes": {}, "baneras": {}, "receptaculos": {}}
    try:
        from routers.catalogo import load_catalogo, get_all_modelos_piscina, get_all_modelos_modulo
        cat = load_catalogo()
        sup_all = cat["modulos"]["superficies_m2"]
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
                "superficies_habitacionales": [m for m in sup_all if m <= 18],
                "superficies_viviendas":      [m for m in sup_all if m > 18],
                "fotos": cat["modulos"].get("fotos", {}),
                "precios_lista": cat["modulos"].get("precios_lista", {}),
                "cuotas_max": cat["modulos"].get("cuotas_max", 60),
                "tecnologia": cat["modulos"].get("tecnologia", ""),
            },
            "modulos_deposito": cat.get("modulos_deposito", {"tamanos": {}}),
            # Líneas adicionales de productos
            "hidromasajes": {
                "modelos": cat.get("hidromasajes", {}).get("modelos", {}),
                "colores":  cat.get("hidromasajes", {}).get("colores", []),
            },
            "baneras": {
                "modelos": cat.get("baneras", {}).get("modelos", {}),
                "colores":  cat.get("baneras", {}).get("colores", []),
            },
            "receptaculos": {
                "modelos": cat.get("receptaculos", {}).get("modelos", {}),
                "colores":  cat.get("receptaculos", {}).get("colores", []),
            },
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

    # PUT /items/{id} requiere {"id": pic_id}, NO {"source": url}.
    # Subir las fotos una sola vez y reusar los IDs para todas las publicaciones.
    pic_ids: list = []
    async with httpx.AsyncClient(timeout=20) as c:
        for url in fotos:
            if not url:
                continue
            try:
                rp = await c.post(
                    f"{ML_BASE}/pictures",
                    headers=_ml_headers(token),
                    json={"source": url},
                )
                if rp.status_code in (200, 201):
                    pid = rp.json().get("id")
                    if pid:
                        pic_ids.append(pid)
            except Exception:
                pass

    if not pic_ids:
        return 0

    payload = {"pictures": [{"id": pid} for pid in pic_ids]}
    for pub in publicaciones:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.put(f"{ML_BASE}/items/{pub.item_id}", headers=_ml_headers(token), json=payload)
            if r.status_code in (200, 201, 204):
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
    variante_idx    = int(data.get("variante_idx", 0) or 0)
    total_variantes = int(data.get("total_variantes", 0) or 0)
    if not palabras:
        partes = [p for p in [tipo, modelo, color, f"{superficie}m²" if superficie else ""] if p]
        palabras = ", ".join(partes)
    if not palabras:
        raise HTTPException(400, "Ingresá algunas palabras clave del producto")

    prompt = f"""{ctx_seo_ml(descripcion_existente=palabras, variante_idx=variante_idx, total_variantes=total_variantes)}

════════════════════════════════════════════
TAREA: Generá un TÍTULO y una DESCRIPCIÓN para MercadoLibre Argentina.
════════════════════════════════════════════

Datos del producto a publicar:
{palabras}

Respondé EXCLUSIVAMENTE con este JSON válido, sin texto extra ni markdown:
{{"titulo": "...", "descripcion": "..."}}"""

    try:
        texto = await ai_complete(db, prompt, max_tokens=2800, temperature=0.4)
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
    variante_idx    = int(data.get("variante_idx", 0) or 0)
    total_variantes = int(data.get("total_variantes", 0) or 0)

    if not descripcion:
        raise HTTPException(400, "Falta la descripción del producto")

    # Tipo label para el prompt de IA — describe el producto en lenguaje natural
    tipo_label = {
        "PISCINA":               "piscina / pileta de fibra de vidrio",
        "MINIPISCINA":           "minipiscina / pileta pequeña de fibra de vidrio",
        "HIDROMASAJE":           "hidromasaje / jacuzzi / spa de acrílico sanitario EcoFiver",
        "ACCESORIO_HIDROMASAJE": "accesorio opcional para hidromasaje / jacuzzi / spa",
        "MODULO_HABITACIONAL":   "módulo habitacional de celulosa estructural (6-18 m²) — espacio auxiliar prefabricado, NO es una vivienda",
        "MODULO":                "módulo habitacional de celulosa estructural / espacio habitacional prefabricado",
        "VIVIENDA_MODULAR":      "vivienda modular de celulosa estructural / casa prefabricada (24 m² en adelante)",
        "MODULO_DEPOSITO":       "módulo depósito / galpón prefabricado de celulosa estructural",
        "QUINCHO":               "quincho prefabricado",
        "PERGOLA":               "pérgola / gazebo",
        "COMBO":                 "combo piscina y módulo habitacional",
        "BANIO_QUIMICO":         "baño químico portátil",
        "GARITA_SEGURIDAD":      "garita de seguridad prefabricada",
        "DEPOSITO_JARDIN":       "depósito de jardín prefabricado",
        "ACCESORIO_PISCINA":     "accesorio para piscina",
        "ILUMINACION_PISCINA":   "iluminación LED sumergible para piscina",
        "EQUIPO_PISCINA":        "equipo para piscina (filtro / bomba / calentador)",
        "REPUESTO_PISCINA":      "repuesto para piscina",
        "BANERA":                "bañera hidromasaje con jets de acrílico sanitario",
        "RECEPTACULO":           "receptáculo de ducha de acrílico",
        "REPOSERA_FIBRA":        "reposera de fibra de vidrio reclinable",
        "CUCHA":                 "cucha / casilla para perro",
        "CUCHA_PERRO":           "cucha / casilla para perro",
    }.get(tipo_producto, tipo_producto.lower())

    # Palabras clave obligatorias que ML usa para categorizar — el título DEBE contenerlas
    _kw_oblig = {
        "HIDROMASAJE":  "DEBE empezar con 'Hidromasaje', 'Jacuzzi' o 'Spa'",
        "BANERA":       "DEBE incluir 'Bañera Hidromasaje' o 'Jacuzzi' (sin esa palabra ML lo cataloga como gasa médica)",
        "PISCINA":      "DEBE incluir 'Piscina' o 'Pileta'",
        "MINIPISCINA":  "DEBE incluir 'Piscina' o 'Pileta' o 'Minipiscina'",
        "MODULO_DEPOSITO": "DEBE incluir 'Módulo' o 'Depósito' (NO usar 'jardín', 'versatilidad' — ML lo cataloga como gazebo)",
        "MODULO":       "DEBE incluir 'Módulo' o 'Modulo'",
        "MODULO_HABITACIONAL": "DEBE incluir 'Módulo'",
        "RECEPTACULO":  "DEBE incluir 'Receptáculo' o 'Ducha'",
        "QUINCHO":      "DEBE incluir 'Quincho'",
        "PERGOLA":      "DEBE incluir 'Pérgola'",
    }.get(tipo_producto, "")

    kw_hint = f"\n\n⚠️ REGLA CRÍTICA DE CATEGORIZACIÓN ML: {_kw_oblig}" if _kw_oblig else ""

    variante_hint = ""
    if variante_idx > 0 and total_variantes > 1:
        variante_hint = f"\n\nVARIANTE {variante_idx} DE {total_variantes}: el título debe ser ÚNICO. Usá estructura, énfasis y palabras clave distintas a las otras variantes del mismo producto."

    prompt = f"""{ctx_seo_ml(tipo_producto=tipo_label, descripcion_existente=descripcion, variante_idx=variante_idx, total_variantes=total_variantes)}

════════════════════════════════════════════
TAREA: Generá UN título optimizado para MercadoLibre Argentina.
════════════════════════════════════════════

Tipo de producto: {tipo_label}{kw_hint}

Descripción de referencia:
{descripcion}{variante_hint}

ESTRUCTURA OBLIGATORIA (en orden de prioridad):
1. Palabra clave principal de búsqueda (piscina/pileta/hidromasaje/jacuzzi/módulo/etc.)
2. Material específico (fibra de vidrio/acrílico sanitario/celulosa estructural)
3. Medidas concretas si están en la descripción (ej: 6x3 metros / 1,76x1,76)
4. Característica que diferencia (jets / autoportante / sin obra / con escalera)
PROHIBIDO USAR (el algoritmo de ML penaliza o el buscador los ignora):
- Palabras emocionales o de marketing: "ideal para", "de calidad", "premium", "exclusiva", "minimalista", "perfecta", "lujosa"
- Mayúsculas sostenidas (excepción: siglas como PRFV)
- Signos de puntuación: ! ? , ; : | — –
- Emojis
- La marca "EcoFiver"
- Nombre del vendedor
EJEMPLO CORRECTO: "Piscina fibra de vidrio 6x3 metros con escalera sin obra"
EJEMPLO INCORRECTO: "Piscina minimalista IDEAL PARA TU JARDÍN con instalación incluida"

Respondé SOLO con el título, sin explicaciones ni comillas. Máximo 60 caracteres."""

    try:
        texto = await ai_complete(db, prompt, max_tokens=80, temperature=0.2)
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
        from utils.ml_fichas_content import (
            FICHAS_PISCINAS, FICHAS_MODULOS,
            FICHAS_HIDROMASAJES, FICHAS_BANERAS, FICHAS_RECEPTACULOS,
            FICHAS_REPOSERAS, FICHAS_CUCHAS, FICHAS_BANIO_QUIMICO, FICHAS_GARITA_SEGURIDAD,
        )
    except ImportError:
        return {"piscinas": [], "modulos": [], "hidromasajes": [], "baneras": [], "receptaculos": [],
                "reposeras": [], "cuchas": [], "banio_quimico": [], "garita_seguridad": []}

    return {
        "piscinas":         list(FICHAS_PISCINAS.keys()),
        "modulos":          [f"{k}m2" for k in FICHAS_MODULOS.keys()],
        "hidromasajes":     list(FICHAS_HIDROMASAJES.keys()),
        "baneras":          list(FICHAS_BANERAS.keys()),
        "receptaculos":     list(FICHAS_RECEPTACULOS.keys()),
        "reposeras":        list(FICHAS_REPOSERAS.keys()),
        "cuchas":           list(FICHAS_CUCHAS.keys()),
        "banio_quimico":    list(FICHAS_BANIO_QUIMICO.keys()),
        "garita_seguridad": list(FICHAS_GARITA_SEGURIDAD.keys()),
    }


@router.get("/api/ml/ficha/{modelo:path}")
async def get_ficha_ml(
    modelo: str,
    db: Session = Depends(get_db),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Devuelve la ficha pre-escrita (título + descripción) para el modelo dado."""
    try:
        from utils.ml_fichas_content import (
            FICHAS_PISCINAS, FICHAS_MODULOS,
            FICHAS_HIDROMASAJES, FICHAS_BANERAS, FICHAS_RECEPTACULOS,
            FICHAS_REPOSERAS, FICHAS_CUCHAS, FICHAS_BANIO_QUIMICO, FICHAS_GARITA_SEGURIDAD,
        )
    except ImportError:
        raise HTTPException(500, "No se pudo cargar el archivo de fichas de producto")

    modelo_norm = modelo.lower().strip()

    def _buscar(diccionario: dict) -> Optional[dict]:
        """Búsqueda exacta y luego case-insensitive."""
        found = diccionario.get(modelo)
        if found:
            return found
        for k, v in diccionario.items():
            if k.lower().strip() == modelo_norm:
                return v
        return None

    # Buscar en piscinas
    ficha = _buscar(FICHAS_PISCINAS)

    # Buscar en módulos (clave numérica, acepta "12m2", "12m²", "12")
    if not ficha:
        m2_str = modelo_norm.replace("m2", "").replace("m²", "").strip()
        ficha = FICHAS_MODULOS.get(m2_str)

    # Buscar en hidromasajes, bañeras, receptáculos
    if not ficha:
        ficha = _buscar(FICHAS_HIDROMASAJES)
    if not ficha:
        ficha = _buscar(FICHAS_BANERAS)
    if not ficha:
        ficha = _buscar(FICHAS_RECEPTACULOS)

    # Buscar en reposeras, cuchas, baños químicos, garitas
    if not ficha:
        ficha = _buscar(FICHAS_REPOSERAS)
    if not ficha:
        ficha = _buscar(FICHAS_CUCHAS)
    if not ficha:
        ficha = _buscar(FICHAS_BANIO_QUIMICO)
    if not ficha:
        ficha = _buscar(FICHAS_GARITA_SEGURIDAD)

    if not ficha:
        raise HTTPException(404, f"No se encontró ficha para el modelo: {modelo}")

    return {
        "modelo":        modelo,
        "titulo_ml":     ficha.get("titulo_ml", ""),
        "descripcion_ml": ficha.get("descripcion_ml", ""),
        "atributos_ml":  ficha.get("atributos_ml", {}),
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
        "encabezado":     get_config_value("ml_desc_encabezado", db) or "",
        "pie":            get_config_value("ml_desc_pie", db) or "",
        "encabezado_ref": get_config_value("ml_desc_encabezado_referencia", db) or "",
        "pie_ref":        get_config_value("ml_desc_pie_referencia", db) or "",
        "keywords":       get_config_value("ml_desc_keywords", db) or "",
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
            "sku": "ECOF-HIDRO-QUADRA", "modelo": "Spa Quadra", "precio": calcular_precio_ml(1_220_000),
            "titulo": "Hidromasaje Rectangular Spa Quadra 117x168 Acrílico EcoFiver",
            "descripcion": (
                "Hidromasaje rectangular modelo Spa Quadra de EcoFiver. "
                "Fabricado en acrílico sanitario reforzado con fibra de vidrio. "
                "Formato rectangular compacto de 1,17 m de ancho × 1,68 m de largo con 0,45 m de profundidad. "
                "Conexión directa a agua fría/caliente, desagüe y electricidad."
                "\n\nEspecificaciones: 1,17 × 1,68 × 0,45 m · 4 jets dirigibles · "
                "Motor 1/2 HP o 3/4 HP · 1 pulsador neumático · 1 regulador de aire."
                + DESC_BASE_HIDRO
            ),
        },
        {
            "sku": "ECOF-HIDRO-RECTA", "modelo": "Spa Recta", "precio": calcular_precio_ml(1_520_000),
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
            "sku": "ECOF-HIDRO-ORBIS", "modelo": "Spa Orbis", "precio": calcular_precio_ml(1_620_000),
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
            "sku": "ECOF-HIDRO-DELTA", "modelo": "Spa Delta", "precio": calcular_precio_ml(1_890_000),
            "titulo": "Mini Spa Hidromasaje Spa Delta 197x142 Acrílico EcoFiver",
            "descripcion": (
                "Mini spa modelo Spa Delta de EcoFiver. El hidromasaje de mayor capacidad de la línea. "
                "Acrílico sanitario reforzado con fibra de vidrio. "
                "Formato esquinero XL de 1,97 m × 1,42 m con 0,52 m de profundidad."
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
    precio_pub = 0.0
    pub_local = None
    if item_id_data:
        pub_local = db.query(PublicacionML).filter(PublicacionML.item_id == item_id_data).first()
        if pub_local:
            descripcion_pub = pub_local.descripcion or ""
            precio_pub = float(pub_local.precio or 0)
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
            precio_pub=precio_pub,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Publicación masiva: 500 variantes de título por modelo
# ═══════════════════════════════════════════════════════════════════════════════

import math as _math
import itertools as _itertools

# Comisión gold_special (Clásica) en MLA (Argentina) — 12 % para la mayoría
# de las categorías (bañeras, jacuzzis, piscinas, módulos, etc.).
# Fuente: ML listing_prices API. Se usa como fallback cuando la API no está
# disponible; cuando hay token activo se consulta el valor real.
ML_COMISION_GOLD_SPECIAL = 0.12


def calcular_precio_ml(precio_contado: float, ganancia_pct: float = 0.05) -> float:
    """
    Precio a publicar en ML para que, descontada la comisión de ML (gold_special ~11%),
    el vendedor nete precio_contado × (1 + ganancia_pct).

    Fórmula: precio_ml = precio_contado × (1 + ganancia_pct) / (1 − comision)
    Se redondea al múltiplo de $1.000 hacia arriba.
    """
    bruto = precio_contado * (1 + ganancia_pct) / (1 - ML_COMISION_GOLD_SPECIAL)
    return _math.ceil(bruto / 1_000) * 1_000


# ── Pools de palabras clave por modelo ────────────────────────────────────────
_POOLS_HIDRO = {
    "Spa Quadra": {
        "tipos":    ["Hidromasaje", "Jacuzzi", "Spa", "Bañera Hidromasaje", "Tina Spa", "Bañera Spa"],
        "formatos": ["Rectangular", "Compacto", "Mini", "Moderno"],
        "dims":     ["117x168", "1.17x1.68m", "117x168 cm"],
        "mats":     ["Acrílico", "Acrílico Sanitario", "PRFV"],
        "marcas":   ["EcoFiver", "Eco Fiver"],
        "extra":    ["4 Jets", "Motor 1/2 HP", "Sin Obra", ""],
        "sku_base": "ECOF-HIDRO-QUADRA",
        "precio_contado": 1_220_000,
        "categoria_ml":   "MLA88471",  # Jacuzzis e Hidromasajes ✓
        "descripcion_base": (
            "Hidromasaje rectangular Spa Quadra de EcoFiver. Acrílico sanitario reforzado PRFV. "
            "Formato rectangular compacto 1,17 × 1,68 × 0,45 m. Ideal para baños con espacio disponible. "
            "4 jets dirigibles, motor 1/2 HP o 3/4 HP, 1 pulsador neumático, 1 regulador de aire. "
            "Estructura autoportante metálica reforzada incluida. Sin obra de albañilería.\n"
            "Colores sin cargo: Blanco, Beige, Negro, Gris.\n"
            "Pago: contado o tarjeta. Retiro: San Telmo (CABA) o Zárate (Bs. As.). Envío cotizar.\n"
            "Fabricación propia EcoFiver — Zárate, Buenos Aires. Garantía estructural incluida."
        ),
        "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.69x1.17x0.40-HIDRO.jpeg"],
    },
    "Spa Recta": {
        "tipos":    ["Hidromasaje", "Jacuzzi", "Spa", "Bañera Hidromasaje", "Tina Spa", "Bañera Spa"],
        "formatos": ["Rectangular", "Doble", "Para 2 Personas", "Amplio"],
        "dims":     ["165x140", "1.65x1.40m", "165 cm"],
        "mats":     ["Acrílico", "Acrílico Sanitario", "PRFV"],
        "marcas":   ["EcoFiver", "Eco Fiver"],
        "extra":    ["6 Jets", "Motor 3/4 HP", "Para 2 Personas", ""],
        "sku_base": "ECOF-HIDRO-RECTA",
        "precio_contado": 1_520_000,
        "categoria_ml":   "MLA88471",  # Jacuzzis e Hidromasajes ✓
        "descripcion_base": (
            "Hidromasaje rectangular Spa Recta de EcoFiver. Acrílico sanitario reforzado PRFV. "
            "Formato rectangular doble 1,65 × 1,40 × 0,45 m. Confort para dos personas. "
            "6 jets dirigibles, motor 3/4 HP, 1 pulsador neumático, 2 reguladores de aire. "
            "Estructura autoportante metálica reforzada incluida. Sin obra de albañilería.\n"
            "Colores sin cargo: Blanco, Beige, Negro, Gris.\n"
            "Pago: contado o tarjeta. Retiro: San Telmo (CABA) o Zárate (Bs. As.). Envío cotizar.\n"
            "Fabricación propia EcoFiver — Zárate, Buenos Aires. Garantía estructural incluida."
        ),
        "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.65x1.40x0.45-HIDRO.jpeg"],
    },
    "Spa Orbis": {
        "tipos":    ["Hidromasaje", "Jacuzzi", "Spa", "Bañera Hidromasaje", "Tina Spa", "Spa Circular"],
        "formatos": ["Circular", "Redondo", "Panorámico", "Circular de Lujo"],
        "dims":     ["176x176", "1.76x1.76m", "176 cm"],
        "mats":     ["Acrílico", "Acrílico Sanitario", "PRFV"],
        "marcas":   ["EcoFiver", "Eco Fiver"],
        "extra":    ["6 a 8 Jets", "Motor 3/4 HP", "Lujo", ""],
        "sku_base": "ECOF-HIDRO-ORBIS",
        "precio_contado": 1_620_000,
        "categoria_ml":   "MLA88471",  # Jacuzzis e Hidromasajes ✓
        "descripcion_base": (
            "Hidromasaje circular panorámico Spa Orbis de EcoFiver. Acrílico sanitario reforzado PRFV. "
            "Diseño circular 1,76 × 1,76 × 0,40 m. Ideal para baños de lujo, terrazas o ambientes spa. "
            "6 a 8 jets dirigibles, motor 3/4 HP, 1 pulsador neumático, 2 reguladores de aire. "
            "Estructura autoportante metálica reforzada incluida. Sin obra de albañilería.\n"
            "Colores sin cargo: Blanco, Beige, Negro, Gris.\n"
            "Pago: contado o tarjeta. Retiro: San Telmo (CABA) o Zárate (Bs. As.). Envío cotizar.\n"
            "Fabricación propia EcoFiver — Zárate, Buenos Aires. Garantía estructural incluida."
        ),
        "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.76x1.76x0.40-HIDRO.jpeg"],
    },
    "Spa Delta": {
        "tipos":    ["Hidromasaje", "Jacuzzi", "Mini Spa", "Bañera Spa", "Tina Spa", "Spa Esquinero"],
        "formatos": ["Esquinero XL", "Extra Grande", "Gran Capacidad", "Amplio"],
        "dims":     ["197x142", "1.97x1.42m", "197 cm"],
        "mats":     ["Acrílico", "Acrílico Sanitario", "PRFV"],
        "marcas":   ["EcoFiver", "Eco Fiver"],
        "extra":    ["8 Jets", "Motor 1 HP", "Mayor Capacidad", ""],
        "sku_base": "ECOF-HIDRO-DELTA",
        "precio_contado": 1_890_000,
        "categoria_ml":   "MLA88471",  # Jacuzzis e Hidromasajes ✓
        "descripcion_base": (
            "Mini spa hidromasaje Spa Delta de EcoFiver. Acrílico sanitario reforzado PRFV. "
            "Mayor capacidad de la línea: 1,97 × 1,42 × 0,52 m. "
            "8 jets dirigibles, motor 1 HP, 1 pulsador neumático, 2 reguladores de aire. "
            "Estructura autoportante metálica reforzada incluida. Sin obra de albañilería.\n"
            "Colores sin cargo: Blanco, Beige, Negro, Gris.\n"
            "Pago: contado o tarjeta. Retiro: San Telmo (CABA) o Zárate (Bs. As.). Envío cotizar.\n"
            "Fabricación propia EcoFiver — Zárate, Buenos Aires. Garantía estructural incluida."
        ),
        "fotos": ["https://ecofiver.site/wp-content/uploads/2025/12/1.97x1.42x0.52-HIDRO.jpeg"],
    },
}


def _generar_titulos_hidro(modelo: str, n: int) -> list[str]:
    """
    Genera hasta N títulos únicos ≤60 chars para un modelo de hidromasaje.
    Combina palabras clave (tipo / formato / dimensiones / material / marca / extra)
    con itertools.product para maximizar la cobertura de términos de búsqueda.
    """
    pool = _POOLS_HIDRO[modelo]
    vistos: set = set()
    titulos: list = []

    # Combinaciones principales (tipo + formato + dims + mat + marca)
    for tipo, fmt, dim, mat, marca in _itertools.product(
        pool["tipos"], pool["formatos"], pool["dims"], pool["mats"], pool["marcas"]
    ):
        t = f"{tipo} {fmt} {dim} {mat} {marca}"[:60].strip()
        if t not in vistos:
            vistos.add(t)
            titulos.append(t)
            if len(titulos) >= n:
                return titulos

    # Variantes con "extra" (ej. "6 Jets", "Sin Obra")
    for tipo, fmt, dim, extra, marca in _itertools.product(
        pool["tipos"], pool["formatos"], pool["dims"], pool["extra"], pool["marcas"]
    ):
        if not extra:
            continue
        t = f"{tipo} {fmt} {dim} {extra} {marca}"[:60].strip()
        if t not in vistos:
            vistos.add(t)
            titulos.append(t)
            if len(titulos) >= n:
                return titulos

    # Variantes invertidas (marca primero)
    for marca, tipo, fmt, dim, mat in _itertools.product(
        pool["marcas"], pool["tipos"], pool["formatos"], pool["dims"], pool["mats"]
    ):
        t = f"{marca} {tipo} {fmt} {dim} {mat}"[:60].strip()
        if t not in vistos:
            vistos.add(t)
            titulos.append(t)
            if len(titulos) >= n:
                return titulos

    # Relleno numerado si hace falta
    base = f"{pool['tipos'][0]} {modelo} EcoFiver"[:50]
    i = len(titulos) + 1
    while len(titulos) < n:
        t = f"{base} V{i:04d}"[:60]
        if t not in vistos:
            vistos.add(t)
            titulos.append(t)
        i += 1

    return titulos[:n]


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN MASIVA GENÉRICA — TODOS LOS PRODUCTOS DEL CATÁLOGO
# ─────────────────────────────────────────────────────────────────────────────

import unicodedata as _unicodedata
import re as _re_gen


def _sku_slug(texto: str) -> str:
    """'Spa Quadra' → 'SPA-QUADRA'  (max 20 chars, ASCII limpio, para SKU)."""
    norm = _unicodedata.normalize("NFD", texto)
    ascii_only = norm.encode("ascii", "ignore").decode()
    slug = _re_gen.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-").upper()
    return slug[:20]


# Pools de palabras clave por categoría del catálogo
_POOLS_GENERICOS: dict = {
    "piscinas": {
        "tipos":   ["Pileta", "Piscina", "Pileta de Fibra", "Piscina de Fibra",
                    "Pileta Fibra de Vidrio", "Piscina Fibra de Vidrio"],
        "extras":  ["Autoinstalable", "Sin Obra", "Con Escalera",
                    "Autoportante", "Resistente UV", ""],
        "mats":    ["Fibra de Vidrio", "PRFV", "Fibra"],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "PISCINA",
    },
    "baneras": {
        "tipos":   ["Bañera", "Tina", "Bañera de Lujo", "Bañera Clásica",
                    "Bañera Autoportante", "Bañera Acrílico"],
        "extras":  ["Autoportante", "Empotrable", "Con Desagüe", ""],
        "mats":    ["Acrílico", "Acrílico Sanitario", "PRFV"],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "BANERA",
    },
    "receptaculos": {
        "tipos":   ["Receptáculo", "Base de Ducha", "Plato de Ducha",
                    "Receptáculo Fibra", "Plato Ducha Fibra"],
        "extras":  ["Antideslizante", "Sin Obra", "Fácil Instalación", ""],
        "mats":    ["Fibra de Vidrio", "PRFV", "Fibra"],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "RECEPTACULO",
    },
    "reposeras": {
        "tipos":   ["Reposera", "Reposera de Pileta", "Silla Reposera",
                    "Reposera Reclinable", "Tumbona"],
        "extras":  ["Para Pileta", "Exterior", "Reclinable", "UV", ""],
        "mats":    ["Fibra de Vidrio", "Fibra", "PRFV"],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "REPOSERA_FIBRA",
    },
    "modulos": {
        # Legacy key — se usa cuando tipo_producto no está definido
        "tipos":   ["Módulo Habitacional", "Casa Prefabricada", "Vivienda Modular",
                    "Casa Modular", "Construcción Modular"],
        "extras":  ["Llave en Mano", "Entrega Rápida", "Sin Obra Civil", ""],
        "mats":    ["Wood Frame", "Steel Frame", "Madera"],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "MODULO",
    },
    # Pools por tipo_producto (tienen prioridad sobre cat_nombre en título genérico)
    "MODULO_HABITACIONAL": {
        "tipos":   ["Módulo Habitacional", "Espacio Habitacional Prefabricado",
                    "Ambiente Prefabricado", "Módulo Prefabricado Wood Frame",
                    "Espacio Prefabricado"],
        "extras":  ["Montaje en el Día", "Llave en Mano", "Sin Obra Civil",
                    "Instalación en el Día", ""],
        "mats":    ["Wood Frame", "Madera", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "MODULO_HABITACIONAL",
    },
    "VIVIENDA_MODULAR": {
        "tipos":   ["Vivienda Modular", "Casa Prefabricada", "Casa Modular",
                    "Vivienda Prefabricada", "Casa Wood Frame",
                    "Construcción en Seco"],
        "extras":  ["Llave en Mano", "Entrega Rápida", "Sin Obra Civil",
                    "Financiada", ""],
        "mats":    ["Wood Frame", "Madera", "Steel Frame", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "VIVIENDA_MODULAR",
    },
    "modulos_deposito": {
        "tipos":   ["Módulo Depósito", "Galpón Modular", "Depósito Prefabricado",
                    "Galpón", "Depósito Modular"],
        "extras":  ["Rápido Montaje", "Autoportante", "Sin Obra", ""],
        "mats":    ["Metal", "Steel Frame", "Chapa Galvanizada", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "MODULO_DEPOSITO",
    },
    "combos": {
        "tipos":   ["Combo", "Pack Completo", "Kit", "Conjunto"],
        "extras":  ["Llave en Mano", "Completo", "Todo Incluido", ""],
        "mats":    ["Fibra de Vidrio", "PRFV", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "COMBO",
    },
    "hidromasajes": {
        "tipos":   ["Hidromasaje", "Jacuzzi", "Spa", "Bañera Hidromasaje",
                    "Tina Spa", "Bañera Spa"],
        "extras":  ["Con Jets", "Motor Incluido", "Sin Obra", ""],
        "mats":    ["Acrílico", "Acrílico Sanitario", "PRFV", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "HIDROMASAJE",
    },
    "accesorios_piscinas": {
        "tipos":   ["Accesorio para Pileta", "Accesorio para Piscina",
                    "Equipo para Pileta", "Accesorio Piscina"],
        "extras":  ["Original", ""],
        "mats":    [],
        "marcas":  ["EcoFiver", ""],
        "tipo_producto": "ACCESORIO_PISCINA",
    },
    "banios_quimicos": {
        "tipos":   ["Baño Químico", "Baño Portátil", "Sanitario Portátil",
                    "Baño Químico Portátil"],
        "extras":  ["Para Obra", "Reforzado", "Con Ventilación", ""],
        "mats":    ["Polipropileno", "HDPE", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "BANIO_QUIMICO",
    },
    "garitas_seguridad": {
        "tipos":   ["Garita de Seguridad", "Casilla de Seguridad",
                    "Garita Prefabricada", "Casilla Prefabricada"],
        "extras":  ["Con Ventana", "Reforzada", "Sin Obra", ""],
        "mats":    ["Steel Frame", "Metal", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "GARITA_SEGURIDAD",
    },
    "cuchas_perros": {
        "tipos":   ["Cucha para Perro", "Casa para Perro", "Cucha",
                    "Refugio Canino"],
        "extras":  ["Con Techo", "Impermeable", "Grande", ""],
        "mats":    ["Madera", "Pino", ""],
        "marcas":  ["EcoFiver", ""],
        "tipo_producto": "CUCHA",
    },
    "depositos_jardin": {
        "tipos":   ["Depósito de Jardín", "Galpón de Jardín",
                    "Depósito Exterior", "Storage Jardín"],
        "extras":  ["Con Puerta", "Resistente UV", ""],
        "mats":    ["Steel Frame", "Metal", "Chapa", ""],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": "DEPOSITO_JARDIN",
    },
    "_default": {
        "tipos":   ["Producto", "Artículo"],
        "extras":  ["Original", ""],
        "mats":    [],
        "marcas":  ["EcoFiver", "Eco Fiver"],
        "tipo_producto": None,
    },
}


def _generar_titulos_generico(nombre_display: str, categoria: str,
                               descripcion: str, n: int,
                               tipo_producto_key: str = "") -> list:
    """
    Genera hasta N títulos únicos ≤60 chars para cualquier producto del catálogo.
    Combina el nombre del producto con el pool de su categoría.
    tipo_producto_key tiene prioridad sobre categoria para buscar el pool.
    """
    pool   = (_POOLS_GENERICOS.get(tipo_producto_key)
              or _POOLS_GENERICOS.get(categoria)
              or _POOLS_GENERICOS["_default"])
    tipos  = pool["tipos"]
    extras = pool["extras"]
    mats   = pool["mats"] or [""]
    marcas = pool["marcas"]

    # Extraer dimensiones del nombre o descripción (ej: "3x6", "120x60 cm")
    raw = nombre_display + " " + descripcion
    dims_found = _re_gen.findall(
        r'\d{1,3}[xX×]\d{1,3}(?:[xX×]\d{1,3})?(?:\s*(?:cm|m|metros?))?', raw
    )
    dims = list(dict.fromkeys(dims_found))[:3]

    nombre_clean = nombre_display.strip()
    vistos: set  = set()
    titulos: list = []

    def _add(partes):
        t = " ".join(p for p in partes if p).strip()[:60]
        if t and t not in vistos:
            vistos.add(t)
            titulos.append(t)
            return len(titulos) >= n
        return False

    # Ronda 1: tipo + nombre + extra + mat + marca
    for tipo, extra, mat, marca in _itertools.product(tipos, extras, mats, marcas):
        if _add([tipo, nombre_clean, extra, mat, marca]):
            return titulos

    # Ronda 2: con dimensiones
    for tipo, dim, extra, marca in _itertools.product(tipos, dims or [""], extras, marcas):
        if _add([tipo, nombre_clean, dim, extra, marca]):
            return titulos

    # Ronda 3: marca adelante
    for marca, tipo, extra in _itertools.product(marcas, tipos, extras):
        if _add([marca, tipo, nombre_clean, extra]):
            return titulos

    # Relleno numerado
    base = f"{tipos[0]} {nombre_clean} EcoFiver"[:50]
    i = len(titulos) + 1
    while len(titulos) < n and i < n * 3:
        t = f"{base} V{i:04d}"[:60]
        if t not in vistos:
            vistos.add(t)
            titulos.append(t)
        i += 1

    return titulos[:n]


def _leer_productos_catalogo() -> list:
    """
    Lee catalogo.json y devuelve lista normalizada de todos los productos
    con precio_contado > 0.  Incluye todas las categorías (legacy + genéricas).
    Maneja correctamente módulos (por m²) y módulos depósito (por tamaño+línea).
    """
    from routers.catalogo import load_catalogo, _get_items

    cat = load_catalogo()
    resultado: list = []

    for cat_nombre, cat_data in cat.items():
        if not isinstance(cat_data, dict):
            continue

        # ── Módulos habitacionales / viviendas modulares ──────────────────────
        # (no usan "modelos", usan "precios" keyed por superficie en m²)
        if cat_nombre == "modulos":
            precios   = cat_data.get("precios", {})
            fotos_cat = cat_data.get("fotos", {})
            tecnologia = cat_data.get("tecnologia", "")
            for sup_str, precio_c in precios.items():
                if not precio_c:
                    continue
                try:
                    precio_f = float(precio_c)
                    sup_m2   = int(float(sup_str))
                except (TypeError, ValueError):
                    continue
                if precio_f <= 0:
                    continue
                es_hab   = sup_m2 <= 18
                tipo     = "MODULO_HABITACIONAL" if es_hab else "VIVIENDA_MODULAR"
                desc_tip = "Módulo Habitacional" if es_hab else "Vivienda Modular"
                fotos    = fotos_cat.get(sup_str, [])
                if not isinstance(fotos, list):
                    fotos = []
                resultado.append({
                    "categoria":      "modulos",
                    "nombre":         f"{sup_str}m2",
                    "nombre_display": f"{desc_tip} {sup_str} m²",
                    "precio_contado": precio_f,
                    "fotos":          fotos,
                    "descripcion":    tecnologia,
                    "sku_base":       f"ECOF-MOD-{sup_str}M2",
                    "tipo_producto":  tipo,
                    "tiene_fotos":    bool(fotos),
                    "n_fotos":        len(fotos),
                })
            continue  # no caer en la rama genérica

        # ── Módulos depósito ──────────────────────────────────────────────────
        # (usan "tamanos" keyed por tamaño → linea → {precio_contado, fotos})
        if cat_nombre == "modulos_deposito":
            tamanos   = cat_data.get("tamanos", {})
            desc_base = cat_data.get("descripcion_base", "")
            desc_prem = cat_data.get("descripcion_premium", "")
            for tam_str, lineas in tamanos.items():
                if not isinstance(lineas, dict):
                    continue
                for linea_nombre, linea_data in lineas.items():
                    if not isinstance(linea_data, dict):
                        continue
                    precio_c = linea_data.get("precio_contado")
                    if not precio_c:
                        continue
                    try:
                        precio_f = float(precio_c)
                    except (TypeError, ValueError):
                        continue
                    if precio_f <= 0:
                        continue
                    fotos = linea_data.get("fotos", [])
                    if not isinstance(fotos, list):
                        fotos = []
                    desc = desc_prem if linea_nombre.upper() == "PREMIUM" else desc_base
                    sku_base = f"ECOF-DEP{tam_str}-{linea_nombre[:3].upper()}"
                    resultado.append({
                        "categoria":      "modulos_deposito",
                        "nombre":         f"{tam_str}m2_{linea_nombre}",
                        "nombre_display": f"Módulo Depósito {tam_str} m² {linea_nombre.title()}",
                        "precio_contado": precio_f,
                        "fotos":          fotos,
                        "descripcion":    desc,
                        "sku_base":       sku_base,
                        "tipo_producto":  "MODULO_DEPOSITO",
                        "tiene_fotos":    bool(fotos),
                        "n_fotos":        len(fotos),
                    })
            continue  # no caer en la rama genérica

        # ── Categorías genéricas (modelos / productos dict) ───────────────────
        items = _get_items(cat_data)
        if not items:
            continue
        pool_meta = _POOLS_GENERICOS.get(cat_nombre, _POOLS_GENERICOS["_default"])

        for prod_nombre, prod_data in items.items():
            if not isinstance(prod_data, dict):
                continue
            precio = prod_data.get("precio_contado")
            if not precio:
                continue
            try:
                precio_f = float(precio)
            except (TypeError, ValueError):
                continue
            if precio_f <= 0:
                continue

            fotos = prod_data.get("fotos") or []
            sku_base = f"ECOF-{_sku_slug(cat_nombre)[:6]}-{_sku_slug(prod_nombre)[:12]}"
            nombre_display = (prod_data.get("nombre")
                              or prod_nombre.replace("_", " ").title())
            resultado.append({
                "categoria":      cat_nombre,
                "nombre":         prod_nombre,
                "nombre_display": nombre_display,
                "precio_contado": precio_f,
                "fotos":          fotos,
                "descripcion":    (prod_data.get("descripcion_corta")
                                   or prod_data.get("descripcion") or ""),
                "sku_base":       sku_base,
                "tipo_producto":  pool_meta.get("tipo_producto") or cat_nombre.upper()[:20],
                "tiene_fotos":    bool(fotos),
                "n_fotos":        len(fotos),
            })

    return resultado


@router.get("/api/ml/borradores/catalogo-disponible")
async def catalogo_disponible(
    db: Session = Depends(get_db), x_api_key=Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Lista productos del catálogo con precio configurado, listos para publicación masiva."""
    _auth(x_api_key, current_user)
    from routers.mercadolibre import calcular_precio_ml as _cpm
    productos = _leer_productos_catalogo()
    por_cat: dict = {}
    for p in productos:
        cat = p["categoria"]
        if cat not in por_cat:
            por_cat[cat] = []
        por_cat[cat].append({
            "nombre":          p["nombre"],
            "nombre_display":  p["nombre_display"],
            "precio_contado":  p["precio_contado"],
            "precio_ml":       _cpm(p["precio_contado"]),
            "tiene_fotos":     p["tiene_fotos"],
            "n_fotos":         p["n_fotos"],
            "sku_base":        p["sku_base"],
            "tipo_producto":   p["tipo_producto"],
        })
    return {"ok": True, "por_categoria": por_cat, "total": len(productos)}


@router.post("/api/ml/borradores/masivos")
async def crear_borradores_masivos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Crea en lote N borradores ML con títulos únicos SEO para CUALQUIER producto.

    Body (todos opcionales):
      prod_sku       sku_base del producto seleccionado → solo ese producto
      from_catalogo  bool — si True usa todos los productos del catálogo con precio
      categorias     lista de categorías a incluir (filtro; default: todas)
      modelos        lista de modelos de hidromasaje (modo legado si from_catalogo=False)
      cantidad       variantes por producto (default: 500, max: 500)
      ganancia_pct   margen sobre precio contado (default: 0.05 = 5 %)

    Retorna: {ok, creados, omitidos, ids (lista de IDs creados), detalle}
    """
    import json as _json_local

    data          = await request.json()
    cantidad      = min(int(data.get("cantidad") or 500), 500)
    ganancia_pct  = float(data.get("ganancia_pct") or 0.05)
    from_catalogo = bool(data.get("from_catalogo", False))
    cat_filter    = data.get("categorias")  # None = todas

    creados_total  = 0
    omitidos_total = 0
    detalle: dict  = {}
    ids_creados:   list = []   # IDs de borradores creados en este lote

    def _procesar(cat_nombre, prod_nombre, nombre_display,
                  precio_contado, fotos, descripcion, sku_base, tipo_producto):
        nonlocal creados_total, omitidos_total
        precio_ml  = calcular_precio_ml(precio_contado, ganancia_pct)
        fotos_json = _json_local.dumps(fotos)

        # Categoría ML pre-asignada (fallback si falla predictor al publicar)
        categoria_ml = ML_CATEGORIAS.get(tipo_producto, "")

        # Generador curado para los 4 modelos de hidromasaje, genérico para el resto
        if cat_nombre == "hidromasajes" and prod_nombre in _POOLS_HIDRO:
            titulos = _generar_titulos_hidro(prod_nombre, cantidad)
        else:
            titulos = _generar_titulos_generico(
                nombre_display, cat_nombre, descripcion, cantidad,
                tipo_producto_key=tipo_producto,
            )

        creados_prod  = 0
        omitidos_prod = 0
        for i, titulo in enumerate(titulos, start=1):
            sku = f"{sku_base}-{i:04d}"
            if db.query(BorradorML).filter(BorradorML.seller_sku == sku).first():
                omitidos_prod += 1
                continue
            b = BorradorML(
                origen             = "masiva",
                titulo             = titulo,
                descripcion        = descripcion,
                producto           = tipo_producto,
                precio             = precio_ml,
                costo              = float(precio_contado),
                seller_sku         = sku,
                modelo_nombre      = nombre_display,
                condicion          = "new",
                listing_type       = "gold_special",
                cuotas_sin_interes = 0,
                cantidad           = 1,
                fotos_json         = fotos_json,
                categoria          = categoria_ml,  # pre-asignada desde ML_CATEGORIAS
                estado             = "borrador",
                created_by_id      = current_user.id,
            )
            db.add(b)
            db.flush()          # para obtener el id generado
            ids_creados.append(b.id)
            creados_prod += 1
            if creados_prod % 100 == 0:
                db.flush()

        key = f"{cat_nombre}/{prod_nombre}" if from_catalogo else prod_nombre
        detalle[key] = {
            "precio_contado":         precio_contado,
            "precio_ml":              precio_ml,
            "ganancia_neta_estimada": round(precio_ml * (1 - ML_COMISION_GOLD_SPECIAL) - precio_contado),
            "creados":                creados_prod,
            "omitidos":               omitidos_prod,
            "tiene_fotos":            bool(fotos),
            "categoria_ml":           categoria_ml,
        }
        creados_total  += creados_prod
        omitidos_total += omitidos_prod

    # ── MODO PRODUCTO ÚNICO: un solo producto del catálogo ────────────────────
    prod_sku = data.get("prod_sku")   # sku_base del producto seleccionado
    if prod_sku:
        productos = _leer_productos_catalogo()
        prod_match = next((p for p in productos if p["sku_base"] == prod_sku), None)
        if not prod_match:
            raise HTTPException(400, f"Producto no encontrado en catálogo: {prod_sku}")
        _procesar(prod_match["categoria"], prod_match["nombre"], prod_match["nombre_display"],
                  prod_match["precio_contado"], prod_match["fotos"], prod_match["descripcion"],
                  prod_match["sku_base"], prod_match["tipo_producto"])

    # ── MODO CATÁLOGO: todos los productos con precio ─────────────────────────
    elif from_catalogo:
        productos = _leer_productos_catalogo()
        if cat_filter:
            productos = [p for p in productos if p["categoria"] in cat_filter]
        if not productos:
            raise HTTPException(400, "No se encontraron productos con precio en el catálogo.")
        for p in productos:
            _procesar(p["categoria"], p["nombre"], p["nombre_display"],
                      p["precio_contado"], p["fotos"], p["descripcion"],
                      p["sku_base"], p["tipo_producto"])

    # ── MODO LEGADO: solo hidromasajes (compatibilidad hacia atrás) ───────────
    else:
        modelos_req     = data.get("modelos") or list(_POOLS_HIDRO.keys())
        modelos_validos = [m for m in modelos_req if m in _POOLS_HIDRO]
        if not modelos_validos:
            raise HTTPException(400, f"Modelos no reconocidos: {modelos_req}. "
                                     f"Válidos: {list(_POOLS_HIDRO.keys())}")
        for modelo in modelos_validos:
            pool = _POOLS_HIDRO[modelo]
            _procesar("hidromasajes", modelo, modelo,
                      pool["precio_contado"], pool["fotos"], pool["descripcion_base"],
                      pool["sku_base"], "HIDROMASAJE")

    db.commit()
    return {
        "ok":               True,
        "creados":          creados_total,
        "omitidos":         omitidos_total,
        "ids":              ids_creados,        # para "publicar todos" sin recargar
        "ganancia_pct_usada": ganancia_pct,
        "comision_ml_usada":  ML_COMISION_GOLD_SPECIAL,
        "detalle":          detalle,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SCORE DE PUBLICACIONES
# ─────────────────────────────────────────────────────────────────────────────

_SIMBOLOS_PROHIBIDOS = set(",|:;!?\"–—_%")

def _calcular_health(titulo: str, n_fotos: int, n_palabras: int) -> dict:
    """Calcula el health score de una publicación (0-100)."""
    score = 0
    checks = []

    # Título (30 pts)
    tlen = len(titulo)
    if 40 <= tlen <= 60:
        score += 20
        checks.append({"ok": True, "label": f"Título {tlen} chars (40-60 ✓)"})
    else:
        checks.append({"ok": False, "label": f"Título {tlen} chars — necesita entre 40 y 60"})

    sin_simb = not any(c in _SIMBOLOS_PROHIBIDOS for c in titulo)
    if sin_simb:
        score += 10
        checks.append({"ok": True, "label": "Sin símbolos prohibidos ✓"})
    else:
        checks.append({"ok": False, "label": "Tiene símbolos prohibidos (,|:;!?\"–—_%)"})

    # Fotos (30 pts)
    if n_fotos >= 8:
        score += 30
        checks.append({"ok": True, "label": f"{n_fotos} fotos (excelente ✓)"})
    elif n_fotos >= 5:
        score += 20
        checks.append({"ok": True, "label": f"{n_fotos} fotos (bueno — ideal 8+)"})
    elif n_fotos >= 3:
        score += 10
        checks.append({"ok": False, "label": f"{n_fotos} fotos (mínimo — subí más fotos)"})
    else:
        checks.append({"ok": False, "label": f"{n_fotos} foto(s) — necesitás al menos 3"})

    # Descripción (40 pts)
    if n_palabras >= 300:
        score += 40
        checks.append({"ok": True, "label": f"Descripción {n_palabras} palabras (excelente ✓)"})
    elif n_palabras >= 200:
        score += 30
        checks.append({"ok": True, "label": f"Descripción {n_palabras} palabras (buena)"})
    elif n_palabras >= 100:
        score += 15
        checks.append({"ok": False, "label": f"Descripción {n_palabras} palabras (ideal 200+)"})
    elif n_palabras > 0:
        score += 5
        checks.append({"ok": False, "label": f"Descripción muy corta ({n_palabras} palabras)"})
    else:
        checks.append({"ok": False, "label": "Sin descripción — impacta el posicionamiento"})

    grade = "A" if score >= 85 else "B" if score >= 65 else "C" if score >= 45 else "D"
    return {"score": score, "grade": grade, "checks": checks}


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SCORE (background job — puede tener 2000+ items)
# ─────────────────────────────────────────────────────────────────────────────

_HEALTH_JOBS: Dict[str, Dict[str, Any]] = {}


async def _health_score_bg(
    job_id: str,
    token: str,
    item_ids: list,
    pub_map: dict,   # item_id → PublicacionML (solo para descripción local)
    bor_map: dict,   # item_id → BorradorML
) -> None:
    job = _HEALTH_JOBS[job_id]
    BATCH = 20
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for i in range(0, len(item_ids), BATCH):
                batch = item_ids[i:i + BATCH]
                try:
                    r = await c.get(
                        f"{ML_BASE}/items",
                        headers=_ml_headers(token),
                        params={"ids": ",".join(batch), "attributes": "id,title,status,pictures,description,permalink"},
                    )
                    if r.status_code != 200:
                        log.warning(f"[HEALTH] batch error {r.status_code}")
                    else:
                        for raw in r.json():
                            body = raw.get("body", raw) if isinstance(raw, dict) and "body" in raw else raw
                            if not body or "id" not in body:
                                continue
                            item_id  = body["id"]
                            titulo   = body.get("title", "")
                            fotos    = body.get("pictures", [])
                            desc_raw = body.get("description") or {}
                            if isinstance(desc_raw, dict):
                                desc_text = desc_raw.get("plain_text") or desc_raw.get("text") or ""
                            else:
                                desc_text = str(desc_raw)
                            n_fotos    = len(fotos) if isinstance(fotos, list) else 0
                            n_palabras = len(desc_text.split()) if desc_text else 0

                            # Enriquecer descripción desde BD local si ML no la devolvió
                            if n_palabras == 0:
                                _pub_l = pub_map.get(item_id)
                                _bor_l = bor_map.get(item_id)
                                _desc_l = (
                                    (getattr(_pub_l, "descripcion", None) if _pub_l else None)
                                    or (getattr(_bor_l, "descripcion", None) if _bor_l else None)
                                    or ""
                                )
                                if _desc_l:
                                    n_palabras = len(_desc_l.split())

                            health = _calcular_health(titulo, n_fotos, n_palabras)
                            _bor_l = bor_map.get(item_id)
                            # permalink viene directo de ML (PublicacionML no tiene esa columna)
                            job["items"].append({
                                "item_id":    item_id,
                                "titulo":     titulo,
                                "estado_ml":  body.get("status", ""),
                                "n_fotos":    n_fotos,
                                "n_palabras": n_palabras,
                                "score":      health["score"],
                                "grade":      health["grade"],
                                "checks":     health["checks"],
                                "permalink":  body.get("permalink", ""),
                                "producto":   getattr(_bor_l, "producto", None) or "",
                                "modelo":     getattr(_bor_l, "modelo_nombre", None) or "",
                            })
                except Exception as _e_batch:
                    log.warning(f"[HEALTH] batch exception: {_e_batch}")
                job["procesados"] = min(i + BATCH, len(item_ids))
                await asyncio.sleep(0.1)

        job["items"].sort(key=lambda x: x["score"])  # peores primero
        job["estado"] = "listo"
        job["total_final"] = len(job["items"])
    except Exception as e:
        log.error(f"[HEALTH] job error: {e}")
        job["estado"] = "error"
        job["error"] = str(e)


@router.post("/api/ml/publicaciones/health-score/iniciar")
async def iniciar_health_score(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lanza el cálculo de health score en background y devuelve un job_id."""
    token = await _get_token(db)

    pubs = db.query(PublicacionML).filter(PublicacionML.item_id.isnot(None)).all()
    bors_pub = db.query(BorradorML).filter(
        BorradorML.item_id.isnot(None),
        BorradorML.estado == "publicada",
    ).all()

    pub_map: dict = {p.item_id: p for p in pubs}
    bor_map: dict = {b.item_id: b for b in bors_pub}
    item_ids = list({*(p.item_id for p in pubs if p.item_id), *(b.item_id for b in bors_pub if b.item_id)})

    if not item_ids:
        # No hay nada que analizar — devolvemos un job "listo" vacío
        job_id = str(uuid.uuid4())[:8]
        _HEALTH_JOBS[job_id] = {"estado": "listo", "procesados": 0, "total": 0, "total_final": 0, "items": []}
        return {"ok": True, "job_id": job_id}

    job_id = str(uuid.uuid4())[:8]
    _HEALTH_JOBS[job_id] = {
        "estado":       "procesando",
        "procesados":   0,
        "total":        len(item_ids),
        "total_final":  0,
        "items":        [],
    }
    background_tasks.add_task(_health_score_bg, job_id, token, item_ids, pub_map, bor_map)
    return {"ok": True, "job_id": job_id, "total": len(item_ids)}


@router.get("/api/ml/publicaciones/health-score/estado/{job_id}")
async def estado_health_score(
    job_id: str,
    current_user: Usuario = Depends(_require_config_access),
):
    """Devuelve el estado del job de health score."""
    job = _HEALTH_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


# ─── Lista rápida de publicaciones (sin llamar a ML API) ─────────────────────

@router.get("/api/ml/publicaciones/lista")
async def lista_publicaciones(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lista liviana de borradores publicados (solo BD local, sin llamar a ML).
    Usada por el modal de actualización de precios."""
    bors = db.query(BorradorML).filter(
        BorradorML.item_id.isnot(None),
        BorradorML.estado == "publicada",
    ).order_by(BorradorML.titulo).all()
    items = [
        {
            "item_id": b.item_id,
            "titulo":  b.titulo or "",
            "precio":  b.precio or 0,
            "score":   0,
            "grade":   "—",
        }
        for b in bors
    ]
    return {"ok": True, "items": items, "total": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZACIÓN DE PUBLICACIONES (individual + masiva)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/ml/publicaciones/{item_id}/detalle")
async def detalle_publicacion_ml(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Detalle completo de una publicación: ML API + BD local. Incluye URLs de fotos."""
    token = await _get_token(db)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ML_BASE}/items/{item_id}", headers=_ml_headers(token))
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"ML error: {r.text[:200]}")
    item = r.json()

    bor = db.query(BorradorML).filter(BorradorML.item_id == item_id).first()
    pub = db.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()

    fotos = [
        {"id": p.get("id", ""), "url": p.get("url") or p.get("secure_url", "")}
        for p in item.get("pictures", [])
        if p.get("id")
    ]
    desc_raw = item.get("description") or {}
    if isinstance(desc_raw, dict):
        desc_text = desc_raw.get("plain_text") or desc_raw.get("text") or ""
    else:
        desc_text = str(desc_raw)
    if not desc_text:
        desc_text = getattr(bor, "descripcion", None) or getattr(pub, "descripcion", None) or ""

    return {
        "ok":          True,
        "item_id":     item_id,
        "titulo":      item.get("title", ""),
        "descripcion": desc_text,
        "estado_ml":   item.get("status", ""),
        "permalink":   item.get("permalink", ""),
        "precio":      item.get("price"),
        "fotos":       fotos,
        "producto":    getattr(bor, "producto", None) or "",
        "modelo":      getattr(bor, "modelo_nombre", None) or "",
    }


@router.post("/api/ml/publicaciones/{item_id}/optimizar")
async def optimizar_publicacion(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Aplica optimizaciones (título, descripción, fotos desde biblioteca) a una publicación ML."""
    token = await _get_token(db)
    data = await request.json()

    titulo           = (data.get("titulo") or "").strip()
    descripcion      = (data.get("descripcion") or "").strip()
    foto_urls        = data.get("foto_urls") or []         # URLs biblioteca → subir a ML
    modo_fotos       = data.get("modo_fotos", "reemplazar")  # reemplazar | agregar_fin
    picture_ids_keep = data.get("picture_ids_keep")        # IDs existentes a conservar (sin re-upload)

    resultados: dict = {}

    async with httpx.AsyncClient(timeout=20) as c:
        # 1) Subir fotos de biblioteca a ML y obtener picture_ids
        nuevos_ids: list = []
        for url in foto_urls:
            try:
                rp = await c.post(
                    f"{ML_BASE}/pictures",
                    headers=_ml_headers(token),
                    json={"source": url},
                )
                if rp.status_code in (200, 201):
                    nuevos_ids.append(rp.json().get("id"))
                else:
                    log.warning(f"[OPT] foto no subida {url}: {rp.status_code}")
            except Exception as _ef:
                log.warning(f"[OPT] error subir foto: {_ef}")

        # 2) Construir lista final de picture_ids para el PUT
        picture_ids: list = []
        if picture_ids_keep is not None and not foto_urls:
            # Usuario removió fotos desde el tab "Actuales" → conservar solo los IDs indicados
            picture_ids = [pid for pid in picture_ids_keep if pid]
        elif nuevos_ids:
            if modo_fotos == "agregar_fin":
                # Traer fotos actuales y agregar al final
                try:
                    rc = await c.get(
                        f"{ML_BASE}/items/{item_id}",
                        headers=_ml_headers(token),
                        params={"attributes": "pictures"},
                    )
                    if rc.status_code == 200:
                        actuales = [p["id"] for p in rc.json().get("pictures", []) if p.get("id")]
                        picture_ids = actuales + nuevos_ids
                except Exception:
                    picture_ids = nuevos_ids
            else:
                picture_ids = nuevos_ids

        # 3) Actualizar ítem (título + fotos)
        payload: dict = {}
        if titulo:
            payload["title"] = titulo
        if picture_ids:
            payload["pictures"] = [{"id": pid} for pid in picture_ids if pid]
        if payload:
            ri = await c.put(
                f"{ML_BASE}/items/{item_id}",
                headers=_ml_headers(token),
                json=payload,
            )
            resultados["item"] = ri.status_code
            if ri.status_code not in (200, 201):
                log.warning(f"[OPT] PUT item {item_id}: {ri.status_code} {ri.text[:200]}")

        # 4) Actualizar descripción (endpoint separado en ML)
        if descripcion:
            rd = await c.put(
                f"{ML_BASE}/items/{item_id}/description",
                headers=_ml_headers(token),
                json={"plain_text": descripcion},
            )
            resultados["descripcion"] = rd.status_code
            if rd.status_code not in (200, 201):
                log.warning(f"[OPT] PUT desc {item_id}: {rd.status_code}")

    # 5) Actualizar BD local
    try:
        bor = db.query(BorradorML).filter(BorradorML.item_id == item_id).first()
        pub = db.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()
        for obj in filter(None, [bor, pub]):
            if titulo:
                obj.titulo = titulo
            if descripcion:
                obj.descripcion = descripcion
        db.commit()
    except Exception as _ed:
        log.warning(f"[OPT] DB update: {_ed}")

    ok = all(v in (200, 201) for v in resultados.values()) if resultados else True
    return {"ok": ok, "resultados": resultados}


# ─── Optimización masiva (background job) ────────────────────────────────────

_BULK_OPT_JOBS: Dict[str, Dict[str, Any]] = {}


async def _bulk_optimizar_bg(
    job_id: str,
    token: str,
    items: list,    # list of {item_id, titulo?, descripcion?, foto_urls?, modo_fotos?}
) -> None:
    job = _BULK_OPT_JOBS[job_id]
    from database.database import SessionLocal
    db_bg = SessionLocal()
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            for i, it in enumerate(items):
                item_id     = it["item_id"]
                titulo      = (it.get("titulo") or "").strip()
                descripcion = (it.get("descripcion") or "").strip()
                foto_urls   = it.get("foto_urls") or []
                modo_fotos  = it.get("modo_fotos", "reemplazar")
                try:
                    # Subir fotos
                    nuevos_ids: list = []
                    for url in foto_urls:
                        try:
                            rp = await c.post(
                                f"{ML_BASE}/pictures",
                                headers=_ml_headers(token),
                                json={"source": url},
                            )
                            if rp.status_code in (200, 201):
                                nuevos_ids.append(rp.json().get("id"))
                        except Exception:
                            pass

                    picture_ids = nuevos_ids
                    if modo_fotos == "agregar_fin" and nuevos_ids:
                        try:
                            rc = await c.get(
                                f"{ML_BASE}/items/{item_id}",
                                headers=_ml_headers(token),
                                params={"attributes": "pictures"},
                            )
                            if rc.status_code == 200:
                                actuales = [p["id"] for p in rc.json().get("pictures", []) if p.get("id")]
                                picture_ids = actuales + nuevos_ids
                        except Exception:
                            pass

                    payload: dict = {}
                    if titulo:
                        payload["title"] = titulo
                    if picture_ids:
                        payload["pictures"] = [{"id": pid} for pid in picture_ids if pid]
                    if payload:
                        ri = await c.put(
                            f"{ML_BASE}/items/{item_id}",
                            headers=_ml_headers(token),
                            json=payload,
                        )
                        if ri.status_code not in (200, 201):
                            job["errores"].append(f"{item_id}: HTTP {ri.status_code}")

                    if descripcion:
                        await c.put(
                            f"{ML_BASE}/items/{item_id}/description",
                            headers=_ml_headers(token),
                            json={"plain_text": descripcion},
                        )

                    # BD local
                    bor = db_bg.query(BorradorML).filter(BorradorML.item_id == item_id).first()
                    pub = db_bg.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()
                    for obj in filter(None, [bor, pub]):
                        if titulo:
                            obj.titulo = titulo
                        if descripcion:
                            obj.descripcion = descripcion

                    job["ok"] = job.get("ok", 0) + 1
                except Exception as e:
                    job["errores"].append(f"{item_id}: {str(e)[:60]}")

                job["procesados"] = i + 1
                if (i + 1) % 20 == 0:
                    try:
                        db_bg.commit()
                    except Exception:
                        pass
                await asyncio.sleep(0.4)

        try:
            db_bg.commit()
        except Exception:
            pass
    finally:
        db_bg.close()

    job["estado"] = "listo"


@router.post("/api/ml/publicaciones/bulk-optimizar/iniciar")
async def iniciar_bulk_optimizar(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lanza optimización masiva en background. Body: {items: [{item_id, titulo?, descripcion?, foto_urls?, modo_fotos?}]}"""
    token = await _get_token(db)
    data = await request.json()
    items = data.get("items", [])
    if not items:
        raise HTTPException(400, "Sin items para optimizar")

    job_id = str(uuid.uuid4())[:8]
    _BULK_OPT_JOBS[job_id] = {
        "estado":     "procesando",
        "procesados": 0,
        "total":      len(items),
        "ok":         0,
        "errores":    [],
    }
    background_tasks.add_task(_bulk_optimizar_bg, job_id, token, items)
    return {"ok": True, "job_id": job_id, "total": len(items)}


@router.get("/api/ml/publicaciones/bulk-optimizar/estado/{job_id}")
async def estado_bulk_optimizar(
    job_id: str,
    current_user: Usuario = Depends(_require_config_access),
):
    job = _BULK_OPT_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


# ─────────────────────────────────────────────────────────────────────────────
# ACTUALIZACIÓN MASIVA DE PRECIOS EN ML
# ─────────────────────────────────────────────────────────────────────────────

_PRICE_JOBS: Dict[str, Dict[str, Any]] = {}


async def _actualizar_precios_bg(
    job_id: str,
    token: str,
    item_ids: list,
    modo: str,
    valor: float,
):
    """
    Worker de fondo para actualización masiva de precios.
    modo='porcentaje' → nuevo = redondear(precio_actual × (1+valor/100), 1000)
    modo='fijo'       → nuevo = valor (mismo para todos)
    """
    from database.database import SessionLocal
    db_bg = SessionLocal()
    job = _PRICE_JOBS[job_id]
    try:
        for item_id in item_ids:
            try:
                if modo == "porcentaje":
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.get(
                            f"{ML_BASE}/items/{item_id}",
                            headers=_ml_headers(token),
                            params={"attributes": "id,price"},
                        )
                    if r.status_code != 200:
                        job["errores"].append(f"{item_id}: no se pudo leer precio ({r.status_code})")
                        job["procesados"] += 1
                        continue
                    precio_actual = float(r.json().get("price", 0) or 0)
                    nuevo_precio  = round(precio_actual * (1 + valor / 100) / 1000) * 1000
                else:  # fijo
                    nuevo_precio = int(valor)

                async with httpx.AsyncClient(timeout=10) as c:
                    r2 = await c.put(
                        f"{ML_BASE}/items/{item_id}",
                        headers=_ml_headers(token),
                        json={"price": nuevo_precio},
                    )
                if r2.status_code in (200, 201, 204):
                    job["ok"] += 1
                    pub = db_bg.query(PublicacionML).filter(PublicacionML.item_id == item_id).first()
                    if pub:
                        pub.precio = nuevo_precio
                        db_bg.commit()
                else:
                    job["errores"].append(f"{item_id}: {r2.text[:80]}")
            except Exception as e:
                job["errores"].append(f"{item_id}: {e}")
            job["procesados"] += 1
            await asyncio.sleep(0.5)
    finally:
        db_bg.close()
        job["status"] = "done"
        log.info(f"[PRECIOS] job {job_id}: {job['ok']}/{job['total']} OK, {len(job['errores'])} errores")


@router.post("/api/ml/publicaciones/actualizar-precios-lote")
async def actualizar_precios_lote(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Actualiza el precio de publicaciones activas en ML en segundo plano.

    Body JSON:
      - item_ids:  lista de item_ids a actualizar (vacío = todas las activas)
      - modo:      'porcentaje' | 'fijo'
      - valor:     porcentaje (+/-) o precio fijo
    """
    data      = await request.json()
    item_ids  = data.get("item_ids", [])
    modo      = data.get("modo", "porcentaje")
    valor     = float(data.get("valor", 0))

    if modo not in ("porcentaje", "fijo"):
        raise HTTPException(400, "modo debe ser 'porcentaje' o 'fijo'")
    if modo == "fijo" and valor <= 0:
        raise HTTPException(400, "El precio fijo debe ser mayor a 0")

    # Si no se especifican IDs, tomar todas las publicaciones activas con item_id
    if not item_ids:
        pubs = db.query(PublicacionML).filter(
            PublicacionML.item_id.isnot(None),
            PublicacionML.estado_ml == "active",
        ).all()
        item_ids = [p.item_id for p in pubs if p.item_id]

    if not item_ids:
        raise HTTPException(400, "No hay publicaciones activas para actualizar")

    token  = await _get_token(db)
    job_id = str(uuid.uuid4())
    _PRICE_JOBS[job_id] = {
        "status": "running", "total": len(item_ids),
        "procesados": 0, "ok": 0, "errores": [],
    }
    background_tasks.add_task(_actualizar_precios_bg, job_id, token, item_ids, modo, valor)
    return {"ok": True, "job_id": job_id, "total": len(item_ids)}


@router.get("/api/ml/publicaciones/actualizar-precios-lote/estado/{job_id}")
async def estado_precios_lote(job_id: str):
    """Consulta el progreso de un job de actualización masiva de precios."""
    job = _PRICE_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


# ─────────────────────────────────────────────────────────────────────────────
# RECÁLCULO DE PRECIOS CORRECTOS (comisión REAL de ML por categoría)
# ─────────────────────────────────────────────────────────────────────────────

_RECALCULAR_JOBS: Dict[str, Dict[str, Any]] = {}


async def _recalcular_precios_bg(
    job_id: str,
    token: str,
    ganancia_pct: float,
    sku_prefixes: Optional[list],
):
    """
    Background: recalcula el precio de cada borrador usando la tasa de comisión
    REAL de ML (consulta listing_prices una vez por grupo de costo/listing_type).
    Para los borradores ya publicados (item_id), actualiza también en ML.
    """
    from database.database import SessionLocal
    from sqlalchemy import or_ as _or

    db_bg = SessionLocal()
    job = _RECALCULAR_JOBS[job_id]
    try:
        # 1. Obtener borradores candidatos
        q = db_bg.query(BorradorML).filter(
            BorradorML.costo.isnot(None),
            BorradorML.costo > 0,
        )
        if sku_prefixes:
            q = q.filter(_or(*[BorradorML.seller_sku.like(f"{p}%") for p in sku_prefixes]))
        borradores = q.all()

        job["total"] = len(borradores)
        if not borradores:
            job["status"] = "done"
            return

        # 2. Agrupar por (listing_type, costo) para minimizar llamadas a ML
        grupos: dict = {}
        for b in borradores:
            lt    = b.listing_type or "gold_special"
            costo = float(b.costo)
            grupos.setdefault((lt, costo), []).append(b)

        # 3. Para cada grupo, consultar la tasa real de comisión a ML
        precio_correcto_map: dict = {}          # (lt, costo) → precio_correcto
        for (lt, costo) in grupos:
            precio_ref = calcular_precio_ml(costo, ganancia_pct)
            fee_rate   = ML_COMISION_GOLD_SPECIAL   # fallback
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(
                        f"{ML_BASE}/sites/MLA/listing_prices",
                        params={"price": precio_ref, "listing_type_id": lt},
                        headers=_ml_headers(token),
                    )
                if r.status_code == 200:
                    fee_data   = r.json()
                    fee_amount: float = 0.0
                    if isinstance(fee_data, list):
                        match = next((x for x in fee_data if x.get("listing_type_id") == lt), None)
                        fee_amount = float((match or fee_data[0]).get("sale_fee_amount", 0))
                    elif isinstance(fee_data, dict):
                        fee_amount = float(fee_data.get("sale_fee_amount", 0))
                    if fee_amount > 0 and precio_ref > 0:
                        fee_rate = fee_amount / precio_ref
            except Exception as fe:
                log.warning(f"[RECALCULAR] fee query error ({lt}, {costo}): {fe}")

            correcto = _math.ceil(costo * (1 + ganancia_pct) / max(1 - fee_rate, 0.01) / 1_000) * 1_000
            precio_correcto_map[(lt, costo)] = correcto
            job["detalle_grupos"].append({
                "listing_type":   lt,
                "costo":          costo,
                "fee_rate_pct":   round(fee_rate * 100, 2),
                "precio_correcto": correcto,
                "n_borradores":   len(grupos[(lt, costo)]),
            })

        # 4. Actualizar cada borrador
        # Un solo cliente HTTP reutilizado para todo el loop — evita 2000 handshakes TCP.
        # Commits en lote cada 50 ítems — evita 2000 flushes individuales a SQLite.
        async with httpx.AsyncClient(timeout=12) as ml_client:
            for (lt, costo), items in grupos.items():
                precio_correcto = precio_correcto_map.get((lt, costo), calcular_precio_ml(costo, ganancia_pct))
                for b in items:
                    old_precio = float(b.precio or 0)
                    diff = abs(old_precio - precio_correcto)

                    if diff < 500:                         # ya está correcto (tolerancia $500)
                        job["ya_ok"] += 1
                        job["procesados"] += 1
                        continue

                    try:
                        if b.item_id:                      # publicado → actualizar en ML también
                            r2 = await ml_client.put(
                                f"{ML_BASE}/items/{b.item_id}",
                                headers=_ml_headers(token),
                                json={"price": precio_correcto},
                            )
                            if r2.status_code in (200, 201, 204):
                                b.precio = precio_correcto
                                job["ok"] += 1
                            else:
                                job["errores"].append(f"{b.item_id}: {r2.text[:80]}")
                            await asyncio.sleep(0.5)       # rate-limit ML + respira el event loop
                        else:                              # solo borrador → update DB
                            b.precio = precio_correcto
                            job["ok"] += 1
                    except Exception as e:
                        job["errores"].append(f"bor{b.id}: {e}")
                    job["procesados"] += 1

                    if job["procesados"] % 50 == 0:        # commit cada 50 — no por cada ítem
                        db_bg.commit()

        db_bg.commit()
    except Exception as e:
        log.error(f"[RECALCULAR] fatal: {e}")
        job["errores"].append(f"Error crítico: {e}")
    finally:
        db_bg.close()
        job["status"] = "done"
        log.info(
            f"[RECALCULAR] job {job_id}: {job['ok']} actualizados, "
            f"{job.get('ya_ok',0)} ya correctos, {len(job['errores'])} errores"
        )


@router.post("/api/ml/publicaciones/recalcular-precios")
async def recalcular_precios(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Recalcula el precio de publicación de borradores usando la comisión REAL de ML.

    Para cada grupo de (listing_type, precio_contado), consulta la API de ML
    una sola vez para obtener la tasa exacta, luego corrige todos los borradores
    de ese grupo. Los ya publicados (item_id) también se actualizan en ML.

    Body JSON:
      - ganancia_pct:  margen deseado, default 0.05 (5 %)
      - sku_prefixes:  lista de prefijos de SKU para filtrar (default: todos)
                       ej: ["ECOF-HIDRO-"] para solo hidromasajes
    """
    data         = await request.json()
    ganancia_pct = float(data.get("ganancia_pct") or 0.05)
    sku_prefixes = data.get("sku_prefixes") or None

    token  = await _get_token(db)
    job_id = str(uuid.uuid4())
    _RECALCULAR_JOBS[job_id] = {
        "status": "running", "total": 0, "procesados": 0,
        "ok": 0, "ya_ok": 0, "errores": [], "detalle_grupos": [],
    }
    background_tasks.add_task(
        _recalcular_precios_bg, job_id, token, ganancia_pct, sku_prefixes
    )
    return {"ok": True, "job_id": job_id}


@router.get("/api/ml/publicaciones/recalcular-precios/estado/{job_id}")
async def recalcular_precios_estado(
    job_id: str,
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Consulta el progreso del job de recálculo de precios."""
    job = _RECALCULAR_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


# VERIFICACIÓN Y RECLASIFICACIÓN DE CATEGORÍAS
# Detecta publicaciones que quedaron en categorías incorrectas (ej. hidromasajes
# publicados como "Viviendas Prefabricadas") y permite reclasificarlas.
# ─────────────────────────────────────────────────────────────────────────────

_VERIFICAR_JOBS:   Dict[str, Dict[str, Any]] = {}
_RECLASIF_JOBS:    Dict[str, Dict[str, Any]] = {}

# Keywords que DEBEN aparecer en el path de categoría ML para considerar correcto el tipo.
# Si ninguna aparece → categoría incorrecta.
_CATEG_OK_KEYWORDS: Dict[str, set] = {
    "HIDROMASAJE": {"jacuzzi", "hidromasaje", "bañera", "spa", "baño"},
    "BANERA":      {"bañera", "hidromasaje", "baño", "spa"},
    "RECEPTACULO": {"ducha", "receptáculo", "receptaculo", "baño", "sanitario"},
    "PISCINA":     {"piscina", "pileta", "natación"},
    "MINIPISCINA": {"piscina", "pileta"},
    "MODULO":      {"módulo", "modulo", "vivienda", "prefabricada", "construcción"},
}


async def _verificar_categorias_bg(
    job_id: str,
    token: str,
    sku_prefixes: Optional[list],
    tipo_producto: Optional[str],
):
    """
    Verifica que cada publicación publicada esté en la categoría correcta de ML.
    Hace multiget en batches de 20; para cada category_id único descarga el path
    y lo compara contra _CATEG_OK_KEYWORDS.
    """
    from database.database import SessionLocal
    from sqlalchemy import or_ as _or

    db_bg = SessionLocal()
    job = _VERIFICAR_JOBS[job_id]
    try:
        q = db_bg.query(BorradorML).filter(
            BorradorML.item_id.isnot(None),
            BorradorML.estado == "publicada",
        )
        if tipo_producto:
            q = q.filter(BorradorML.producto == tipo_producto)
        if sku_prefixes:
            q = q.filter(_or(*[BorradorML.seller_sku.like(f"{p}%") for p in sku_prefixes]))
        borradores = q.all()

        job["total"] = len(borradores)
        if not borradores:
            job["status"] = "done"
            return

        item_map: dict = {b.item_id: b for b in borradores}
        ids_list = list(item_map.keys())
        categ_cache: dict = {}    # category_id → {name, path, ok}
        item_cats:   dict = {}    # item_id → category_id

        async with httpx.AsyncClient(timeout=12) as hc:
            # ── Multiget: obtener category_id de cada ítem ──────────────────
            for i in range(0, len(ids_list), 20):
                batch = ids_list[i:i+20]
                r = await hc.get(
                    f"{ML_BASE}/items",
                    params={"ids": ",".join(batch), "attributes": "id,category_id"},
                    headers=_ml_headers(token),
                )
                if r.status_code == 200:
                    for entry in r.json():
                        if (entry.get("code") or 0) == 200:
                            body   = entry.get("body", {})
                            iid    = body.get("id")
                            cat_id = body.get("category_id")
                            if iid and cat_id:
                                item_cats[iid] = cat_id

                # ── Para categorías nuevas, descargar el path ────────────────
                for iid in batch:
                    cat_id = item_cats.get(iid)
                    if not cat_id or cat_id in categ_cache:
                        continue
                    rc = await hc.get(f"{ML_BASE}/categories/{cat_id}")
                    if rc.status_code == 200:
                        cd = rc.json()
                        path_names = [lv["name"] for lv in cd.get("path_from_root", [])]
                        path_str   = " > ".join(path_names)
                        path_lower = path_str.lower()
                        # Determinar tipo para este item
                        b_tipo  = (item_map.get(iid, BorradorML()).producto or tipo_producto or "HIDROMASAJE").upper()
                        ok_kws  = _CATEG_OK_KEYWORDS.get(b_tipo, set())
                        categ_cache[cat_id] = {
                            "name": cd.get("name", cat_id),
                            "path": path_str,
                            "ok":   any(k in path_lower for k in ok_kws),
                        }

                job["procesados"] = min(i + 20, len(ids_list))
                await asyncio.sleep(0.3)

        # ── Clasificar resultados ────────────────────────────────────────────
        for iid, cat_id in item_cats.items():
            b        = item_map.get(iid)
            if not b:
                continue
            cat_info = categ_cache.get(cat_id, {"name": cat_id, "path": cat_id, "ok": True})
            if not cat_info["ok"]:
                job["incorrectas"].append({
                    "item_id":        iid,
                    "titulo":         (b.titulo or "")[:60],
                    "sku":            b.seller_sku or "",
                    "borrador_id":    b.id,
                    "producto":       b.producto or "",
                    "cat_actual_id":  cat_id,
                    "cat_actual":     cat_info["name"],
                    "cat_path":       cat_info["path"],
                })

        # items sin respuesta de ML
        for iid in ids_list:
            if iid not in item_cats:
                b = item_map[iid]
                job["sin_respuesta"].append({"item_id": iid, "sku": b.seller_sku or ""})

    except Exception as e:
        log.error(f"[VERIFICAR_CAT] fatal: {e}")
        job["error"] = str(e)
    finally:
        db_bg.close()
        job["status"] = "done"
        log.info(f"[VERIFICAR_CAT] job {job_id}: {len(job['incorrectas'])} incorrectas / {job['total']} total")


async def _reclasificar_bg(
    job_id: str,
    token: str,
    items_info: list,   # lista de {item_id, borrador_id, producto}
):
    """
    Reclasifica publicaciones en categorías incorrectas:
    1. Predice la categoría correcta con un título genérico por tipo
    2. PUT /items/{id} con la nueva categoría
    3. Actualiza el campo 'categoria' del borrador en DB
    """
    from database.database import SessionLocal
    from routers.mercadolibre import _ml_categoria_sugerida

    db_bg = SessionLocal()
    job = _RECLASIF_JOBS[job_id]
    job["total"] = len(items_info)

    # Precalcular categoría correcta por tipo (una llamada al predictor por tipo único)
    tipo_cat_cache: dict = {}

    try:
        async with httpx.AsyncClient(timeout=12) as hc:
            for info in items_info:
                item_id    = info["item_id"]
                bid        = info["borrador_id"]
                tipo       = (info.get("producto") or "HIDROMASAJE").upper()

                # Categoría correcta — predecir una vez por tipo
                if tipo not in tipo_cat_cache:
                    fallback_t = _FALLBACK_TITULO_POR_TIPO.get(tipo, "")
                    if fallback_t:
                        # Usar sesión temporal para el predictor
                        _db_tmp = db_bg
                        nueva_cat = await _ml_categoria_sugerida(_db_tmp, fallback_t)
                        tipo_cat_cache[tipo] = nueva_cat
                    else:
                        tipo_cat_cache[tipo] = None

                nueva_cat = tipo_cat_cache.get(tipo)
                if not nueva_cat:
                    job["errores"].append(f"{item_id}: sin categoría predicha para tipo {tipo}")
                    job["procesados"] += 1
                    continue

                # PUT a ML con nueva categoría
                r = await hc.put(
                    f"{ML_BASE}/items/{item_id}",
                    headers=_ml_headers(token),
                    json={"category_id": nueva_cat},
                )
                if r.status_code in (200, 201, 204):
                    job["ok"] += 1
                    # Actualizar borrador en DB
                    b = db_bg.query(BorradorML).filter(BorradorML.id == bid).first()
                    if b:
                        b.categoria = nueva_cat
                else:
                    job["errores"].append(f"{item_id}: HTTP {r.status_code} — {r.text[:80]}")

                job["procesados"] += 1
                await asyncio.sleep(0.4)

        db_bg.commit()

    except Exception as e:
        log.error(f"[RECLASIF] fatal: {e}")
        job["errores"].append(f"Error crítico: {e}")
    finally:
        db_bg.close()
        job["status"] = "done"
        log.info(f"[RECLASIF] job {job_id}: {job['ok']} OK, {len(job['errores'])} errores")


@router.post("/api/ml/publicaciones/verificar-categorias")
async def verificar_categorias(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Inicia verificación de categorías de publicaciones en ML."""
    body         = await request.json()
    sku_prefixes = body.get("sku_prefixes") or None
    tipo         = body.get("tipo_producto") or None
    tok          = await _ml_valid_token(db)
    job_id       = str(uuid.uuid4())
    _VERIFICAR_JOBS[job_id] = {
        "status":       "running",
        "total":        0,
        "procesados":   0,
        "incorrectas":  [],
        "sin_respuesta":[],
        "error":        None,
    }
    background_tasks.add_task(_verificar_categorias_bg, job_id, tok, sku_prefixes, tipo)
    return {"job_id": job_id}


@router.get("/api/ml/publicaciones/verificar-categorias/estado/{job_id}")
async def verificar_categorias_estado(job_id: str):
    job = _VERIFICAR_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


@router.post("/api/ml/publicaciones/reclasificar-categorias")
async def reclasificar_categorias(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Reclasifica en ML las publicaciones con categoría incorrecta."""
    body       = await request.json()
    items_info = body.get("items") or []    # [{item_id, borrador_id, producto}]
    if not items_info:
        raise HTTPException(400, "Sin ítems para reclasificar")
    tok    = await _ml_valid_token(db)
    job_id = str(uuid.uuid4())
    _RECLASIF_JOBS[job_id] = {
        "status": "running", "total": 0, "procesados": 0, "ok": 0, "errores": [],
    }
    background_tasks.add_task(_reclasificar_bg, job_id, tok, items_info)
    return {"job_id": job_id}


@router.get("/api/ml/publicaciones/reclasificar-categorias/estado/{job_id}")
async def reclasificar_categorias_estado(job_id: str):
    job = _RECLASIF_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job
