"""
Quiz de postulación para Aliados Comerciales EcoFiver.
Flujo: postulante en CRM → Franco envía quiz por WA → respuestas → paquete 🟡 a Rodrigo.

Estado en memoria (keyed by teléfono). Suficiente para el volumen esperado.
Si el proceso se reinicia, los estados activos se reconstruyen al responder.
"""

import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PREGUNTAS DEL QUIZ
# ─────────────────────────────────────────────────────────────────────────────

PREGUNTAS = [
    {
        "num": 1,
        "texto": "¿En qué zona geográfica opera el programa de Socios Comerciales?",
        "tipo": "cerrada",
        "respuesta_correcta": [
            "todo el pais", "en todo el pais", "todo el país", "en todo el país",
            "nacional", "argentina", "todo el territorio nacional", "en todo el territorio nacional",
        ],
    },
    {
        "num": 2,
        "texto": "¿Quién cierra una venta, contado o financiada: el Socio Comercial o el equipo de EcoFiver?",
        "tipo": "cerrada",
        "respuesta_correcta": ["el socio", "el socio comercial", "yo", "el aliado"],
    },
    {
        "num": 3,
        "texto": "¿Con qué herramienta cotizás precios y cuotas?",
        "tipo": "cerrada",
        "respuesta_correcta": ["fichas", "fichas oficiales", "las fichas", "ficha oficial", "calculadora", "catalogo", "catálogo"],
    },
    {
        "num": 4,
        "texto": "¿Tenés horario fijo de trabajo como Socio Comercial?",
        "tipo": "cerrada",
        "respuesta_correcta": ["no", "no tengo", "no hay"],
    },
    {
        "num": 5,
        "texto": "¿Cómo se calcula tu comisión en una venta financiada?",
        "tipo": "cerrada",
        "respuesta_correcta": ["75%", "75% de una cuota", "sobre una cuota", "75 por ciento de la cuota", "el 75% del valor de una cuota"],
    },
    {
        "num": 6,
        "texto": "¿Cuándo se libera tu comisión en una venta financiada?",
        "tipo": "cerrada",
        "respuesta_correcta": [
            "con la llamada de bienvenida",
            "cuando el equipo llama al cliente",
            "despues de la auditoria",
            "después de la auditoría",
            "con la auditoria",
        ],
    },
    {
        "num": 7,
        "texto": "¿Necesitás inscribirte en Monotributo para operar como Socio Comercial?",
        "tipo": "cerrada",
        "respuesta_correcta": ["si", "sí", "eventualmente", "si eventualmente"],
    },
    {
        "num": 8,
        "texto": "¿La instalación está incluida en una venta de contado?",
        "tipo": "cerrada",
        "respuesta_correcta": ["no", "no esta incluida", "no está incluida", "la coordino yo", "no incluye instalacion", "no incluye instalación"],
    },
    {
        "num": 9,
        "texto": "¿A quién le escribís si tenés dudas sobre una venta en curso?",
        "tipo": "cerrada",
        "respuesta_correcta": ["franco", "al grupo", "grupo de socios", "al grupo de socios", "grupo de aliados"],
    },
    {
        "num": 10,
        "texto": "Contanos en una frase: ¿por qué te interesa este programa? (respuesta libre)",
        "tipo": "abierta",
        "respuesta_correcta": [],  # cualitativa, no puntúa
    },
]

PUNTAJE_MINIMO = 7   # de 9 cerradas
TIMEOUT_DIAS   = 5   # sin respuesta → inactivo


# ─────────────────────────────────────────────────────────────────────────────
# ESTADO EN MEMORIA
# ─────────────────────────────────────────────────────────────────────────────

# { telefono: { "nombre": str, "codigo_postulante": str, "pregunta_actual": int,
#               "respuestas": [str], "inicio": datetime, "video_recibido": bool } }
_estados_quiz: dict[str, dict] = {}


def iniciar_quiz(telefono: str, nombre: str, codigo: str):
    """Registra el inicio del quiz para un postulante."""
    _estados_quiz[telefono] = {
        "nombre": nombre,
        "codigo_postulante": codigo,
        "pregunta_actual": 1,
        "respuestas": [],
        "inicio": datetime.now(timezone.utc),
        "video_recibido": False,
    }
    logger.info(f"[QUIZ] Inicio quiz postulante {codigo} ({telefono})")


def estado_quiz(telefono: str) -> dict | None:
    return _estados_quiz.get(telefono)


def esta_en_quiz(telefono: str) -> bool:
    return telefono in _estados_quiz


def pregunta_actual(telefono: str) -> dict | None:
    estado = _estados_quiz.get(telefono)
    if not estado:
        return None
    num = estado["pregunta_actual"]
    if num > len(PREGUNTAS):
        return None
    return PREGUNTAS[num - 1]


def registrar_respuesta(telefono: str, respuesta: str) -> dict:
    """
    Registra la respuesta a la pregunta actual y avanza.
    Retorna: { "avanza": bool, "es_correcta": bool | None, "completo": bool }
    """
    estado = _estados_quiz.get(telefono)
    if not estado:
        return {"avanza": False, "es_correcta": None, "completo": False}

    num_actual = estado["pregunta_actual"]
    pregunta = PREGUNTAS[num_actual - 1]
    estado["respuestas"].append(respuesta.strip())

    es_correcta = None
    if pregunta["tipo"] == "cerrada":
        resp_lower = respuesta.strip().lower()
        es_correcta = any(
            correcta in resp_lower or resp_lower in correcta
            for correcta in pregunta["respuesta_correcta"]
        )

    estado["pregunta_actual"] += 1
    completo = estado["pregunta_actual"] > len(PREGUNTAS)

    return {"avanza": True, "es_correcta": es_correcta, "completo": completo}


def marcar_video_recibido(telefono: str):
    if telefono in _estados_quiz:
        _estados_quiz[telefono]["video_recibido"] = True


def calcular_puntaje(telefono: str) -> dict:
    """Calcula puntaje sobre las 9 preguntas cerradas."""
    estado = _estados_quiz.get(telefono)
    if not estado:
        return {"correctas": 0, "total_cerradas": 9, "aprobado": False}

    correctas = 0
    for i, pregunta in enumerate(PREGUNTAS[:-1]):  # excluye pregunta 10 (abierta)
        if i >= len(estado["respuestas"]):
            break
        resp = estado["respuestas"][i].lower()
        if any(
            c in resp or resp in c
            for c in pregunta["respuesta_correcta"]
        ):
            correctas += 1

    return {
        "correctas": correctas,
        "total_cerradas": 9,
        "aprobado": correctas >= PUNTAJE_MINIMO,
    }


def armar_resumen_para_rodrigo(telefono: str) -> str:
    """Arma el texto del paquete 🟡 con el resultado del quiz."""
    estado = _estados_quiz.get(telefono)
    if not estado:
        return ""

    puntaje = calcular_puntaje(telefono)
    respuestas_txt = ""
    for i, preg in enumerate(PREGUNTAS):
        resp = estado["respuestas"][i] if i < len(estado["respuestas"]) else "(sin responder)"
        respuestas_txt += f"  P{i+1}: {resp}\n"

    estado_aprobacion = (
        f"✅ APROBADO ({puntaje['correctas']}/{puntaje['total_cerradas']})"
        if puntaje["aprobado"]
        else f"⚠️ NO ALCANZÓ EL MÍNIMO ({puntaje['correctas']}/{puntaje['total_cerradas']} — mínimo {PUNTAJE_MINIMO})"
    )
    video_ok = "✅ Recibido" if estado.get("video_recibido") else "⏳ Pendiente"

    return (
        f"🟡 POSTULANTE COMPLETA QUIZ — {estado['nombre']} ({estado['codigo_postulante']})\n"
        f"Quiz: {estado_aprobacion}\n"
        f"Video: {video_ok}\n"
        f"Respuestas:\n{respuestas_txt}"
        f"→ Responder: ALTA / RECHAZAR / SEGUNDA CHARLA"
    )


def limpiar_estado(telefono: str):
    _estados_quiz.pop(telefono, None)


def postulantes_con_timeout() -> list[str]:
    """Retorna teléfonos de postulantes sin actividad por más de TIMEOUT_DIAS días."""
    ahora = datetime.now(timezone.utc)
    timeout = timedelta(days=TIMEOUT_DIAS)
    return [
        tel for tel, est in _estados_quiz.items()
        if (ahora - est["inicio"]) > timeout
    ]


# ─────────────────────────────────────────────────────────────────────────────
# MENSAJES PREDEFINIDOS
# ─────────────────────────────────────────────────────────────────────────────

MENSAJE_BIENVENIDA = (
    "¡Hola {nombre}! Gracias por tu interés en ser Aliado Comercial de EcoFiver 🙌\n\n"
    "Para conocerte un poco más y avanzar con tu alta, te pedimos dos cosas simples:\n\n"
    "1️⃣ Respondé este cuestionario corto (5 minutos) — te voy a ir haciendo las preguntas "
    "acá por WhatsApp, una por una.\n\n"
    "2️⃣ Cuando termines el quiz, mandanos un video de 60 segundos contándonos:\n"
    "  • Tu nombre y localidad (5 seg)\n"
    "  • A qué te dedicás hoy (10 seg)\n"
    "  • Por qué te interesa sumarte (20 seg)\n"
    "  • Cómo pensás captar clientes en tu zona (15 seg)\n"
    "  • Algo sobre vos que quieras que sepamos (10 seg)\n\n"
    "Con eso, en las próximas 48hs te confirmamos si avanzamos.\n\n"
    "Arrancamos con la primera pregunta:"
)

MENSAJE_TIMEOUT = (
    "¡Hola {nombre}! Notamos que no pudiste completar el quiz. "
    "Si querés retomarlo cuando tengas unos minutos, escribinos y arrancamos desde el principio. "
    "¡Éxitos!"
)

GUION_VIDEO = (
    "📹 *Guía para el video de 60 segundos* (no es un libreto, es solo una guía — "
    "la naturalidad importa más que seguirlo al pie de la letra):\n\n"
    "• Tu nombre y de qué localidad sos (5 seg)\n"
    "• A qué te dedicás hoy (10 seg)\n"
    "• Por qué te interesa sumarte como Aliado Comercial (20 seg)\n"
    "• Cómo pensás captar clientes en tu zona (15 seg)\n"
    "• Algo sobre vos que querés que sepamos (10 seg)\n\n"
    "Podés enviarlo por acá nomás 👇"
)
