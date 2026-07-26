"""
Módulo 12 — Configuración del Sistema
Acceso: ADMIN y COORDINADOR_OPERATIVO
"""
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.encryption import encrypt_value, decrypt_value, has_encryption_key
from database.models import ConfiguracionSistema, Usuario
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ─── DEFINICIÓN CENTRAL DE TODAS LAS CLAVES ──────────────────────────────────

CONFIG_DEFS: dict = {
    # ── API Keys de IA ──
    "openrouter_api_key": {
        "label": "⭐ OpenRouter API Key — IA Predeterminada",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "openrouter",
        "placeholder": "sk-or-v1-...",
        "link_obtener": "https://openrouter.ai/keys",
        "link_label": "Obtener en OpenRouter →",
    },
    "grok_api_key": {
        "label": "Grok API Key (xAI)",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "grok",
        "placeholder": "xai-...",
        "link_obtener": "https://console.x.ai/",
        "link_label": "Obtener en console.x.ai →",
    },
    "gemini_api_key": {
        "label": "Gemini API Key (Google) — fallback",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "gemini",
        "placeholder": "AIzaSy...",
        "link_obtener": "https://aistudio.google.com/app/apikey",
        "link_label": "Obtener en Google AI Studio →",
    },
    "claude_api_key": {
        "label": "Claude API Key (Anthropic) — fallback",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "claude",
        "placeholder": "sk-ant-api03-...",
        "link_obtener": "https://console.anthropic.com/settings/keys",
        "link_label": "Obtener en Anthropic Console →",
    },
    "wa_token": {
        "label": "WhatsApp Cloud API — Token de acceso",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "whatsapp",
        "placeholder": "EAABsbCS...",
        "link_obtener": "https://developers.facebook.com/apps/",
        "link_label": "Meta for Developers →",
    },
    "wa_phone_id": {
        "label": "WhatsApp Cloud API — Phone Number ID",
        "categoria": "api_keys",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "123456789012345",
    },
    "wa_webhook_verify_token": {
        "label": "WhatsApp Cloud API — Webhook Verify Token",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": None,
        "placeholder": "mi_token_secreto_webhook",
    },
    "ml_client_id": {
        "label": "MercadoLibre — Client ID",
        "categoria": "api_keys",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "1234567890",
        "link_obtener": "https://developers.mercadolibre.com.ar/es_ar/api-docs-es",
        "link_label": "MercadoLibre Developers →",
    },
    "ml_client_secret": {
        "label": "MercadoLibre — Client Secret",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": None,
        "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    },
    "ml_access_token": {
        "label": "MercadoLibre — Access Token",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": "mercadolibre",
        "placeholder": "APP_USR-...",
    },
    "ml_refresh_token": {
        "label": "MercadoLibre — Refresh Token",
        "categoria": "api_keys",
        "es_secreto": True,
        "test_id": None,
        "placeholder": "TG-...",
    },
    # ── Sistema multiagente ──
    "orquestador_url": {
        "label": "Agentes IA — URL del Sistema",
        "categoria": "api_keys",
        "es_secreto": False,
        "test_id": "orquestador",
        "placeholder": "https://eco-multiagente-polished-sunset-4227.fly.dev",
        "default": "https://eco-multiagente-polished-sunset-4227.fly.dev",
    },
    # ── Precios ──
    "flete_precio_km": {
        "label": "Flete — Precio por km ($)",
        "categoria": "precios",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "3000",
        "default": "3000",
    },
    "flete_miniportante_km": {
        "label": "Flete Miniportante — Precio por km ($)",
        "categoria": "precios",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "2000",
        "default": "2000",
    },
    "descuento_combo_pct": {
        "label": "Descuento Combo módulo + piscina (%)",
        "categoria": "precios",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "25",
        "default": "25",
    },
    # ── Empresa ──
    "empresa_nombre": {
        "label": "Nombre comercial",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "EcoFiver",
        "default": "EcoFiver",
    },
    "empresa_cuit": {
        "label": "CUIT",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "20-12345678-9",
    },
    "empresa_dir_planta": {
        "label": "Dirección planta (Zárate)",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "Zárate, Buenos Aires",
        "default": "Zárate, Buenos Aires",
    },
    "empresa_dir_showroom": {
        "label": "Dirección showroom (CABA)",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "Av. Paseo Colón 1013, CABA",
        "default": "Av. Paseo Colón 1013, CABA",
    },
    "empresa_wa_principal": {
        "label": "WhatsApp principal",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "empresa_instagram": {
        "label": "Instagram handle",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "@ecomodulos",
    },
    "empresa_website": {
        "label": "Website",
        "categoria": "empresa",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "https://www.ecomodulos.com.ar",
    },
    # ── Distribución de Leads ──
    "leads_modo_distribucion": {
        "label": "Modo de distribución de leads",
        "categoria": "leads",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "ROUND_ROBIN / MANUAL / ROTACION_24H",
        "default": "ROUND_ROBIN",
    },
    "leads_rotacion_horas": {
        "label": "Rotación automática — horas sin actividad",
        "categoria": "leads",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "24",
        "default": "24",
    },
    # ── ML Config ──
    "ml_renovacion_automatica": {
        "label": "MercadoLibre — Renovación automática",
        "categoria": "ml_config",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "true / false",
        "default": "false",
    },
    "ml_user_id": {
        "label": "MercadoLibre — User ID (auto)",
        "categoria": "ml_config",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "123456789",
    },
    # ── Notificaciones ──
    "notif_lead_nuevo": {
        "label": "Lead nuevo → WhatsApp destino",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "notif_lead_calificado": {
        "label": "Lead calificado → WhatsApp destino",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "notif_cuota_vencida": {
        "label": "Cuota vencida → WhatsApp destino",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "notif_fabrica_terminada": {
        "label": "Orden fábrica terminada → WhatsApp destino",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "notif_liquidacion_lista": {
        "label": "Liquidación de sueldos lista → WhatsApp destino",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5411XXXXXXXXX",
    },
    "tel_rodrigo": {
        "label": "📊 Resumen diario 08:00 → WhatsApp Rodrigo",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "5491112345678",
    },
    "equipo_codigo_acceso": {
        "label": "🔑 Código de acceso equipo (pedidos de materiales)",
        "categoria": "notificaciones",
        "es_secreto": False,
        "test_id": None,
        "placeholder": "ECO2026",
    },
}


def auto_init_config(db: Session):
    """
    Inicializa en DB las claves que vienen de variables de entorno (fly secrets)
    y los valores por defecto, para que la UI los muestre correctamente.
    Se llama automáticamente cuando el usuario abre Configuración.
    """
    import os
    from database.encryption import encrypt_value

    AUTO_INIT = [
        # (clave_config, env_vars_a_buscar, es_secreto)
        ("openrouter_api_key", ["OPENROUTER_API_KEY"],        True),
        ("grok_api_key",   ["GROK_API_KEY", "XAI_API_KEY"],  True),
        ("gemini_api_key", ["GEMINI_API_KEY"],                True),
        ("claude_api_key", ["ANTHROPIC_API_KEY"],             True),
        ("wa_token",       ["WA_TOKEN"],                      True),
        ("wa_phone_id",    ["WA_PHONE_ID"],                   False),
        ("wa_webhook_verify_token", ["WA_VERIFY_TOKEN"],      True),
    ]
    DEFAULT_INIT = [
        ("orquestador_url", "https://eco-multiagente-polished-sunset-4227.fly.dev", False),
    ]

    changed = False
    for clave, env_vars, es_secreto in AUTO_INIT:
        entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        if entry and entry.valor:
            continue  # ya tiene valor
        for env_var in env_vars:
            val = os.getenv(env_var, "")
            if val:
                stored = encrypt_value(val) if es_secreto else val
                if entry:
                    entry.valor = stored
                    entry.estado = "activa"
                    entry.es_secreto = es_secreto
                else:
                    defn = CONFIG_DEFS.get(clave, {})
                    db.add(ConfiguracionSistema(
                        clave=clave, valor=stored,
                        es_secreto=es_secreto,
                        categoria=defn.get("categoria", "api_keys"),
                        estado="activa",
                    ))
                changed = True
                break

    for clave, default_val, es_secreto in DEFAULT_INIT:
        entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        if not entry:
            defn = CONFIG_DEFS.get(clave, {})
            db.add(ConfiguracionSistema(
                clave=clave, valor=default_val,
                es_secreto=es_secreto,
                categoria=defn.get("categoria", "api_keys"),
                estado="activa",
            ))
            changed = True

    if changed:
        try:
            db.commit()
        except Exception:
            db.rollback()


def _require_config_access(current_user: Usuario = Depends(require_auth)) -> Usuario:
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        raise HTTPException(403, "Acceso restringido a administradores y coordinadores")
    return current_user


def get_config_value(clave: str, db: Session) -> Optional[str]:
    """Lee y desencripta un valor de configuración."""
    entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if not entry or entry.valor is None:
        return CONFIG_DEFS.get(clave, {}).get("default")
    defn = CONFIG_DEFS.get(clave, {})
    return decrypt_value(entry.valor) if defn.get("es_secreto") else entry.valor


def _entry_to_dict(entry: Optional[ConfiguracionSistema], clave: str) -> dict:
    """Serializa una entrada de config para el frontend (sin exponer secretos)."""
    defn = CONFIG_DEFS.get(clave, {})
    tiene_valor = bool(entry and entry.valor)
    updated_at = entry.updated_at.isoformat() if (entry and entry.updated_at) else None
    estado = entry.estado if entry else "sin_configurar"
    return {
        "clave": clave,
        "label": defn.get("label", clave),
        "categoria": defn.get("categoria", "general"),
        "es_secreto": defn.get("es_secreto", False),
        "test_id": defn.get("test_id"),
        "placeholder": defn.get("placeholder", ""),
        "tiene_valor": tiene_valor,
        # Para no-secretos devolvemos el valor para que el form lo muestre
        "valor": (entry.valor if (entry and not defn.get("es_secreto")) else None),
        "updated_at": updated_at,
        "estado": estado,
        # Links de acceso rápido para obtener la API key
        "link_obtener": defn.get("link_obtener"),
        "link_label": defn.get("link_label"),
    }


# ─── RUTAS ────────────────────────────────────────────────────────────────────

@router.get("/configuracion", response_class=HTMLResponse)
async def configuracion_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    roles = get_user_roles(current_user)
    # Auto-inicializar claves de env vars en DB para que la UI las muestre
    auto_init_config(db)
    return templates.TemplateResponse("configuracion.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "encryption_ok": has_encryption_key(),
    })


@router.get("/api/config/ai-status")
async def get_ai_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Estado del proveedor de IA activo en el CRM."""
    from utils.ai_client import get_ai_key_info
    return get_ai_key_info(db)


@router.get("/api/config")
async def get_all_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Devuelve todas las claves con sus metadatos (secretos: solo indica si tienen valor)."""
    entries = {
        e.clave: e
        for e in db.query(ConfiguracionSistema).all()
    }
    result = []
    for clave in CONFIG_DEFS:
        result.append(_entry_to_dict(entries.get(clave), clave))
    return result


@router.put("/api/config/{clave}")
async def update_config(
    clave: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    if clave not in CONFIG_DEFS:
        raise HTTPException(404, f"Clave '{clave}' no reconocida")

    data = await request.json()
    valor = data.get("valor", "")
    defn = CONFIG_DEFS[clave]

    stored = encrypt_value(valor) if (defn["es_secreto"] and valor) else valor

    entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if entry:
        entry.valor = stored
        entry.estado = "activa" if valor else "sin_configurar"
        entry.updated_by_id = current_user.id
    else:
        entry = ConfiguracionSistema(
            clave=clave,
            valor=stored,
            es_secreto=defn["es_secreto"],
            categoria=defn["categoria"],
            estado="activa" if valor else "sin_configurar",
            updated_by_id=current_user.id,
        )
        db.add(entry)

    db.commit()
    return {"ok": True, "clave": clave, "estado": entry.estado}


@router.post("/api/config/{clave}/test")
async def test_connection(
    clave: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Prueba si la credencial guardada funciona haciendo una llamada real a la API."""
    import os
    if clave not in CONFIG_DEFS:
        raise HTTPException(404, "Clave no reconocida")

    defn = CONFIG_DEFS[clave]
    entry = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()

    if entry and entry.valor:
        valor = decrypt_value(entry.valor) if defn["es_secreto"] else entry.valor
    else:
        # Fallback: leer de variables de entorno (keys inyectadas via fly secrets)
        ENV_MAP = {
            "grok_api_key":   ["GROK_API_KEY", "XAI_API_KEY"],
            "gemini_api_key": ["GEMINI_API_KEY"],
            "claude_api_key": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
            "wa_token":       ["WA_TOKEN"],
            "orquestador_url": ["ORQUESTADOR_URL"],
        }
        valor = None
        for env_var in ENV_MAP.get(clave, []):
            val = os.getenv(env_var, "")
            if val:
                valor = val
                break
        # Para campos sin valor ni env var
        if not valor:
            # Para orquestador_url usar el default
            valor = defn.get("default", "")
        if not valor:
            raise HTTPException(400, "Sin valor configurado. Ingresá la clave y guardá primero.")

    if not valor:
        raise HTTPException(400, "No se pudo leer el valor")

    test_id = defn.get("test_id")
    result = await _run_test(test_id, clave, valor, db)

    # Actualizar estado en DB según resultado
    if entry:
        entry.estado = "activa" if result["ok"] else "error"
        db.commit()

    return result


async def _run_test(test_id: Optional[str], clave: str, valor: str, db: Session) -> dict:
    """Ejecuta la prueba de conexión real para cada tipo de credencial."""

    if test_id == "openrouter":
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {valor}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
                        "X-Title": "EcoFiver",
                    },
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
            if r.status_code == 200:
                model_used = r.json().get("model", "openai/gpt-4o-mini")
                return {"ok": True, "msg": f"✓ OpenRouter activo ({model_used})"}
            return {"ok": False, "msg": f"Error {r.status_code}: {r.text[:120]}"}
        except Exception as e:
            return {"ok": False, "msg": f"Sin conexion: {str(e)[:80]}"}

    elif test_id == "grok":
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {valor}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-3-mini",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
            if r.status_code == 200:
                model_used = r.json().get("model", "grok")
                return {"ok": True, "msg": f"✓ Grok API activa ({model_used})"}
            return {"ok": False, "msg": f"Error {r.status_code}: {r.text[:120]}"}
        except Exception as e:
            return {"ok": False, "msg": f"Sin conexión: {str(e)[:80]}"}

    elif test_id == "claude":
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                r = await c.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": valor,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-20240307",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            if r.status_code == 200:
                return {"ok": True, "msg": "✓ Claude API activa"}
            return {"ok": False, "msg": f"Error {r.status_code}: {r.json().get('error', {}).get('message', r.text[:80])}"}
        except Exception as e:
            return {"ok": False, "msg": f"Sin conexión: {str(e)[:80]}"}

    elif test_id == "gemini":
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                r = await c.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={valor}",
                    json={"contents": [{"parts": [{"text": "ping"}]}]},
                )
            if r.status_code == 200:
                return {"ok": True, "msg": "✓ Gemini API activa"}
            return {"ok": False, "msg": f"Error {r.status_code}: {r.text[:80]}"}
        except Exception as e:
            return {"ok": False, "msg": f"Sin conexión: {str(e)[:80]}"}

    elif test_id == "whatsapp":
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://graph.facebook.com/v17.0/me",
                    headers={"Authorization": f"Bearer {valor}"},
                )
            if r.status_code == 200:
                uid = r.json().get("id", "?")
                return {"ok": True, "msg": f"✓ WhatsApp token válido (ID: {uid})"}
            return {"ok": False, "msg": f"Token inválido: {r.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:80]}

    elif test_id == "mercadolibre":
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://api.mercadolibre.com/users/me",
                    headers={"Authorization": f"Bearer {valor}"},
                )
            if r.status_code == 200:
                nick = r.json().get("nickname", "?")
                uid = r.json().get("id", "")
                # Guardar user_id para uso posterior
                if uid:
                    ml_uid = db.query(ConfiguracionSistema).filter(
                        ConfiguracionSistema.clave == "ml_user_id"
                    ).first()
                    if ml_uid:
                        ml_uid.valor = str(uid)
                    else:
                        db.add(ConfiguracionSistema(
                            clave="ml_user_id", valor=str(uid),
                            categoria="ml_config", es_secreto=False
                        ))
                    db.commit()
                return {"ok": True, "msg": f"✓ MercadoLibre conectado como {nick}"}
            return {"ok": False, "msg": f"Token inválido: {r.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": str(e)[:80]}

    elif test_id == "orquestador":
        try:
            url = valor.rstrip("/")
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{url}/health")
            if r.status_code == 200:
                data = r.json()
                agentes = data.get("agentes", "?")
                return {"ok": True, "msg": f"✓ Sistema de agentes activo ({agentes} agentes)"}
            return {"ok": False, "msg": f"Error {r.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"Sin conexión: {str(e)[:80]}"}

    return {"ok": False, "msg": "Test no disponible para esta clave"}
