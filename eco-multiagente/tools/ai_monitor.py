"""
Monitoreo de inferencia IA: éxitos/fallos por proveedor y categoría del último error.
No guarda ni expone claves, prompts ni texto de error crudo (solo una categoría).
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

_stats: dict = {
    "ok": 0,
    "fail_total": 0,           # turnos en que fallaron TODOS los proveedores
    "last_ok": None,           # {"provider": str, "ts": float}
    "last_fail_total_ts": None,
    "por_proveedor": {},       # label -> {"ok", "fail", "last_status", "last_categoria", "last_fail_ts"}
}

_STATUS_RE = re.compile(r"\b(4\d\d|5\d\d)\b")


def clasificar_error(exc: Exception) -> tuple[int, str]:
    """Devuelve (status_http_o_0, categoria) sin exponer el texto del error."""
    txt = str(exc).lower()
    status = 0
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None):
        status = int(resp.status_code)
    else:
        m = _STATUS_RE.search(txt)
        if m:
            status = int(m.group(1))

    if "timeout" in type(exc).__name__.lower() or "timeout" in txt or "timed out" in txt:
        cat = "timeout"
    elif "no configurada" in txt or ("api_key" in txt and "missing" in txt):
        cat = "sin_clave"
    elif status in (401, 403) or "unauthorized" in txt or "invalid api key" in txt:
        cat = "clave_invalida"
    elif status == 402 or "credit" in txt or "insufficient" in txt or ("quota" in txt and status != 429):
        cat = "sin_creditos"
    elif status == 404 or "not found" in txt or "not a valid model" in txt or "no endpoints" in txt:
        cat = "modelo_inexistente"
    elif (status == 413 or "too large" in txt
          or ("context" in txt and ("length" in txt or "window" in txt))
          or ("maximum" in txt and "token" in txt)):
        cat = "contexto_excedido"
    elif status == 429 or "rate limit" in txt or "resource_exhausted" in txt:
        cat = "rate_limit"
    elif status >= 500:
        cat = "proveedor_caido"
    elif "vacía" in txt or "empty" in txt:
        cat = "respuesta_vacia"
    else:
        cat = "otro"
    return status, cat


def _slot(provider: str) -> dict:
    return _stats["por_proveedor"].setdefault(
        provider, {"ok": 0, "fail": 0, "last_status": None, "last_categoria": None, "last_fail_ts": None}
    )


def record_ok(provider: str) -> None:
    _stats["ok"] += 1
    _stats["last_ok"] = {"provider": provider, "ts": time.time()}
    _slot(provider)["ok"] += 1


def record_fail(provider: str, exc: Exception) -> str:
    status, cat = clasificar_error(exc)
    s = _slot(provider)
    s["fail"] += 1
    s["last_status"] = status or None
    s["last_categoria"] = cat
    s["last_fail_ts"] = time.time()
    return cat


def record_fail_total(agente: str, intentos: list[str]) -> None:
    _stats["fail_total"] += 1
    _stats["last_fail_total_ts"] = time.time()
    logger.error(f"[IA] {agente}: fallaron TODOS los proveedores → respuesta de espera. Intentos: {intentos}")


def get_stats() -> dict:
    now = time.time()
    last_ok = _stats["last_ok"]
    last_ft = _stats["last_fail_total_ts"]
    proveedores = {}
    for label, s in _stats["por_proveedor"].items():
        proveedores[label] = {
            "ok": s["ok"],
            "fail": s["fail"],
            "last_status": s["last_status"],
            "last_categoria": s["last_categoria"],
            "last_fail_secs_ago": round(now - s["last_fail_ts"]) if s["last_fail_ts"] else None,
        }
    return {
        "respuestas_ok": _stats["ok"],
        "respuestas_de_espera": _stats["fail_total"],
        "last_ok_provider": last_ok["provider"] if last_ok else None,
        "last_ok_secs_ago": round(now - last_ok["ts"]) if last_ok else None,
        "last_espera_secs_ago": round(now - last_ft) if last_ft else None,
        "por_proveedor": proveedores,
    }
