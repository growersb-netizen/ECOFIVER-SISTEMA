"""
Proveedor OpenAI (GPT).
Modelo por defecto: gpt-4o-mini (más económico, excelente calidad)
Alternativa: gpt-4o
"""
import os
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    @property
    def name(self) -> str:
        return f"OpenAI ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada")

        # Convertir historial común → formato OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = h["role"]   # "user" | "assistant"
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                )

            if r.status_code != 200:
                error_msg = r.json().get("error", {}).get("message", r.text[:200])
                raise ValueError(f"OpenAI API error {r.status_code}: {error_msg}")

            return r.json()["choices"][0]["message"]["content"]

        except httpx.TimeoutException:
            logger.error("[OpenAIProvider] Timeout")
            raise
        except Exception as e:
            logger.error(f"[OpenAIProvider] Error: {e}")
            raise
