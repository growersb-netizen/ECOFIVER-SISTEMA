"""
Registro de ejecuciones del scheduler — Etapa 1.

Cada tarea programada queda envuelta: se registra inicio, fin, duración,
resultado (ok / error / omitida) y el error si lo hubo. Las tareas pueden
devolver un dict con un resumen ({"enviados": 3, ...}) que se guarda como
evidencia. Sin esto, una tarea que fallaba o no hacía nada era indistinguible
de una que funcionaba.

Persistencia: últimas ejecuciones en memoria + archivo JSONL en DATA_DIR
(scheduler_runs.jsonl, recortado a las últimas 5000 líneas).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=-3))
_MAX_LINEAS = 5000

_recientes: deque = deque(maxlen=300)
_ultima_por_tarea: dict[str, dict] = {}


def _ruta() -> Path:
    return Path(os.getenv("DATA_DIR", "/data")) / "scheduler_runs.jsonl"


def _persistir(registro: dict) -> None:
    try:
        p = _ruta()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        if p.stat().st_size > 2_000_000:  # recorte ocasional
            lineas = p.read_text(encoding="utf-8").splitlines()[-_MAX_LINEAS:]
            p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[RunLog] no se pudo persistir: {e}")


def registrar(tarea: str, inicio: float, estado: str, resultado=None, error: str = "") -> dict:
    fin = time.time()
    reg = {
        "tarea": tarea,
        "inicio": datetime.fromtimestamp(inicio, _TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "fin": datetime.fromtimestamp(fin, _TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "duracion_s": round(fin - inicio, 2),
        "estado": estado,                      # ok | error
        "resultado": resultado if isinstance(resultado, (dict, list, str, int, float, bool)) else None,
        "error": (error or "")[:300],
    }
    _recientes.append(reg)
    _ultima_por_tarea[tarea] = reg
    _persistir(reg)
    return reg


def tracked(tarea: str, fn):
    """Envuelve una corrutina de tarea programada para registrar su ejecución."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        from tools.ai_metrics import proceso_actual
        token = proceso_actual.set(f"cron:{tarea}")
        inicio = time.time()
        try:
            resultado = await fn(*args, **kwargs)
        except Exception as e:
            logger.error(f"[RunLog] {tarea} falló: {e}")
            registrar(tarea, inicio, "error", error=f"{type(e).__name__}: {e}")
            return None
        finally:
            proceso_actual.reset(token)
        estado = "error" if isinstance(resultado, dict) and resultado.get("error") else "ok"
        registrar(tarea, inicio, estado, resultado=resultado,
                  error=str(resultado.get("error")) if estado == "error" else "")
        return resultado
    wrapper.__wrapped_tarea__ = tarea
    return wrapper


def instrumentar(scheduler) -> int:
    """Envuelve todas las tareas ya registradas en el scheduler. Retorna cuántas."""
    n = 0
    for job in scheduler.get_jobs():
        if getattr(job.func, "__wrapped_tarea__", None):
            continue
        job.modify(func=tracked(job.id, job.func))
        n += 1
    return n


def resumen(detalle: bool = False) -> dict:
    tareas = {}
    for t, r in sorted(_ultima_por_tarea.items()):
        tareas[t] = {k: r[k] for k in ("fin", "duracion_s", "estado")}
        if detalle:
            tareas[t]["resultado"] = r.get("resultado")
            tareas[t]["error"] = r.get("error")
        else:
            tareas[t]["con_error"] = bool(r.get("error"))
    ultimas = list(_recientes)[-50:]
    return {
        "tareas": tareas,
        "ejecuciones_registradas": len(_recientes),
        "errores_recientes": sum(1 for r in _recientes if r["estado"] == "error"),
        "ultimas": ultimas if detalle else [{k: r[k] for k in ("tarea", "fin", "estado", "duracion_s")} for r in ultimas],
    }


def _reset_para_tests() -> None:
    _recientes.clear()
    _ultima_por_tarea.clear()
