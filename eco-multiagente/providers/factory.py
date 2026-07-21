"""
Factory de proveedores de IA.
Lee AI_PROVIDER del entorno.
Proveedores soportados: openrouter | grok | gemini | claude | openai
Por defecto: openrouter si hay OPENROUTER_API_KEY, sino grok.
"""
import os
import logging
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

_instances: dict[str, BaseProvider] = {}


def get_active_provider_name() -> str:
    """
    Lee AI_PROVIDER del entorno.
    Auto-detecta por keys disponibles si no está configurado.
    """
    configured = os.getenv("AI_PROVIDER", "").lower()
    if configured:
        return configured
    # Auto-detect: usa el primero que tenga API key
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"):
        return "grok"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "openrouter"  # default (fallará con error claro si no hay key)


def get_provider() -> BaseProvider:
    provider_name = get_active_provider_name()

    if provider_name not in _instances:
        if provider_name == "openrouter":
            from .openrouter_provider import OpenRouterProvider
            model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            _instances[provider_name] = OpenRouterProvider(model=model)

        elif provider_name == "groq":
            from .groq_provider import GroqProvider
            model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            _instances[provider_name] = GroqProvider(model=model)

        elif provider_name == "grok":
            from .grok_provider import GrokProvider
            model = os.getenv("GROK_MODEL", "grok-3-mini")
            _instances[provider_name] = GrokProvider(model=model)

        elif provider_name == "claude":
            from .claude_provider import ClaudeProvider
            model = os.getenv("CLAUDE_MODEL", "claude-haiku-20240307")
            _instances[provider_name] = ClaudeProvider(model=model)

        elif provider_name == "openai":
            from .openai_provider import OpenAIProvider
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            _instances[provider_name] = OpenAIProvider(model=model)

        else:  # gemini (fallback)
            from .gemini_provider import GeminiProvider
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            _instances[provider_name] = GeminiProvider(model=model)

        logger.info(f"[AI Factory] Proveedor activo: {_instances[provider_name].name}")

    return _instances[provider_name]


def reset_provider_cache():
    """Fuerza recrear los providers (se llama al guardar config en el panel)."""
    _instances.clear()
    logger.info("[AI Factory] Cache de providers reseteada")
