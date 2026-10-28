"""
Proveedor OpenRouter — acceso a múltiples modelos (OpenAI, Claude, Llama, Gemini, etc.)
API 100% compatible con OpenAI. URL base: https://openrouter.ai/api/v1
"""
import os
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

# Modelo por defecto. El anterior modelo gratuito (llama-3.3-70b-instruct:free)
# fue dado de baja por OpenRouter (404). Se puede override con OPENROUTER_MODEL.
# "openrouter/free" es el router de modelos gratuitos de OpenRouter.
DEFAULT_MODEL = "openrouter/free"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# IDs que alguna vez se usaron en este sistema y no existen en OpenRouter (404/400).
# Se traducen al equivalente válido para que una variable vieja no deje sin IA.
_MODELOS_INVALIDOS = {
    "openrouter/auto:free": "openrouter/free",
    "anthropic/claude-3-haiku": "anthropic/claude-haiku-4.5",
    "google/gemini-flash-1.5": "google/gemini-2.5-flash",
    "openai/chatgpt-4o-latest": "openai/gpt-4o",
}


def normalizar_modelo(model: str) -> str:
    model = (model or "").strip()
    if model in _MODELOS_INVALIDOS:
        valido = _MODELOS_INVALIDOS[model]
        logger.warning(f"[OpenRouterProvider] Modelo '{model}' no existe en OpenRouter → usando '{valido}'")
        return valido
    return model


def fallback_models() -> list[str]:
    """Modelos a probar como fallback: OPENROUTER_FALLBACK_MODELS (coma-separado) o
    el modelo configurado + un modelo pago económico + el router gratuito."""
    env = os.getenv("OPENROUTER_FALLBACK_MODELS", "")
    if env.strip():
        candidatos = [m.strip() for m in env.split(",") if m.strip()]
    else:
        candidatos = [os.getenv("OPENROUTER_MODEL", ""), "openai/gpt-4o-mini", DEFAULT_MODEL]
    vistos, out = set(), []
    for m in candidatos:
        m = normalizar_modelo(m)
        if m and m not in vistos:
            vistos.add(m)
            out.append(m)
    return out


class OpenRouterProvider(BaseProvider):

    def __init__(self, model: str = None):
        self._model = normalizar_modelo(model or os.getenv("OPENROUTER_MODEL", "") or DEFAULT_MODEL)

    @property
    def name(self) -> str:
        return f"OpenRouter ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY no configurada")

        # Formato OpenAI-compatible
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
                        "X-Title": "EcoFiver",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "max_tokens": 700,
                        "temperature": 0.7,
                    },
                )

            if r.status_code != 200:
                error_data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error", {}).get("message", r.text[:200])
                raise ValueError(f"OpenRouter API error {r.status_code}: {error_msg}")

            data = r.json()
            return data["choices"][0]["message"]["content"]

        except httpx.TimeoutException:
            logger.error("[OpenRouterProvider] Timeout al llamar a OpenRouter")
            raise
        except Exception as e:
            logger.error(f"[OpenRouterProvider] Error: {e}")
            raise
