"""
Cotización de piscinas de contado en la conversación con el cliente.

El agente NO calcula precios: escribe la frase y pone [COTIZAR:modelo|localidad|provincia|dirección]
donde va el precio. Acá se reemplaza por el precio final único que calcula el CRM
(catálogo vigente + traslado por km verificado + promoción autorizada). Si el CRM
no puede cotizar sin inventar (distancia no verificada, modelo sin precio), se le
dice al cliente que se lo confirmamos y se avisa al equipo.
"""
from __future__ import annotations

import logging
import re

import httpx

from tools import crm_client

logger = logging.getLogger(__name__)

_RE = re.compile(r"\[COTIZAR:([^\]|]+)\|([^\]|]+)(?:\|([^\]|]*))?(?:\|([^\]]*))?\]")

_SIN_DISTANCIA = "te confirmo el precio final en un rato (estoy verificando el traslado exacto a tu localidad)"
_SIN_PRECIO = "te confirmo el precio vigente de ese modelo en un rato"
_AUTOPORTANTE = "ese tamaño no lo hacemos en autoportante (llegan hasta 4,10 m)"
_ERROR = "te confirmo el precio final en un rato"


def _pesos(n: float) -> str:
    return "$" + f"{round(n):,}".replace(",", ".")


async def _cotizar(agente: str, modelo: str, localidad: str, provincia: str, direccion: str = "") -> dict:
    headers = {**crm_client.HEADERS, "X-Agente": agente}
    async with httpx.AsyncClient(timeout=crm_client.TIMEOUT) as c:
        r = await c.post(f"{crm_client.CRM_BASE_URL}/api/comercial/contado/cotizar", headers=headers,
                         json={"modelo": modelo.strip(), "localidad": localidad.strip(), "provincia": provincia.strip(),
                               "direccion": direccion.strip()})
    r.raise_for_status()
    return r.json()


async def _avisar_equipo(texto: str) -> None:
    try:
        from channels.telegram_bot import send_alert
        await send_alert(texto)
    except Exception as e:
        logger.warning(f"[Cotizador] No se pudo avisar al equipo: {e}")


async def procesar_cotizaciones(reply: str, agente: str) -> str:
    """Reemplaza cada [COTIZAR:...] por el precio final del servidor (o un aviso honesto)."""
    if "[COTIZAR:" not in (reply or ""):
        return reply
    salida, ultimo = [], 0
    for m in _RE.finditer(reply):
        modelo, localidad, provincia, direccion = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
        try:
            q = await _cotizar(agente, modelo, localidad, provincia, direccion)
        except Exception as e:
            logger.warning(f"[Cotizador] CRM no cotizó {modelo}/{localidad}: {e}")
            q = {"ok": False, "motivo": "error"}
        if q.get("ok"):
            texto = _pesos(q["precio_final"])
            promo = q.get("promocion_disponible")
            if promo:
                texto += (f" (o {_pesos(promo['precio_final_con_promocion'])} si reservás la fecha de instalación "
                          f"durante la promoción, hasta el {promo['hasta'][8:10]}/{promo['hasta'][5:7]})")
        else:
            motivo = q.get("motivo")
            texto = {"distancia_no_disponible": _SIN_DISTANCIA, "modelo_sin_precio": _SIN_PRECIO,
                     "autoportante_fuera_de_rango": _AUTOPORTANTE}.get(motivo, _ERROR)
            if motivo == "localidad_ambigua":
                provs = " o ".join(q.get("candidatos") or [])
                texto = (f"te lo paso apenas me confirmes la provincia: ¿{localidad.strip()} de {provs}?"
                         if provs else f"te lo paso apenas me confirmes la provincia de {localidad.strip()}")
            elif motivo in ("distancia_no_disponible", "modelo_sin_precio"):
                await _avisar_equipo(f"⚠️ Cotización pendiente ({agente}): {q.get('detalle', motivo)}. "
                                     "Cargar el dato en el CRM (Comercial → distancias/catálogo).")
        salida.append(reply[ultimo:m.start()] + texto)
        ultimo = m.end()
    salida.append(reply[ultimo:])
    return "".join(salida)
