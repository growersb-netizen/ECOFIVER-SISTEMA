"""
Control empresarial de agentes (Fase 2), lado multiagente.

Lee del CRM (GET /api/motor/control) el estado administrativo de cada agente y
si puede iniciar salientes comerciales ahora (horario L-S 09-21 ART o guardia).
Caché de 30 s.

Criterios ante falta de datos del CRM:
  - Entrante (clientes escriben): se atiende igual (24/7). Un agente se
    considera ACTIVO si no hay dato.
  - Saliente comercial: NO se envía sin confirmación (falla cerrado).
  - Tareas del motor: sin dato no se filtra (el CRM igual controla el reclamo).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from tools import crm_client

logger = logging.getLogger(__name__)

AGENTES_CLIENTE_ORDEN = ["valentina", "camila", "nicolas", "luciano", "mateo", "sebastian"]
TTL_S = 30
VIGENCIA_MAX_S = 300            # un dato viejo sirve para entrante, nunca para saliente

_cache: dict = {"datos": None, "ts": 0.0}


async def _leer() -> Optional[dict]:
    ahora = time.monotonic()
    if _cache["datos"] is not None and ahora - _cache["ts"] < TTL_S:
        return _cache["datos"]
    try:
        async with httpx.AsyncClient(timeout=crm_client.TIMEOUT) as c:
            r = await c.get(f"{crm_client.CRM_BASE_URL}/api/motor/control", headers=crm_client.HEADERS)
        r.raise_for_status()
        _cache.update(datos=r.json(), ts=ahora)
        return _cache["datos"]
    except Exception as e:
        logger.warning(f"[Control] No se pudo leer el estado de agentes: {e}")
        if _cache["datos"] is not None and ahora - _cache["ts"] < VIGENCIA_MAX_S:
            return _cache["datos"]
        return None


def _reset_para_tests() -> None:
    _cache.update(datos=None, ts=0.0)


async def estado(agente: str) -> str:
    d = await _leer()
    return (d or {}).get("estados", {}).get(agente, "ACTIVO")


async def agentes_para_tareas() -> Optional[list[str]]:
    d = await _leer()
    if d is None:
        return None
    return [a for a, e in d.get("estados", {}).items() if e == "ACTIVO"]


async def puede_iniciar_saliente(agente: str) -> tuple[bool, str]:
    d = await _leer()
    if d is None:
        return False, "sin confirmación del CRM"
    if d.get("salientes_permitidos", {}).get(agente):
        return True, ""
    if d.get("estados", {}).get(agente, "ACTIVO") != "ACTIVO":
        return False, f"agente {d['estados'][agente].lower()}"
    return False, "fuera del horario autorizado"


async def agente_para_cliente(asignado: str) -> Optional[str]:
    """Agente que atiende a un cliente ahora. None si no hay ninguno activo."""
    d = await _leer()
    if d is None:
        return asignado                                  # entrante 24/7: sin dato, se atiende
    est = d.get("estados", {})
    for candidato in [asignado, "valentina"]:
        if est.get(candidato, "ACTIVO") == "ACTIVO":
            return candidato
    return None
