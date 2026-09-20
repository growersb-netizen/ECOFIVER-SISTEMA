"""
Proveedor Groq (fast inference — llama, mixtral, etc.)
API compatible con OpenAI — base_url: https://api.groq.com/openai/v1
"""
import os
import asyncio
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen/qwen3.8-27b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Modelos de fallback probados como disponibles para esta cuenta Groq
GROQ_FALLBACK_MODELS = [
    "qwen/qwen3.8-27b",
    "groq/compound-mini",
    "groq/compound",
]


class GroqProvider(BaseProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    @property
    def name(self) -> str:
        return f"Groq ({self._model})"

    async def _call_model(self, model: str, api_key: str, messages: list) -> str:
        """Llama a un modelo específico con retry en 429. Lanza en 404/400."""
        last_err = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.post(
                        f"{GROQ_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": 800,
                            "temperature": 0.75,
                        },
                    )
                if r.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"[Groq/{model}] 429 rate limit, reintento en {wait}s")
                    await asyncio.sleep(wait)
                    last_err = httpx.HTTPStatusError("429", request=r.request, response=r)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_err = e
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                logger.error(f"[Groq/{model}] Error inesperado: {e}")
                raise
        raise last_err

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY no configurada")

        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        # Probar modelo configurado, luego modelos disponibles si falla con 404/400
        models_to_try = [self._model]
        for fb in GROQ_FALLBACK_MODELS:
            if fb not in models_to_try:
                models_to_try.append(fb)

        last_err = None
        for model in models_to_try:
            try:
                result = await self._call_model(model, api_key, messages)
                if model != self._model:
                    logger.info(f"[Groq] Modelo {self._model} no disponible; usando {model}")
                    self._model = model
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (400, 404):
                    logger.warning(f"[Groq] {model} no disponible ({e.response.status_code}), probando siguiente...")
                    last_err = e
                    continue
                raise
            except Exception as e:
                raise

        raise last_err
