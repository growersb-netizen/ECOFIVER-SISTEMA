"""
Sistema de auditoría de acciones de agentes.
Registra en /data/audit.log (volumen persistente) cada interacción:
quién respondió, cuándo, qué recibió, qué dijo, y qué señales emitió.
Nunca bloquea el flujo principal — fallas se loguean y se ignoran.
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_TZ_ARG = timezone(timedelta(hours=-3))
_LOG_PATH = Path(os.getenv("DATA_DIR", "/data")) / "audit.log"
_MAX_MSG_LEN = 500  # truncar mensajes largos en el log


def _now_str() -> str:
    return datetime.now(_TZ_ARG).strftime("%Y-%m-%d %H:%M:%S")


def _truncate(text: str, max_len: int = _MAX_MSG_LEN) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


def registrar_interaccion(
    *,
    canal: str,
    session_id: str,
    agente: str,
    mensaje_usuario: str,
    respuesta_agente: str,
    señales: list[str] | None = None,
    derivacion_a: str | None = None,
    acciones_crm: list[str] | None = None,
    msg_type: str = "text",
) -> None:
    """
    Escribe una línea JSONL en el archivo de auditoría.
    Llamar después de que el agente generó su respuesta final (ya limpia).
    """
    try:
        entry = {
            "ts": _now_str(),
            "canal": canal,
            "session": session_id,
            "agente": agente,
            "tipo_msg": msg_type,
            "usuario": _truncate(mensaje_usuario),
            "respuesta": _truncate(respuesta_agente),
        }
        if señales:
            entry["señales"] = señales
        if derivacion_a:
            entry["derivado_a"] = derivacion_a
        if acciones_crm:
            entry["acciones_crm"] = acciones_crm

        line = json.dumps(entry, ensure_ascii=False)

        # Asegurar que el directorio existe
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    except Exception as e:
        logger.warning(f"[Audit] No se pudo escribir en audit.log: {e}")


def leer_ultimas(n: int = 50) -> list[dict]:
    """Retorna las últimas N entradas del log (más recientes al final)."""
    try:
        if not _LOG_PATH.exists():
            return []
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except Exception as e:
        logger.warning(f"[Audit] No se pudo leer audit.log: {e}")
        return []


def leer_por_session(session_id: str, n: int = 100) -> list[dict]:
    """Retorna entradas de una sesión específica."""
    try:
        if not _LOG_PATH.exists():
            return []
        entries = []
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("session") == session_id:
                        entries.append(e)
                except json.JSONDecodeError:
                    pass
        return entries[-n:]
    except Exception as e:
        logger.warning(f"[Audit] Error leyendo por session: {e}")
        return []
