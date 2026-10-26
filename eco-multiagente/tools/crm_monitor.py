"""
Monitoreo de conectividad CRM: contadores de exito/fallo y health loop periodico.
No bloquea el arranque ni expone credenciales.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_stats: dict = {
    "calls_ok":          0,
    "calls_fail":        0,
    "last_fail":         None,   # {"fn": str, "status": int, "error": str, "ts": float}
    "last_ok_ts":        None,
    "health_ok":         None,   # None=sin verificar, True/False=ultimo resultado
    "last_health_ts":    None,
    "last_wa_event_ts":  None,
}


def record_ok(fn_name: str = "") -> None:
    _stats["calls_ok"] += 1
    _stats["last_ok_ts"] = time.time()


def record_fail(fn_name: str = "", status: int = 0, error: str = "") -> None:
    _stats["calls_fail"] += 1
    _stats["last_fail"] = {
        "fn":     fn_name,
        "status": status,
        "error":  error[:200],
        "ts":     time.time(),
    }
    logger.error(f"[CRM] fallo: fn={fn_name} status={status} error={error[:120]}")


def record_wa_event() -> None:
    _stats["last_wa_event_ts"] = time.time()


def get_stats() -> dict:
    now = time.time()
    last_wa = _stats["last_wa_event_ts"]
    last_ok = _stats["last_ok_ts"]
    last_fail_info = _stats["last_fail"]
    return {
        "calls_ok":               _stats["calls_ok"],
        "calls_fail":             _stats["calls_fail"],
        "last_fail":              last_fail_info,
        "last_ok_secs_ago":       round(now - last_ok)    if last_ok  else None,
        "last_wa_event_secs_ago": round(now - last_wa)    if last_wa  else None,
        "health_ok":              _stats["health_ok"],
        "last_health_ts":         _stats["last_health_ts"],
        "status": "ok" if _stats["calls_fail"] == 0 else "degradado",
    }


async def _crm_health_loop() -> None:
    """Ping periodico al CRM cada 15 min para detectar fallos de auth."""
    import os
    import httpx

    await asyncio.sleep(45)   # tiempo para que el startup complete

    base_url = os.getenv("CRM_BASE_URL", "https://eco-crm-production.up.railway.app")
    api_key  = os.getenv("CRM_API_KEY", "")

    while True:
        if not api_key:
            logger.warning("[CRM_HEALTH] CRM_API_KEY no configurada — ping omitido")
            await asyncio.sleep(900)
            continue
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(
                    f"{base_url}/api/leads/agent",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params={"limit": 1},
                )
            if r.status_code in (200, 404):
                _stats["health_ok"]      = True
                _stats["last_health_ts"] = time.time()
                logger.debug("[CRM_HEALTH] ping ok")
            else:
                _stats["health_ok"]      = False
                _stats["last_health_ts"] = time.time()
                logger.error(f"[CRM_HEALTH] Auth falla: HTTP {r.status_code}")
                record_fail("health_ping", r.status_code, r.text[:100])
        except Exception as exc:
            _stats["health_ok"]      = False
            _stats["last_health_ts"] = time.time()
            logger.error(f"[CRM_HEALTH] Ping fallido: {exc}")
            record_fail("health_ping", 0, str(exc))

        await asyncio.sleep(900)  # 15 min


def start_health_loop() -> None:
    asyncio.create_task(_crm_health_loop())
