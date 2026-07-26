"""
Proveedor OpenRouter — acceso a múltiples modelos (OpenAI, Claude, Llama, Gemini, etc.)
API 100% compatible con OpenAI. URL base: https://openrouter.ai/api/v1
"""
import os
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

# Modelo por defecto: GRATUITO (no consume créditos). Se puede override con OPENROUTER_MODEL.
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseProvider):

    def __init__(self, model: str = None):
        self._model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

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
