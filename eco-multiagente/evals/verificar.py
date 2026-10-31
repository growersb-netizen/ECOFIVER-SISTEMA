"""Comprobaciones determinísticas de un caso de evaluación (sin red, sin costo)."""
from __future__ import annotations

import re


def verificar(caso: dict, respuesta: str) -> list[str]:
    """Devuelve la lista de fallas (vacía = el caso pasa)."""
    fallas = []
    for p in caso.get("esperar", []):
        if not re.search(p, respuesta):
            fallas.append(f"falta señal esperada: {p}")
    alguno = caso.get("esperar_alguno", [])
    if alguno and not any(re.search(p, respuesta) for p in alguno):
        fallas.append(f"no aparece ninguno de: {alguno}")
    for p in caso.get("prohibir", []):
        m = re.search(p, respuesta, re.IGNORECASE | re.DOTALL)
        if m:
            fallas.append(f"contenido prohibido: '{m.group(0)[:80]}'")
    return fallas
