"""
Router: detecta qué agente debe manejar cada conversación.
"""
import re
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

genai.configure(api_key=GEMINI_API_KEY)

# Palabras clave por categoría
KEYWORDS_PISCINA = [
    "piscina", "pileta", "natación", "nadar", "pool", "arco romano",
    "minimalista", "playa", "abanico", "fibra", "fibra de vidrio",
    "miniportante", "autoportante", "minideck", "minipiscina",
    "pileta chica", "piscina chica", "piscina pequeña", "nadar"
]

KEYWORDS_MODULO = [
    "módulo", "modulo", "nce", "vivienda", "casa", "habitación", "habitacion",
    "oficina", "quincho", "local", "espacio", "construcción", "construccion",
    "ampliación", "ampliacion", "panel", "paneles", "m2", "metros", "m²",
    "dormitorio", "pieza", "cuarto", "prefabricado", "prefabricada"
]

KEYWORDS_CONTADO = [
    "contado", "efectivo", "transferencia", "pago", "precio", "cuánto cuesta",
    "cuanto cuesta", "de una", "al toque", "ya", "rápido", "rapido", "hoy",
    "en efectivo", "cuanto sale", "cuánto sale", "vale", "cuesta"
]

KEYWORDS_FINANCIACION = [
    "cuotas", "financiación", "financiacion", "financiar", "plan", "mensual",
    "cooperativa", "no tengo todo", "no llego", "en partes", "pagar en partes",
    "plazo", "crédito", "credito", "cuota", "pagarlo en", "pagar en cuotas",
    "no tengo el dinero", "no tengo la plata", "en cuotas"
]

AGENT_MAP = {
    ("piscina", "contado"): "pablo",
    ("piscina", "financiacion"): "laura",
    ("modulo", "contado"): "sabrina",
    ("modulo", "financiacion"): "claudio",
}


def detect_keywords(text: str) -> tuple:
    """Retorna (product_type, payment_type) basado en keywords."""
    text_lower = text.lower()

    product = None
    payment = None

    piscina_score = sum(1 for kw in KEYWORDS_PISCINA if kw in text_lower)
    modulo_score = sum(1 for kw in KEYWORDS_MODULO if kw in text_lower)

    if piscina_score > modulo_score:
        product = "piscina"
    elif modulo_score > piscina_score:
        product = "modulo"

    contado_score = sum(1 for kw in KEYWORDS_CONTADO if kw in text_lower)
    financiacion_score = sum(1 for kw in KEYWORDS_FINANCIACION if kw in text_lower)

    if contado_score > financiacion_score:
        payment = "contado"
    elif financiacion_score > contado_score:
        payment = "financiacion"

    return product, payment


def route_with_ai(history: list, new_message: str) -> dict:
    """Usa Gemini para detectar producto y modalidad de pago."""
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction="""Analizás mensajes de WhatsApp de clientes potenciales de una empresa que vende módulos prefabricados y piscinas.
Tu tarea: determinar qué quiere el cliente.
Respondé SOLO con JSON válido:
{
  "product": "piscina" | "modulo" | "unknown",
  "payment": "contado" | "financiacion" | "unknown",
  "confidence": "high" | "medium" | "low"
}"""
        )
        context = ""
        if history:
            last_msgs = history[-6:]
            context = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in last_msgs])
            context += "\n"
        context += f"USER: {new_message}"

        response = model.generate_content(context)
        import json
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return {"product": "unknown", "payment": "unknown", "confidence": "low"}


def get_agent_for_conversation(
    history: list,
    new_message: str,
    current_agent: str = None
) -> str:
    """
    Determina qué agente debe responder.
    Si ya hay un agente asignado, lo mantiene salvo que el cliente cambie de tema.
    """
    if current_agent and current_agent != "router":
        return current_agent

    # Primero intentamos con keywords (más rápido)
    all_text = new_message
    if history:
        all_text = " ".join([m["content"] for m in history[-5:]]) + " " + new_message

    product, payment = detect_keywords(all_text)

    if product and payment:
        agent = AGENT_MAP.get((product, payment))
        if agent:
            return agent

    # Si no alcanza con keywords, usamos AI
    ai_result = route_with_ai(history, new_message)

    ai_product = ai_result.get("product", "unknown")
    ai_payment = ai_result.get("payment", "unknown")

    if ai_product != "unknown" and ai_payment != "unknown":
        agent = AGENT_MAP.get((ai_product, ai_payment))
        if agent:
            return agent

    # Si tenemos producto pero no pago, asignamos el agente de contado por defecto
    # y luego preguntamos
    if ai_product == "piscina":
        return "pablo"  # pablo pregunta modalidad naturalmente
    if ai_product == "modulo":
        return "sabrina"  # sabrina pregunta modalidad naturalmente

    # No detectamos nada → router pregunta
    return "router"


ROUTER_PROMPT = """Sos el primer contacto de Eco Módulos & Piscinas por WhatsApp.
Tu única tarea es entender qué quiere el cliente y derivarlo al asesor correcto.
Sos amable, breve, y hacés UNA sola pregunta a la vez.

Si no sabés qué quiere, preguntá: "¡Hola! ¿Estás consultando por módulos prefabricados o por piscinas?"
Si ya sabés el producto pero no la modalidad de pago, preguntá sobre eso.

Respondé en español argentino, máximo 2 líneas, sin emojis excesivos, sin sonar robot."""


def get_router_response(history: list, new_message: str) -> str:
    """Respuesta del router cuando no puede determinar el agente."""
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=ROUTER_PROMPT
        )
        messages = []
        for msg in history[-10:]:
            role = "user" if msg["role"] == "user" else "model"
            messages.append({"role": role, "parts": [msg["content"]]})
        messages.append({"role": "user", "parts": [new_message]})
        response = model.generate_content(messages)
        return response.text.strip()
    except Exception:
        return "¡Hola! ¿Consultás por módulos prefabricados o por piscinas?"
