"""
Proveedor Claude (Anthropic).
Modelo por defecto: claude-haiku-20240307 (más económico)
Alternativa de mayor calidad: claude-3-5-sonnet-20241022
"""
import os
import logging
import httpx
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-20240307"


class ClaudeProvider(BaseProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    @property
    def name(self) -> str:
        return f"Claude ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada")

        # Convertir historial común → formato Anthropic
        messages = []
        for h in history:
            messages.append({
                "role": h["role"],   # "user" | "assistant"
                "content": h["content"],
            })
        # Agregar mensaje actual
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 1024,
                        "system": system_prompt,
                        "messages": messages,
                    },
                )

            if r.status_code != 200:
                error_msg = r.json().get("error", {}).get("message", r.text[:200])
                raise ValueError(f"Anthropic API error {r.status_code}: {error_msg}")

            return r.json()["content"][0]["text"]

        except httpx.TimeoutException:
            logger.error("[ClaudeProvider] Timeout")
            raise
        except Exception as e:
            logger.error(f"[ClaudeProvider] Error: {e}")
            raise
