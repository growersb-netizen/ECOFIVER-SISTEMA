"""
Scoring automático de temperatura de leads — EcoFiver.

Detecta señales de intención de compra en la conversación para clasificar el lead
como CALIENTE / TIBIO / FRÍO sin depender de que el agente lo marque.
Se usa en el router para:
  - actualizar el estado del lead en el CRM
  - disparar una alerta en tiempo real a Rodrigo cuando un lead se pone caliente
"""

import re
import logging

logger = logging.getLogger(__name__)

# Señales fuertes de compra (cada una pesa 2)
_FUERTES = [
    r"\bquiero (comprar|avanzar|reservar|sacar|cerrar)\b",
    r"\blo quiero\b",
    r"\bme lo llevo\b",
    r"\breserv", r"\bseñ[ao]\b|\bseñar\b",
    r"\bcu[aá]ndo (lo|la|me|pueden|podr[ií]an)\b",
    r"\bpara cu[aá]ndo\b",
    r"\bvideollamada\b|\bvideo llamada\b",
    r"\bc[oó]mo (pago|abono|sigo|avanzo|reservo)\b",
    r"\bya tengo el terreno\b|\btengo el terreno\b|\btengo lugar\b",
    r"\bquiero la (piscina|pileta|casa|m[oó]dulo)\b",
]

# Señales medias de interés (cada una pesa 1)
_MEDIAS = [
    r"\bprecio\b|\bcu[aá]nto (sale|cuesta|vale|es)\b",
    r"\bcuota", r"\bfinanci", r"\bplan(es)?\b",
    r"\bflete\b", r"\bentrega\b|\binstalaci[oó]n\b",
    r"\bdescuento\b|\boferta\b|\bpromo",
    r"\bmedidas\b|\bmodelo\b|\btama[ñn]o\b",
    r"\bterreno\b|\bpatio\b|\bfondo\b",
    r"\bme interesa\b|\bme gustar[ií]a\b",
]

# Señal explícita que el agente puede emitir
_SIGNAL_RE = re.compile(r"\[LEAD_CALIENTE\]", re.IGNORECASE)


def limpiar_signal(texto: str) -> str:
    return _SIGNAL_RE.sub("", texto).strip()


def evaluar_temperatura(mensaje_cliente: str, reply_agente: str = "") -> dict:
    """
    Devuelve {temperatura, score, motivos}.
    temperatura: 'caliente' | 'tibio' | 'frio'
    """
    texto = (mensaje_cliente or "").lower()
    score = 0
    motivos = []

    # Señal explícita del agente → caliente directo
    if reply_agente and _SIGNAL_RE.search(reply_agente):
        return {"temperatura": "caliente", "score": 10, "motivos": ["agente marcó caliente"]}

    for pat in _FUERTES:
        if re.search(pat, texto):
            score += 2
            motivos.append("intención fuerte")
    for pat in _MEDIAS:
        if re.search(pat, texto):
            score += 1
            motivos.append("interés")

    # Dato de contacto/ubicación concreto suma
    if re.search(r"\b\d{6,}\b", texto):  # teléfono o número largo
        score += 1
    if score >= 3:
        temp = "caliente"
    elif score >= 1:
        temp = "tibio"
    else:
        temp = "frio"

    # Resumen de motivos único y corto
    motivos_unicos = list(dict.fromkeys(motivos))[:3]
    return {"temperatura": temp, "score": score, "motivos": motivos_unicos}
