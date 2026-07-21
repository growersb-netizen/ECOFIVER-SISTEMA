"""
Proveedor Grok (xAI).
API compatible con OpenAI — base_url: https://api.x.ai/v1
Modelos disponibles: grok-3-mini (económico), grok-3 (potente)
"""
import os
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "grok-3-mini"
GROK_BASE_URL = "https://api.x.ai/v1"


class GrokProvider(BaseProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    @property
    def name(self) -> str:
        return f"Grok ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("GROK_API_KEY", "") or os.getenv("XAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GROK_API_KEY no configurada. "
                "Obtenela en https://console.x.ai/ y configurala en fly secrets."
            )

        # Formato OpenAI-compatible
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"{GROK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "max_tokens": 1200,
                        "temperature": 0.75,
                    },
                )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()

        except httpx.HTTPStatusError as e:
            logger.error(f"[Grok] HTTP error: {e.response.status_code} {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"[Grok] Error inesperado: {e}")
            raise
