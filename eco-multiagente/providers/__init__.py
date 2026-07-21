"""
Capa de abstracción de proveedores de IA.
Soporta: Gemini (Google), Claude (Anthropic), OpenAI (GPT).
El proveedor activo se controla con la env var AI_PROVIDER.
"""
from .factory import get_provider, get_active_provider_name

__all__ = ["get_provider", "get_active_provider_name"]
