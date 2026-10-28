"""
Métricas de uso de IA — Etapa 1.

Registra cada llamada a un proveedor de IA: agente, proceso (conversación, tarea
programada…), proveedor efectivo, modelo, éxito/error, si fue respaldo
(fallback), latencia, tokens y costo estimado. Expone agregados del día para
GET /health/ia y avisa por Telegram cuando el costo diario se acerca al límite.

No guarda prompts ni respuestas (solo números y mensajes de error truncados).

Costo: si el proveedor devuelve el costo real (OpenRouter `usage.cost`) se usa
ese; si devuelve tokens, se multiplica por la tabla de precios; si no, los tokens
se estiman por caracteres (≈4 caracteres por token) y queda marcado como estimado.
Tabla de precios en USD por millón de tokens, ampliable con AI_PRICES_JSON:
  AI_PRICES_JSON='{"openai/gpt-4o-mini": [0.15, 0.60]}'
Los precios por defecto son referencia y deben validarse contra la consola del proveedor.

Variables:
  AI_DAILY_COST_LIMIT_USD   límite diario para alertas (default 5). No bloquea llamadas.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=-3))

# Proceso que origina la llamada (lo setean el router y el scheduler)
proceso_actual: contextvars.ContextVar[str] = contextvars.ContextVar("ai_proceso", default="otro")
# Uso informado por el proveedor en la última llamada de este contexto
_uso_ultima_llamada: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ai_uso", default=None)

_PRECIOS_DEFAULT: dict[str, tuple[float, float]] = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini": (0.15, 0.60),
}


def _precios() -> dict[str, tuple[float, float]]:
    p = dict(_PRECIOS_DEFAULT)
    raw = os.getenv("AI_PRICES_JSON", "").strip()
    if raw:
        try:
            for k, v in json.loads(raw).items():
                p[k] = (float(v[0]), float(v[1]))
        except Exception as e:
            logger.warning(f"[AIMetrics] AI_PRICES_JSON inválido: {e}")
    return p


def informar_uso(usage: dict | None) -> None:
    """Lo llaman los proveedores con el bloque `usage` de la respuesta (formato OpenAI/OpenRouter)."""
    _uso_ultima_llamada.set(usage if isinstance(usage, dict) else None)


def _limpiar_uso() -> None:
    _uso_ultima_llamada.set(None)


def _modelo_de(provider) -> str:
    return str(getattr(provider, "_model", None) or getattr(provider, "model", None) or "")


def _proveedor_de(provider) -> str:
    return type(provider).__name__.replace("Provider", "").lower() or "desconocido"


def _hoy() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


class _Estado:
    def __init__(self):
        self.reset(_hoy())
        self.errores: deque = deque(maxlen=20)
        self._ultimo_guardado = 0.0
        self._alertas_enviadas: set[str] = set()

    def reset(self, dia: str):
        self.dia = dia
        self.totales = {"llamadas": 0, "ok": 0, "errores": 0, "fallback_ok": 0, "sin_respuesta": 0,
                        "tokens_in": 0, "tokens_out": 0, "costo_usd": 0.0, "llamadas_sin_precio": 0,
                        "tokens_estimados": 0}
        self.por_agente: dict[str, dict] = {}
        self.por_proceso: dict[str, dict] = {}
        self.por_modelo: dict[str, dict] = {}
        self.ultimo_proveedor_ok: dict | None = None
        self._alertas_enviadas = set()


_estado = _Estado()


def _acum(d: dict, key: str, costo: float, ok: bool, tin: int, tout: int):
    a = d.setdefault(key, {"llamadas": 0, "errores": 0, "costo_usd": 0.0, "tokens_in": 0, "tokens_out": 0})
    a["llamadas"] += 1
    a["errores"] += 0 if ok else 1
    a["costo_usd"] = round(a["costo_usd"] + costo, 6)
    a["tokens_in"] += tin
    a["tokens_out"] += tout


def registrar_llamada(*, agente: str, provider, ok: bool, fallback: bool, latencia_s: float,
                      chars_in: int = 0, chars_out: int = 0, error: str = "") -> dict:
    """Registra una llamada a proveedor. Retorna el registro (para tests)."""
    if _estado.dia != _hoy():
        _estado.reset(_hoy())

    modelo = _modelo_de(provider)
    proveedor = _proveedor_de(provider)
    uso = _uso_ultima_llamada.get() or {}
    _limpiar_uso()

    estimado = False
    tin = int(uso.get("prompt_tokens") or 0)
    tout = int(uso.get("completion_tokens") or 0)
    if ok and not (tin or tout):
        tin, tout, estimado = max(chars_in // 4, 0), max(chars_out // 4, 0), True

    costo: float | None
    if uso.get("cost") is not None:
        try:
            costo = float(uso["cost"])
        except (TypeError, ValueError):
            costo = None
    elif modelo.endswith(":free"):
        costo = 0.0
    elif modelo in _precios():
        pin, pout = _precios()[modelo]
        costo = (tin * pin + tout * pout) / 1_000_000
    else:
        costo = None

    t = _estado.totales
    t["llamadas"] += 1
    if ok:
        t["ok"] += 1
        if fallback:
            t["fallback_ok"] += 1
        _estado.ultimo_proveedor_ok = {"proveedor": proveedor, "modelo": modelo, "agente": agente,
                                       "fallback": fallback, "hora": datetime.now(_TZ).strftime("%H:%M:%S")}
    else:
        t["errores"] += 1
        _estado.errores.append({"hora": datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S"), "agente": agente,
                                "proveedor": proveedor, "modelo": modelo, "error": (error or "")[:200]})
    t["tokens_in"] += tin
    t["tokens_out"] += tout
    if estimado:
        t["tokens_estimados"] += tin + tout
    if costo is None:
        if ok:
            t["llamadas_sin_precio"] += 1
        costo_n = 0.0
    else:
        costo_n = costo
        t["costo_usd"] = round(t["costo_usd"] + costo, 6)

    proceso = proceso_actual.get()
    _acum(_estado.por_agente, agente or "?", costo_n, ok, tin, tout)
    _acum(_estado.por_proceso, proceso, costo_n, ok, tin, tout)
    _acum(_estado.por_modelo, f"{proveedor}:{modelo}", costo_n, ok, tin, tout)

    _guardar_si_corresponde()
    _chequear_limite()
    return {"agente": agente, "proceso": proceso, "proveedor": proveedor, "modelo": modelo, "ok": ok,
            "fallback": fallback, "tokens_in": tin, "tokens_out": tout, "costo_usd": costo,
            "tokens_estimados": estimado, "latencia_s": round(latencia_s, 3)}


def registrar_sin_respuesta(agente: str) -> None:
    """Todos los proveedores fallaron y el cliente recibió el mensaje genérico."""
    if _estado.dia != _hoy():
        _estado.reset(_hoy())
    _estado.totales["sin_respuesta"] += 1
    _estado.errores.append({"hora": datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S"), "agente": agente,
                            "proveedor": "-", "modelo": "-", "error": "Todos los proveedores fallaron: respuesta genérica"})
    _alertar(f"sin_respuesta:{agente}",
             f"⚠️ IA sin respuesta: todos los proveedores fallaron para {agente}. El cliente recibió el mensaje genérico. Revisá /health/ia.")


async def generar_medido(*, agente: str, provider, fallback: bool, system_prompt: str,
                         history: list[dict], message: str) -> str:
    """Envuelve provider.generate() midiendo la llamada. Propaga el resultado o la excepción."""
    _limpiar_uso()
    t0 = time.monotonic()
    chars_in = len(system_prompt or "") + len(message or "") + sum(len(h.get("content", "")) for h in history or [])
    try:
        reply = await provider.generate(system_prompt=system_prompt, history=history, message=message)
    except Exception as e:
        _seguro(registrar_llamada, agente=agente, provider=provider, ok=False, fallback=fallback,
                latencia_s=time.monotonic() - t0, chars_in=chars_in, error=str(e))
        raise
    _seguro(registrar_llamada, agente=agente, provider=provider, ok=bool(reply), fallback=fallback,
            latencia_s=time.monotonic() - t0, chars_in=chars_in, chars_out=len(reply or ""),
            error="" if reply else "respuesta vacía")
    return reply


def _seguro(fn, **kw):
    """La medición nunca debe romper la respuesta al cliente."""
    try:
        fn(**kw)
    except Exception as e:
        logger.warning(f"[AIMetrics] no se pudo registrar: {e}")


# ── Límite diario ────────────────────────────────────────────────────────────

def limite_diario() -> float:
    try:
        return float(os.getenv("AI_DAILY_COST_LIMIT_USD", "5"))
    except ValueError:
        return 5.0


def _chequear_limite() -> None:
    lim = limite_diario()
    if lim <= 0:
        return
    costo = _estado.totales["costo_usd"]
    for umbral, etiqueta in ((1.0, "100"), (0.8, "80")):
        if costo >= lim * umbral:
            _alertar(f"limite_{etiqueta}",
                     f"💸 Costo de IA de hoy: USD {costo:.2f} ({etiqueta}% del límite diario de USD {lim:.2f}). "
                     f"No se bloquean respuestas. Detalle en /health/ia.")
            break


def _alertar(clave: str, texto: str) -> None:
    if clave in _estado._alertas_enviadas:
        return
    _estado._alertas_enviadas.add(clave)
    try:
        import asyncio
        from channels.telegram_bot import send_alert
        loop = asyncio.get_running_loop()
        loop.create_task(send_alert(texto))
    except Exception:
        logger.warning(f"[AIMetrics] alerta no enviada: {texto}")


# ── Persistencia ligera y lectura ────────────────────────────────────────────

def _ruta() -> Path:
    return Path(os.getenv("DATA_DIR", "/data")) / f"ai_metrics_{_estado.dia}.json"


def _guardar_si_corresponde(force: bool = False) -> None:
    if not force and time.time() - _estado._ultimo_guardado < 30:
        return
    _estado._ultimo_guardado = time.time()
    try:
        p = _ruta()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(resumen(), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def resumen() -> dict:
    if _estado.dia != _hoy():
        _estado.reset(_hoy())
    from providers.factory import get_active_provider_name
    try:
        configurado = get_active_provider_name()
    except Exception:
        configurado = "?"
    t = _estado.totales
    ok = t["ok"] or 0
    return {
        "dia": _estado.dia,
        "proveedor_configurado": configurado,
        "modelo_configurado": os.getenv("OPENROUTER_MODEL", "") if configurado == "openrouter" else "",
        "ultimo_proveedor_efectivo": _estado.ultimo_proveedor_ok,
        "totales": dict(t),
        "pct_respaldo": round(100 * t["fallback_ok"] / ok, 1) if ok else 0.0,
        "limite_diario_usd": limite_diario(),
        "nota_costos": "Estimado: costo real si el proveedor lo informa; si no, tokens × tabla de precios. "
                       "Las llamadas sin precio conocido no suman costo (ver llamadas_sin_precio).",
        "por_agente": _estado.por_agente,
        "por_proceso": _estado.por_proceso,
        "por_modelo": _estado.por_modelo,
        "errores_recientes": list(_estado.errores),
    }


def _reset_para_tests() -> None:
    _estado.reset(_hoy())
    _estado.errores.clear()
