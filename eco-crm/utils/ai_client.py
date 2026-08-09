"""
Cliente de IA unificado — EcoFiver CRM.
Soporta: OpenRouter · Grok (xAI) · Gemini (Google) · Claude (Anthropic)
Prioridad: openrouter_api_key → grok_api_key → gemini_api_key → claude_api_key

Uso:
    from utils.ai_client import ai_complete, get_ai_key_info

    texto = await ai_complete(db, "Tu prompt aquí")
"""
import os
import httpx
import logging
from typing import Optional
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ─── CONFIGURACIÓN DE PROVEEDORES ─────────────────────────────────────────────

PROVIDERS = {
    "openrouter": {
        "clave_config": "openrouter_api_key",
        "base_url": "https://openrouter.ai/api/v1",
        "model_default": "openai/gpt-4o-mini",
        "model_env": "OPENROUTER_MODEL",   # permite override por entorno
        "chat_path": "/chat/completions",
        "formato": "openai",               # compatible OpenAI
    },
    "grok": {
        "clave_config": "grok_api_key",
        "base_url": "https://api.x.ai/v1",
        "model_default": "grok-3-mini",
        "model_env": "GROK_MODEL",
        "chat_path": "/chat/completions",
        "formato": "openai",          # compatible OpenAI
    },
    "gemini": {
        "clave_config": "gemini_api_key",
        "base_url": "https://generativelanguage.googleapis.com",
        "model_default": "gemini-2.0-flash",
        "model_env": "GEMINI_MODEL",
        "chat_path": "/v1beta/models/{model}:generateContent",
        "formato": "gemini",
    },
    "claude": {
        "clave_config": "claude_api_key",
        "base_url": "https://api.anthropic.com",
        "model_default": "claude-haiku-20240307",
        "model_env": "CLAUDE_MODEL",
        "chat_path": "/v1/messages",
        "formato": "anthropic",
    },
}

# OpenRouter es el predeterminado (mismo motor que los agentes del multiagente)
PROVIDER_PRIORITY = ["openrouter", "grok", "gemini", "claude"]

# Modelo gratuito de fallback cuando OpenRouter devuelve 402 (sin créditos)
OPENROUTER_FREE_FALLBACK = os.getenv("OPENROUTER_FREE_MODEL", "meta-llama/llama-3.2-3b-instruct:free")


def _resolver_modelo(pconf: dict) -> str:
    """Modelo a usar: override por variable de entorno si existe, sino el default."""
    env_var = pconf.get("model_env")
    if env_var:
        val = os.getenv(env_var, "").strip()
        if val:
            return val
    return pconf["model_default"]


def get_config_value(clave: str, db: Session) -> Optional[str]:
    """
    Lee un valor de configuración del CRM (con descifrado si aplica).
    Si no está en DB, intenta leerlo de variables de entorno como fallback.
    """
    from database.models import ConfiguracionSistema
    from database.encryption import decrypt_value

    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if row and row.valor:
        if row.es_secreto:
            try:
                return decrypt_value(row.valor)
            except Exception:
                return row.valor
        return row.valor

    # Fallback: variables de entorno (útil cuando la key viene de flyctl secrets)
    ENV_MAP = {
        "openrouter_api_key": ["OPENROUTER_API_KEY"],
        "grok_api_key":   ["GROK_API_KEY", "XAI_API_KEY"],
        "gemini_api_key": ["GEMINI_API_KEY"],
        "claude_api_key": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    }
    for env_var in ENV_MAP.get(clave, []):
        val = os.getenv(env_var, "")
        if val:
            return val
    return None


def get_active_provider(db: Session) -> Optional[tuple[str, str]]:
    """
    Devuelve (nombre_proveedor, api_key) del primer proveedor con clave configurada.
    Orden: grok → gemini → claude
    """
    for pname in PROVIDER_PRIORITY:
        pconf = PROVIDERS[pname]
        key = get_config_value(pconf["clave_config"], db)
        if key and len(key) > 10:
            return pname, key
    return None, None


def get_ai_key_info(db: Session) -> dict:
    """Devuelve info sobre qué proveedor de IA está activo (para mostrar en UI)."""
    pname, key = get_active_provider(db)
    if not pname:
        return {"proveedor": None, "configurado": False, "modelo": None}
    return {
        "proveedor": pname,
        "configurado": True,
        "modelo": _resolver_modelo(PROVIDERS[pname]),
        "clave_parcial": f"{key[:8]}...{key[-4:]}",
    }


# System prompt base que aplica a todos los agentes y generaciones de texto
SYSTEM_BASE = (
    "Trabajás para EcoFiver, empresa argentina de Zárate, Buenos Aires. "
    "Escribís y hablás SIEMPRE en castellano de Argentina — nunca en español neutro ni latinoamericano genérico. "
    "Usás 'vos', 'acá', 'querés', 'podés', 'tenés' y demás formas rioplatenses de forma natural. "
    "Tu tono es cálido, cercano y profesional: como un experto que le habla de igual a igual al interlocutor, "
    "genera confianza y lo acompaña en la decisión, sin ser informal ni usar lunfardo."
)


async def ai_complete(
    db: Session,
    prompt: str,
    system: str = "",
    max_tokens: int = 1000,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> str:
    """
    Genera texto usando el proveedor de IA activo.
    Retorna el texto generado o lanza Exception si no hay proveedor configurado.
    Aplica automáticamente el system prompt base de EcoFiver (castellano argentino, tono cálido-profesional).
    """
    # Combinar system base con el system específico si lo hay
    if system:
        system = f"{SYSTEM_BASE}\n\n{system}"
    else:
        system = SYSTEM_BASE
    pname, api_key = get_active_provider(db)
    if not pname:
        raise ValueError(
            "No hay proveedor de IA configurado. "
            "Andá a Configuración → API Keys y configurá tu Grok, Gemini o Claude API Key."
        )

    pconf = PROVIDERS[pname]
    modelo = model or _resolver_modelo(pconf)

    try:
        if pconf["formato"] == "openai":
            return await _openai_complete(api_key, pconf["base_url"], modelo, prompt, system, max_tokens, temperature)
        elif pconf["formato"] == "gemini":
            return await _gemini_complete(api_key, modelo, prompt, system, max_tokens)
        elif pconf["formato"] == "anthropic":
            return await _anthropic_complete(api_key, modelo, prompt, system, max_tokens)
        else:
            raise ValueError(f"Formato desconocido: {pconf['formato']}")
    except ValueError as exc:
        # Si OpenRouter devuelve 402 (sin créditos), reintentamos con modelo gratuito
        if pname == "openrouter" and "402" in str(exc) and modelo != OPENROUTER_FREE_FALLBACK:
            log.warning(
                "OpenRouter sin créditos en modelo '%s'. Reintentando con modelo gratuito '%s'.",
                modelo, OPENROUTER_FREE_FALLBACK,
            )
            return await _openai_complete(
                api_key, pconf["base_url"], OPENROUTER_FREE_FALLBACK,
                prompt, system, max_tokens, temperature,
            )
        raise


async def _openai_complete(
    api_key: str, base_url: str, model: str,
    prompt: str, system: str, max_tokens: int, temperature: float
) -> str:
    """Llama a API compatible con OpenAI (Grok, OpenAI, etc.)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
    if not r.is_success:
        raise ValueError(f"OpenRouter HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    # OpenRouter puede devolver error 200 con campo "error" en el body
    if "error" in data:
        raise ValueError(f"OpenRouter error: {data['error']}")
    return data["choices"][0]["message"]["content"].strip()


async def _gemini_complete(
    api_key: str, model: str, prompt: str, system: str, max_tokens: int
) -> str:
    """Llama a Gemini API de Google."""
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, json=payload)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


async def _anthropic_complete(
    api_key: str, model: str, prompt: str, system: str, max_tokens: int
) -> str:
    """Llama a Claude API de Anthropic."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()
