"""
Catálogo real de modelos de OpenRouter (GET https://openrouter.ai/api/v1/models, público).

Se descarga al iniciar y luego como máximo una vez cada 24 h; se guarda en
DATA_DIR/openrouter_models.json para sobrevivir reinicios y funcionar aunque
OpenRouter no responda en ese momento.

Provee, por modelo: precio por token (entrada/salida), contexto máximo y
modalidades de entrada (text / image / audio / file). Lo usan:
  - tools.model_policy: validar que el modelo configurado exista y tenga la
    capacidad que el agente necesita (ej. audio para transcribir).
  - tools.ai_metrics: costo con precios reales.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_URL = "https://openrouter.ai/api/v1/models"
_TTL = 24 * 3600

_modelos: dict[str, dict] = {}
_actualizado: float = 0.0
_origen: str = "vacío"


def _ruta() -> Path:
    return Path(os.getenv("DATA_DIR", "/data")) / "openrouter_models.json"


def _normalizar(item: dict) -> dict | None:
    mid = item.get("id")
    if not mid:
        return None
    pricing = item.get("pricing") or {}
    arch = item.get("architecture") or {}

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "id": mid,
        "nombre": item.get("name", mid),
        "precio_in_token": _f(pricing.get("prompt")),
        "precio_out_token": _f(pricing.get("completion")),
        "contexto": item.get("context_length"),
        "entradas": list(arch.get("input_modalities") or []),
        "salidas": list(arch.get("output_modalities") or []),
    }


def cargar_desde_datos(data: list[dict], origen: str) -> int:
    global _modelos, _actualizado, _origen
    nuevos = {}
    for item in data or []:
        n = _normalizar(item)
        if n:
            nuevos[n["id"]] = n
    if nuevos:
        _modelos, _actualizado, _origen = nuevos, time.time(), origen
    return len(nuevos)


def _cargar_cache() -> None:
    try:
        p = _ruta()
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            n = cargar_desde_datos(raw.get("data", []), "cache")
            global _actualizado
            _actualizado = raw.get("_descargado", _actualizado)
            logger.info(f"[Catálogo OR] {n} modelos desde cache")
    except Exception as e:
        logger.warning(f"[Catálogo OR] cache ilegible: {e}")


async def actualizar(force: bool = False) -> int:
    """Descarga el catálogo si venció (o force). Retorna cantidad de modelos disponibles."""
    if not _modelos:
        _cargar_cache()
    if not force and _modelos and time.time() - _actualizado < _TTL:
        return len(_modelos)
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(_URL)
        r.raise_for_status()
        data = r.json().get("data", [])
        n = cargar_desde_datos(data, "openrouter")
        try:
            p = _ruta()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"_descargado": time.time(), "data": data}), encoding="utf-8")
        except Exception:
            pass
        logger.info(f"[Catálogo OR] {n} modelos actualizados desde OpenRouter")
        return n
    except Exception as e:
        logger.warning(f"[Catálogo OR] no se pudo actualizar ({e}); se usa {_origen} con {len(_modelos)} modelos")
        return len(_modelos)


def disponible() -> bool:
    if not _modelos:
        _cargar_cache()
    return bool(_modelos)


def info(modelo: str) -> dict | None:
    if not _modelos:
        _cargar_cache()
    return _modelos.get(modelo)


def precio_por_millon(modelo: str) -> tuple[float, float] | None:
    i = info(modelo)
    if not i or i["precio_in_token"] is None or i["precio_out_token"] is None:
        return None
    return i["precio_in_token"] * 1_000_000, i["precio_out_token"] * 1_000_000


def estado() -> dict:
    return {
        "modelos": len(_modelos),
        "origen": _origen,
        "actualizado_hace_h": round((time.time() - _actualizado) / 3600, 1) if _actualizado else None,
    }


def _reset_para_tests() -> None:
    global _modelos, _actualizado, _origen
    _modelos, _actualizado, _origen = {}, 0.0, "vacío"
