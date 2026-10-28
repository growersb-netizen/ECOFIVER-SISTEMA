"""
Seguridad transversal del multiagente — Etapa 0.

- require_api_key: autenticación obligatoria para endpoints internos/administrativos.
- Firma de webhooks de Meta (X-Hub-Signature-256) con modo configurable.
- Deduplicación de mensajes entrantes de WhatsApp por wamid.

Variables de entorno:
  MULTIAGENTE_API_KEY          clave para integraciones (CRM, scripts). Opcional: si no
                               está, se acepta la ADMIN_PASSWORD como clave.
  WA_APP_SECRET                App Secret de la app de Meta que entrega el webhook de WA.
                               Si no está, se usa META_APP_SECRET.
  WA_WEBHOOK_SIGNATURE_MODE    off | log | enforce   (default: log)
      off      → no verifica (comportamiento anterior).
      log      → verifica y registra; NO rechaza mensajes de clientes, pero un webhook
                 sin firma válida nunca obtiene privilegios del canal admin.
      enforce  → rechaza con 403 todo webhook sin firma válida.
"""
import hashlib
import hmac
import logging
import os
import time
from collections import OrderedDict

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


# ── Autenticación por API key ────────────────────────────────────────────────

def _valid_keys() -> list[str]:
    keys = []
    k = os.getenv("MULTIAGENTE_API_KEY", "").strip()
    if k:
        keys.append(k)
    pw = os.getenv("ADMIN_PASSWORD", "").strip()
    if pw:
        keys.append(pw)
    return keys


def _extract_key(request: Request) -> str:
    h = request.headers
    key = h.get("X-Api-Key") or h.get("X-Panel-Password") or ""
    if not key:
        auth = h.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
    return key.strip()


def api_key_valid(request: Request) -> bool:
    key = _extract_key(request)
    if not key:
        return False
    return any(hmac.compare_digest(key, k) for k in _valid_keys())


def require_api_key(request: Request) -> None:
    """Dependencia/guard: 503 si no hay claves configuradas, 401 si la clave no es válida."""
    if not _valid_keys():
        logger.error("[Security] Sin MULTIAGENTE_API_KEY ni ADMIN_PASSWORD — endpoint protegido deshabilitado")
        raise HTTPException(status_code=503, detail="Autenticación no configurada en el servidor")
    if not api_key_valid(request):
        raise HTTPException(status_code=401, detail="No autorizado")


# ── Firma de webhooks de Meta ────────────────────────────────────────────────

def signature_mode() -> str:
    mode = os.getenv("WA_WEBHOOK_SIGNATURE_MODE", "log").strip().lower()
    return mode if mode in ("off", "log", "enforce") else "log"


def _app_secret() -> str:
    return (os.getenv("WA_APP_SECRET") or os.getenv("META_APP_SECRET") or "").strip()


def verify_meta_signature(body: bytes, signature_header: str) -> str:
    """
    Retorna: "valid" | "invalid" | "missing" (sin header) | "no_secret" (sin secreto configurado).
    """
    secret = _app_secret()
    if not secret:
        return "no_secret"
    if not signature_header or not signature_header.startswith("sha256="):
        return "missing"
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return "valid" if hmac.compare_digest(expected, signature_header) else "invalid"


# Contadores en memoria para observabilidad (/health/seguridad)
_sig_stats = {"valid": 0, "invalid": 0, "missing": 0, "no_secret": 0, "rejected": 0}


def record_signature_result(result: str, rejected: bool) -> None:
    _sig_stats[result] = _sig_stats.get(result, 0) + 1
    if rejected:
        _sig_stats["rejected"] += 1


def signature_stats() -> dict:
    return {"mode": signature_mode(), "secret_configured": bool(_app_secret()), **_sig_stats}


# ── Deduplicación de mensajes entrantes ──────────────────────────────────────

class _TTLSet:
    """Conjunto acotado con vencimiento; suficiente para una réplica."""

    def __init__(self, max_items: int = 5000, ttl_seconds: int = 24 * 3600):
        self._data: "OrderedDict[str, float]" = OrderedDict()
        self._max = max_items
        self._ttl = ttl_seconds

    def seen(self, key: str) -> bool:
        """True si ya estaba; si no, lo registra y retorna False."""
        now = time.time()
        while self._data:
            k, ts = next(iter(self._data.items()))
            if now - ts > self._ttl or len(self._data) > self._max:
                self._data.popitem(last=False)
            else:
                break
        if key in self._data:
            return True
        self._data[key] = now
        return False

    def clear(self) -> None:
        self._data.clear()


_wamid_seen = _TTLSet()
_dedup_stats = {"duplicados_descartados": 0}


def is_duplicate_wamid(wamid: str | None) -> bool:
    if not wamid:
        return False
    dup = _wamid_seen.seen(wamid)
    if dup:
        _dedup_stats["duplicados_descartados"] += 1
    return dup


def dedup_stats() -> dict:
    return dict(_dedup_stats)
