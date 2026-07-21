"""
Proveedor Groq (fast inference — llama, mixtral, etc.)
API compatible con OpenAI — base_url: https://api.groq.com/openai/v1
Modelos disponibles: llama-3.3-70b-versatile (recomendado), llama-3.1-8b-instant
"""
import os
import asyncio
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.1-8b-instant"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(BaseProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    @property
    def name(self) -> str:
        return f"Groq ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY no configurada. "
                "Obtenela en https://console.groq.com/ y configurala en fly secrets."
            )

        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

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
                            "model": self._model,
                            "messages": messages,
                            "max_tokens": 800,
                            "temperature": 0.75,
                        },
                    )
                if r.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"[Groq] 429 rate limit, reintento {attempt+1}/3 en {wait}s")
                    await asyncio.sleep(wait)
                    last_err = httpx.HTTPStatusError(f"429", request=r.request, response=r)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()

            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    logger.error(f"[Groq] HTTP error: {e.response.status_code} {e.response.text[:200]}")
                    raise
                last_err = e
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"[Groq] Error inesperado: {e}")
                raise
        raise last_err
