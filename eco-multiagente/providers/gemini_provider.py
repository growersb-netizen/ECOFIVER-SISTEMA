"""
Proveedor Gemini (Google AI Studio / Google Cloud).
Modelo por defecto: gemini-2.0-flash
"""
import os
import logging
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseProvider):

    def __init__(self, model: str = "gemini-2.0-flash"):
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(
                api_key=os.getenv("GEMINI_API_KEY", "")
            )
        return self._client

    @property
    def name(self) -> str:
        return f"Gemini ({self._model})"

    async def generate(self, system_prompt: str, history: list[dict], message: str) -> str:
        from google.genai import types

        client = self._get_client()

        # Convertir historial común → formato Gemini
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=h["content"])])
            )
        # Agregar mensaje actual
        contents.append(
            types.Content(role="user", parts=[types.Part(text=message)])
        )

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"[GeminiProvider] Error: {e}")
            raise
