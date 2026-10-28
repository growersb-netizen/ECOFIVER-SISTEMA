"""
Factory de proveedores de IA.
Política: todo el consumo de IA pasa por OpenRouter (modelo principal
OPENROUTER_MODEL y respaldos OPENROUTER_FALLBACK_MODELS). Los demás módulos de
providers/ se conservan pero no se usan para tráfico.
"""
import os
import logging
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

_instances: dict[str, BaseProvider] = {}


def get_active_provider_name() -> str:
    """
    Política de EcoFiver: TODO el consumo de IA pasa por OpenRouter.
    AI_PROVIDER (variable o .env del volumen) ya no elige otro proveedor; si
    indica uno distinto se advierte en el log y se usa OpenRouter igual.
    """
    configured = os.getenv("AI_PROVIDER", "").strip().lower()
    if configured and configured != "openrouter":
        global _aviso_emitido
        if not _aviso_emitido:
            logger.warning(f"[AI Factory] AI_PROVIDER={configured} ignorado: todo el tráfico de IA va por OpenRouter")
            _aviso_emitido = True
    return "openrouter"


_aviso_emitido = False


def get_provider() -> BaseProvider:
    if "openrouter" not in _instances:
        from .openrouter_provider import OpenRouterProvider
        model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        _instances["openrouter"] = OpenRouterProvider(model=model)
        logger.info(f"[AI Factory] Proveedor activo: {_instances['openrouter'].name}")
    return _instances["openrouter"]


def modelos_respaldo(modelo_principal: str = "") -> list[str]:
    """
    Modelos de respaldo DENTRO de OpenRouter, en orden. Configurable con
    OPENROUTER_FALLBACK_MODELS="modelo1,modelo2". Se omite el modelo principal.
    """
    raw = os.getenv("OPENROUTER_FALLBACK_MODELS", "openai/gpt-4o-mini,google/gemini-2.5-flash")
    vistos, out = set(), []
    for m in (x.strip() for x in raw.split(",")):
        if m and m != modelo_principal and m not in vistos:
            vistos.add(m)
            out.append(m)
    return out


def reset_provider_cache():
    """Fuerza recrear los providers (se llama al guardar config en el panel)."""
    _instances.clear()
    logger.info("[AI Factory] Cache de providers reseteada")
