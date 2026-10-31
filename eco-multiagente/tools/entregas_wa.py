"""
Estado real de entrega de los mensajes de WhatsApp.

Meta acepta un envío (HTTP 200) y después informa por webhook si se entregó o
falló (p. ej. 131047: fuera de la ventana de 24 h → hace falta plantilla). Antes
eso solo quedaba en el log: un "enviado" se confundía con "entregado". Acá se
cuentan los estados y las fallas por código (sin teléfonos ni contenido).
"""
from __future__ import annotations

import time

_stats: dict = {"por_estado": {}, "fallas_por_codigo": {}, "ultima_falla": None}
_DESCRIPCION = {131047: "fuera de la ventana de 24 h: requiere plantilla aprobada",
                131026: "el destinatario no puede recibir el mensaje",
                131049: "Meta limitó el envío (calidad/marketing)",
                130472: "número en experimento de Meta (no se entrega marketing)"}


def registrar_estado(st: dict) -> None:
    try:
        estado = str(st.get("status") or "?")
        _stats["por_estado"][estado] = _stats["por_estado"].get(estado, 0) + 1
        if estado == "failed":
            for err in st.get("errors") or [{}]:
                codigo = err.get("code", "?")
                k = str(codigo)
                _stats["fallas_por_codigo"][k] = _stats["fallas_por_codigo"].get(k, 0) + 1
                _stats["ultima_falla"] = {"codigo": codigo, "descripcion": _DESCRIPCION.get(codigo, err.get("title", "")),
                                          "ts": int(time.time())}
    except Exception:
        pass


def stats() -> dict:
    fallas = sum(_stats["fallas_por_codigo"].values())
    return {**_stats, "fallas_total": fallas,
            "fuera_de_ventana_24h": _stats["fallas_por_codigo"].get("131047", 0),
            "nota": "Contadores desde el último reinicio. Los envíos fuera de la ventana de 24 h necesitan plantillas."}
