"""
Validación centralizada de la API key del CRM.

Acepta la clave vigente (API_KEY) y, solo durante una rotación, la anterior
(API_KEY_ANTERIOR). Así se puede cambiar la clave en el CRM primero y en los
consumidores después, sin cortar integraciones. Terminada la rotación se borra
API_KEY_ANTERIOR y la clave vieja deja de valer.

Falla cerrado: sin claves configuradas o sin header, nunca valida.
Las variables se leen en cada llamada (no al importar) para que una rotación
aplicada en Railway tome efecto con el reinicio normal del servicio.
"""
import hmac
import os


def _claves(env_vigente: str, env_anterior: str) -> list[str]:
    return [v for v in (os.getenv(env_vigente, "").strip(), os.getenv(env_anterior, "").strip()) if v]


def _valida(key, claves: list[str]) -> bool:
    if not key or not isinstance(key, str):
        return False
    key = key.strip()
    return any(hmac.compare_digest(key, c) for c in claves)


def api_key_valida(key) -> bool:
    """API key general del CRM (header X-Api-Key o Bearer)."""
    return _valida(key, _claves("API_KEY", "API_KEY_ANTERIOR"))


def multiagente_key_valida(key) -> bool:
    """Clave que usa el multiagente para el inbox (CRM_API_KEY en el CRM)."""
    return _valida(key, _claves("CRM_API_KEY", "CRM_API_KEY_ANTERIOR"))
