"""
Panel Operativo de Agentes — Eco Módulos & Piscinas IA
/panel  — Control completo del sistema multiagente.
"""

import os
import json
import logging
import importlib
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_data_base   = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent
PROMPTS_PATH = _data_base / "agents_prompts.json"

# ── Metadatos de los 15 agentes ───────────────────────────────────────────

AGENTS_INFO = {
    "maximo": {
        "nombre": "Máximo", "emoji": "👑", "color": "#1A5C38",
        "rol": "CEO / Director Operativo",
        "modelo_key": "gemini-2.5-pro",
        "canal": "Telegram",
        "reporta_a": None,
        "supervisa": ["aurora","renata","bruno","ezequiel","daniela","sebastian"],
        "funciones": [
            "Reporte diario 08:00 AM a Rodrigo vía Telegram",
            "Activar/pausar campañas Meta Ads",
            "Reasignar leads entre agentes IA",
            "Autorizar refinanciación hasta 2 cuotas",
            "Escalar a Rodrigo solo en casos críticos",
        ],
        "modulo": "agents.maximo",
        "shortcuts": [
            {"label": "📊 Reporte del día", "msg": "Generá el reporte ejecutivo del día con el estado actual del negocio, pipeline, cierres y alertas.", "color": "#1A5C38"},
            {"label": "🎯 Estado del pipeline", "msg": "¿Cuál es el estado actual del pipeline? ¿Hay leads calientes sin cerrar? ¿Alertas?", "color": "#0277BD"},
            {"label": "⚡ Urgencia cupos", "msg": "Activá el protocolo de urgencia de cupos de fabricación de piscinas para leads calientes.", "color": "#E65100"},
            {"label": "💰 Cuotas vencidas", "msg": "¿Cuántas cuotas están vencidas hoy? ¿Qué acciones tomaste con Ignacio?", "color": "#C62828"},
            {"label": "📣 Ordenar campaña", "msg": "Ordenale a Renata que active una campaña agresiva de piscinas para esta semana.", "color": "#6A1B9A"},
            {"label": "🔍 Auditoría equipo", "msg": "¿Cómo viene el rendimiento de cada vendedor IA esta semana? ¿Hay alguno que esté fallando?", "color": "#37474F"},
        ],
    },
    "aurora": {
        "nombre": "Aurora", "emoji": "📊", "color": "#2E7D32",
        "rol": "Gerente Comercial",
        "modelo_key": None,
        "canal": "Interno",
        "reporta_a": "maximo",
        "supervisa": ["tomas"],
        "funciones": [
            "Revisión pipeline 09:00 y 18:00 hs",
            "Detectar cuellos de botella en ventas",
            "Control tasa conversión (mín 15% contado, 10% financiado)",
            "Reporte matutino y vespertino a Máximo",
        ],
        "modulo": "agents.aurora",
        "shortcuts": [
            {"label": "📈 Pipeline matutino", "msg": "Generá el reporte matutino del pipeline con prioridades del día y leads más calientes.", "color": "#2E7D32"},
            {"label": "⚠️ Leads sin respuesta", "msg": "¿Hay leads sin respuesta hace más de 2 horas? Listá los más urgentes.", "color": "#E65100"},
            {"label": "📊 Tasa de conversión", "msg": "¿Cuál es la tasa de conversión actual de contado y financiado? ¿Estamos en objetivo?", "color": "#0277BD"},
            {"label": "🔄 Reagendar vide ollamadas", "msg": "¿Hay videollamadas canceladas de esta semana que haya que reagendar?", "color": "#6A1B9A"},
        ],
    },
    "tomas": {
        "nombre": "Tomás", "emoji": "👀", "color": "#388E3C",
        "rol": "Supervisor de Ventas",
        "modelo_key": None,
        "canal": "Interno",
        "reporta_a": "aurora",
        "supervisa": ["valentina","camila","mateo","nicolas","luciano"],
        "funciones": [
            "Monitoreo en tiempo real de conversaciones activas",
            "Alerta si lead caliente >48hs sin cierre",
            "Clasificar leads: caliente / tibio / frío",
        ],
        "modulo": "agents.tomas",
        "shortcuts": [
            {"label": "🔥 Leads calientes ahora", "msg": "¿Cuáles son los leads calientes activos en este momento? ¿Alguno en riesgo de enfriarse?", "color": "#C62828"},
            {"label": "😴 Leads sin respuesta", "msg": "¿Hay leads sin respuesta hace más de 4 horas que requieran intervención?", "color": "#E65100"},
            {"label": "📋 Estado del equipo", "msg": "Dame el estado actual de cada vendedor IA: cuántos leads activos tiene cada uno.", "color": "#388E3C"},
            {"label": "🎯 Siguiente videollamada", "msg": "¿Cuándo es la próxima videollamada agendada y quién la conduce?", "color": "#0277BD"},
        ],
    },
    "valentina": {
        "nombre": "Valentina", "emoji": "💬", "color": "#0277BD",
        "rol": "Asesora General — Primer Contacto",
        "modelo_key": None,
        "canal": "WhatsApp / Web",
        "reporta_a": "tomas",
        "supervisa": [],
        "funciones": [
            "Primer contacto en WhatsApp, Instagram y web",
            "Detectar necesidad: piscina o módulo",
            "Detectar forma de pago: contado o financiado",
            "Derivar al vendedor especialista correcto",
        ],
        "modulo": "agents.valentina",
        "shortcuts": [
            {"label": "👋 Saludo inicial", "msg": "Hola, buenos días! Vi el anuncio de las piscinas", "color": "#0277BD"},
            {"label": "🏊 Consulta piscina", "msg": "Hola! Quiero una piscina para mi casa en Córdoba, somos una familia de 4 personas", "color": "#00838F"},
            {"label": "🏠 Consulta módulo", "msg": "Quiero un módulo para usar como oficina en mi terreno de Pilar", "color": "#6A1B9A"},
            {"label": "💳 Pregunta financiación", "msg": "¿Tienen cuotas? No tengo todo el dinero junto", "color": "#E65100"},
            {"label": "💰 Pregunta precio", "msg": "¿Cuánto sale más o menos una piscina mediana?", "color": "#1A5C38"},
            {"label": "🎁 Consulta combo", "msg": "Me interesa el combo de módulo con piscina que vi en Instagram", "color": "#AD1457"},
        ],
    },
    "camila": {
        "nombre": "Camila", "emoji": "🏊", "color": "#0288D1",
        "rol": "Vendedora Piscinas Contado",
        "modelo_key": None,
        "canal": "WhatsApp / Web",
        "reporta_a": "tomas",
        "supervisa": [],
        "funciones": [
            "Venta de piscinas de fibra de vidrio al contado",
            "Cotizar con flete incluido por localidad",
            "Confirmar fecha de instalación",
        ],
        "modulo": "agents.camila",
        "shortcuts": [
            {"label": "💵 Cotizar Arco Romano", "msg": "Cuánto sale el Arco Romano Chico al contado? Estoy en Rosario", "color": "#0288D1"},
            {"label": "📦 Qué incluye la piscina", "msg": "¿Qué incluye el precio? ¿La instalación está incluida?", "color": "#1A5C38"},
            {"label": "📍 Consulta flete Mendoza", "msg": "Cuánto sería el flete hasta Mendoza capital?", "color": "#E65100"},
            {"label": "⏰ Cuándo la tengo", "msg": "Si lo confirmo hoy, ¿para cuándo me lo instalan?", "color": "#6A1B9A"},
            {"label": "🏊 Piscina más vendida", "msg": "¿Cuál es la piscina más vendida? Tengo presupuesto de $3.500.000", "color": "#00838F"},
        ],
    },
    "mateo": {
        "nombre": "Mateo", "emoji": "🏠", "color": "#6A1B9A",
        "rol": "Vendedor Módulos Financiados",
        "modelo_key": None,
        "canal": "WhatsApp / Web",
        "reporta_a": "tomas",
        "supervisa": [],
        "funciones": [
            "Venta de módulos NCE en cuotas (12 a 120)",
            "Simular planes de financiación a medida",
            "Agendar videollamada de admisión",
        ],
        "modulo": "agents.mateo",
        "shortcuts": [
            {"label": "🏠 Módulo vivienda 36m²", "msg": "Quiero un módulo de 36m² para vivir. No tengo banco ni scoring. ¿Cómo funciona?", "color": "#6A1B9A"},
            {"label": "🏕️ Glamping inversión", "msg": "Quiero poner módulos para glamping en mi terreno de la sierra. ¿Cuántos puedo poner?", "color": "#1A5C38"},
            {"label": "💻 Home office", "msg": "Necesito un módulo para home office de 18m² en mi fondo. ¿Qué cuota me quedaría?", "color": "#0277BD"},
            {"label": "📹 Agendar videollamada", "msg": "Me interesa la financiación. ¿Cómo sería la videollamada? ¿Qué necesito tener?", "color": "#E65100"},
            {"label": "🔑 ¿Qué pasa si me rechazan?", "msg": "¿Qué pasa si no califico para el financiamiento?", "color": "#C62828"},
        ],
    },
    "nicolas": {
        "nombre": "Nicolás", "emoji": "💧", "color": "#00838F",
        "rol": "Vendedor Piscinas Financiadas",
        "modelo_key": None,
        "canal": "WhatsApp / Web",
        "reporta_a": "tomas",
        "supervisa": [],
        "funciones": [
            "Venta de piscinas en cuotas sin banco",
            "Simular planes de financiación a medida",
            "Agendar videollamada de admisión",
        ],
        "modulo": "agents.nicolas",
        "shortcuts": [
            {"label": "💧 Piscina en cuotas", "msg": "Quiero una piscina pero no tengo el dinero todo junto. ¿Tienen cuotas?", "color": "#00838F"},
            {"label": "🎁 Combo financiado", "msg": "Vi que tienen combo módulo+piscina. ¿Cómo funciona en cuotas?", "color": "#6A1B9A"},
            {"label": "📹 Quiero la videollamada", "msg": "Quiero avanzar. ¿Cómo hago para agendar la entrevista?", "color": "#0277BD"},
            {"label": "❓ Sin banco ni scoring", "msg": "No tengo cuenta bancaria activa. ¿Puedo acceder igual a la financiación?", "color": "#E65100"},
        ],
    },
    "luciano": {
        "nombre": "Luciano", "emoji": "🏗️", "color": "#EF6C00",
        "rol": "Vendedor Módulos Contado + Combos",
        "modelo_key": None,
        "canal": "WhatsApp / Web",
        "reporta_a": "tomas",
        "supervisa": [],
        "funciones": [
            "Venta de módulos NCE al contado",
            "Gestionar combos módulo+piscina",
            "Calcular precios por m² y flete",
        ],
        "modulo": "agents.luciano",
        "shortcuts": [
            {"label": "🏗️ Módulo 24m² contado", "msg": "Cuánto sale un módulo de 24m² al contado para La Plata?", "color": "#EF6C00"},
            {"label": "🎁 Combo con descuento", "msg": "¿Cómo funciona el combo módulo+piscina? ¿Cuánto es el descuento?", "color": "#1A5C38"},
            {"label": "📐 Superficie máxima", "msg": "¿Cuál es el módulo más grande que tienen? ¿Se pueden unir varios?", "color": "#0277BD"},
            {"label": "🚚 Flete Buenos Aires", "msg": "Vivo en Mar del Plata, ¿cuánto saldría el flete de un módulo de 36m²?", "color": "#E65100"},
        ],
    },
    "renata": {
        "nombre": "Renata", "emoji": "🎨", "color": "#AD1457",
        "rol": "Marketing y Contenido (Ecopost)",
        "modelo_key": None,
        "canal": "Interno / Meta Ads",
        "reporta_a": "maximo",
        "supervisa": [],
        "funciones": [
            "Generar imágenes con Ecopost (Cloudflare Worker)",
            "Gestionar y pausar campañas Meta Ads",
            "Crear copys para redes sociales",
            "Monitorear CPL y rendimiento de campañas",
        ],
        "modulo": "agents.renata",
        "shortcuts": [
            {"label": "🖼️ Flyer piscina Instagram", "msg": "Generá un flyer 1080x1080 para Instagram de la piscina Arco Romano Mediana. Precio en cuotas. Tono dinámico.", "color": "#AD1457"},
            {"label": "📱 Story módulo", "msg": "Generá una story 9:16 para módulos NCE. Foco en home office. Precio en cuotas mensuales.", "color": "#6A1B9A"},
            {"label": "✍️ Copy combo", "msg": "Escribí un copy para redes del combo módulo+piscina con el 25% de descuento. Tono urgente.", "color": "#1A5C38"},
            {"label": "⏸️ Pausar campañas", "msg": "Pausá todas las campañas de Meta Ads activas ahora mismo y confirmame.", "color": "#C62828"},
            {"label": "📊 Métricas de la semana", "msg": "¿Cómo vienen el CPL, alcance y conversiones de las campañas esta semana?", "color": "#0277BD"},
            {"label": "📅 Calendario semanal", "msg": "Proponé el calendario de contenido para esta semana considerando la temporada actual.", "color": "#E65100"},
        ],
    },
    "bruno": {
        "nombre": "Bruno", "emoji": "🚛", "color": "#4E342E",
        "rol": "Operaciones y Logística",
        "modelo_key": None,
        "canal": "Interno",
        "reporta_a": "maximo",
        "supervisa": [],
        "funciones": [
            "Coordinar agenda de instalaciones",
            "Controlar stock de piscinas y módulos",
            "Calcular fletes especiales fuera de tabla",
        ],
        "modulo": "agents.bruno",
        "shortcuts": [
            {"label": "📦 Estado del stock", "msg": "¿Cuántas piscinas quedan en stock por modelo? ¿Hay algún modelo agotado?", "color": "#4E342E"},
            {"label": "📅 Agenda instalaciones", "msg": "¿Qué instalaciones hay programadas para esta semana y la próxima?", "color": "#1A5C38"},
            {"label": "🚛 Flete especial", "msg": "Calculá el flete para una piscina Minimalista Grande hasta Neuquén capital.", "color": "#E65100"},
            {"label": "⚠️ Stock bajo", "msg": "¿Hay algún modelo de piscina con stock bajo que deba alertarle a Máximo?", "color": "#C62828"},
        ],
    },
    "ezequiel": {
        "nombre": "Ezequiel", "emoji": "📋", "color": "#37474F",
        "rol": "Administración General",
        "modelo_key": None,
        "canal": "Interno",
        "reporta_a": "maximo",
        "supervisa": ["ignacio","elena"],
        "funciones": [
            "Administración general del negocio",
            "Supervisar cobros (Ignacio) y finanzas (Elena)",
            "Gestionar documentación y contratos",
        ],
        "modulo": "agents.ezequiel",
        "shortcuts": [
            {"label": "📋 Resumen administrativo", "msg": "Dame el resumen administrativo de la semana: contratos, cobros pendientes y documentación.", "color": "#37474F"},
            {"label": "💳 Estado cobros", "msg": "¿Cómo está Ignacio con los cobros esta semana? ¿Cuántas cuotas vencidas hay?", "color": "#C62828"},
            {"label": "📈 Finanzas Elena", "msg": "¿Qué reporte de finanzas tiene Elena para esta semana?", "color": "#1A5C38"},
        ],
    },
    "ignacio": {
        "nombre": "Ignacio", "emoji": "💳", "color": "#C62828",
        "rol": "Cobrador",
        "modelo_key": None,
        "canal": "WhatsApp (saliente)",
        "reporta_a": "ezequiel",
        "supervisa": [],
        "funciones": [
            "Días 1-3: recordatorio cordial automático",
            "Días 4-7: consulta directa de situación",
            "Días 8-15: propuesta de refinanciación",
            "Día 16+: escalar a Ezequiel y Máximo",
        ],
        "modulo": "agents.ignacio",
        "shortcuts": [
            {"label": "📋 Cuotas vencidas hoy", "msg": "¿Cuántas cuotas vencieron hoy? Dame el detalle de cada cliente con días de mora.", "color": "#C62828"},
            {"label": "📝 Recordatorio cordial", "msg": "Generá un mensaje de recordatorio cordial para un cliente con 2 días de mora en la cuota de este mes.", "color": "#E65100"},
            {"label": "💬 Mensaje refinanciación", "msg": "Generá un mensaje de propuesta de refinanciación para un cliente con 10 días de mora.", "color": "#6A1B9A"},
            {"label": "🚨 Escalar crítico", "msg": "Tenemos un cliente con 20 días de mora. Generá el reporte para escalar a Ezequiel y Máximo.", "color": "#37474F"},
        ],
    },
    "elena": {
        "nombre": "Elena", "emoji": "📈", "color": "#558B2F",
        "rol": "Finanzas y CRM",
        "modelo_key": None,
        "canal": "Interno",
        "reporta_a": "ezequiel",
        "supervisa": [],
        "funciones": [
            "Reporte financiero semanal",
            "Registro y control de contratos en CRM",
            "Seguimiento cuotas cobradas vs vencidas",
        ],
        "modulo": "agents.elena",
        "shortcuts": [
            {"label": "📊 Reporte semanal", "msg": "Generá el reporte financiero semanal completo con cobros, gastos y proyección.", "color": "#558B2F"},
            {"label": "💰 Cuotas cobradas vs vencidas", "msg": "¿Cuántas cuotas se cobraron esta semana vs cuántas vencieron sin pagar?", "color": "#1A5C38"},
            {"label": "📑 Estado contratos", "msg": "¿Cuántos contratos nuevos se generaron este mes? ¿Hay alguno con documentación incompleta?", "color": "#0277BD"},
        ],
    },
    "daniela": {
        "nombre": "Daniela", "emoji": "🤝", "color": "#6A1B9A",
        "rol": "RRPP y Gestión de Crisis",
        "modelo_key": None,
        "canal": "WhatsApp / Redes",
        "reporta_a": "maximo",
        "supervisa": [],
        "funciones": [
            "Atención inmediata de reclamos graves",
            "Gestión de crisis de reputación pública",
            "Mediación con clientes conflictivos",
        ],
        "modulo": "agents.daniela",
        "shortcuts": [
            {"label": "🚨 Reclamo urgente", "msg": "Tenemos un cliente muy enojado que amenaza con publicar en redes. ¿Cómo lo manejamos?", "color": "#C62828"},
            {"label": "⭐ Comentario negativo", "msg": "Un cliente dejó una reseña negativa en Google diciendo que lo estafamos. ¿Qué respondemos?", "color": "#E65100"},
            {"label": "🔧 Problema postventa", "msg": "Un cliente instalado hace 2 semanas dice que la piscina tiene una pérdida. ¿Cómo protocolo?", "color": "#6A1B9A"},
            {"label": "✅ Propuesta compensación", "msg": "Generá una propuesta de compensación razonable para un cliente con problema real de instalación.", "color": "#1A5C38"},
        ],
    },
    "sebastian": {
        "nombre": "Sebastián", "emoji": "🔧", "color": "#00695C",
        "rol": "Postventa y Soporte Técnico",
        "modelo_key": None,
        "canal": "WhatsApp",
        "reporta_a": "maximo",
        "supervisa": [],
        "funciones": [
            "Asistencia técnica post-instalación",
            "Gestionar garantías de piscinas y módulos",
            "Coordinar revisiones técnicas con Bruno",
        ],
        "modulo": "agents.sebastian",
        "shortcuts": [
            {"label": "🔧 Problema bomba", "msg": "Mi bomba de piscina no enciende correctamente desde ayer. ¿Qué hago?", "color": "#C62828"},
            {"label": "🌿 Mantenimiento piscina", "msg": "¿Cómo mantengo el agua de la piscina en óptimas condiciones? ¿Con qué frecuencia?", "color": "#00695C"},
            {"label": "🏠 Consulta módulo NCE", "msg": "Tengo un módulo instalado hace 3 meses y noto que hay humedad en una esquina. ¿Qué puede ser?", "color": "#4E342E"},
            {"label": "📋 Solicitar garantía", "msg": "Quiero solicitar una visita técnica bajo garantía. ¿Cuál es el proceso?", "color": "#0277BD"},
        ],
    },
    # ── Agente privado ────────────────────────────────────────────────────
    "valentin": {
        "nombre": "Dr. Valentín Ríos", "emoji": "🧠", "color": "#4A235A",
        "rol": "Terapeuta Personal — Rodo",
        "modelo_key": None,
        "canal": "Privado (vía Máximo)",
        "reporta_a": None,
        "supervisa": [],
        "funciones": [
            "Sesiones de terapia cognitivo conductual (TCC)",
            "Especialista en TDAH, TDA y Altas Capacidades (AACC)",
            "Regulación emocional y manejo de ansiedad",
            "Estrategias para disfunción ejecutiva",
            "Disponible cuando Rodo lo convoca a través de Máximo",
        ],
        "modulo": "agents.valentin",
        "shortcuts": [
            {"label": "🧠 Iniciar sesión", "msg": "Hola Valentín, necesito hablar.", "color": "#4A235A"},
            {"label": "😤 Estoy desbordado", "msg": "Estoy con la cabeza a mil, no puedo parar de pensar y siento que no llego a nada.", "color": "#6A1B9A"},
            {"label": "😴 No puedo descansar", "msg": "Hace días que no duermo bien, la mente no para ni de noche.", "color": "#283593"},
            {"label": "🔥 Situación de estrés", "msg": "Tuve una semana muy pesada con el laburo y siento que estoy al límite.", "color": "#B71C1C"},
            {"label": "💬 Charla libre", "msg": "Quiero hablar, no sé bien de qué, pero necesito procesar algo.", "color": "#37474F"},
            {"label": "📋 Cierre de sesión", "msg": "Creo que por hoy estamos bien. Gracias Valentín.", "color": "#2E7D32"},
        ],
    },
}

AGENTS_ORDER = [
    "maximo","aurora","tomas",
    "valentina","camila","mateo","nicolas","luciano",
    "renata","bruno","ezequiel","ignacio","elena","daniela","sebastian",
    "valentin",
]


# ── Helpers prompts ───────────────────────────────────────────────────────

def _load_custom_prompts() -> dict:
    if PROMPTS_PATH.exists():
        try:
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_custom_prompt(agent_name: str, prompt: str):
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _load_custom_prompts()
    data[agent_name] = prompt
    with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _delete_custom_prompt(agent_name: str):
    data = _load_custom_prompts()
    if agent_name in data:
        del data[agent_name]
        PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _get_default_prompt(agent_name: str) -> str:
    info = AGENTS_INFO.get(agent_name, {})
    module_path = info.get("modulo", f"agents.{agent_name}")
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, "_SYSTEM_PROMPT", "").strip()
    except Exception:
        return ""


def _get_active_prompt(agent_name: str) -> str:
    custom = _load_custom_prompts().get(agent_name)
    return custom if custom else _get_default_prompt(agent_name)


# ── HTML LOGIN ─────────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel Operativo — Eco Módulos IA</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:linear-gradient(135deg,#0a1a0f 0%,#0f2a18 100%);
     min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{background:rgba(26,46,32,0.95);border:1px solid #2d4a35;border-radius:20px;
      padding:44px 40px;max-width:400px;width:100%;text-align:center;
      box-shadow:0 20px 60px rgba(0,0,0,0.5)}
.logo{font-size:52px;margin-bottom:12px;filter:drop-shadow(0 4px 8px rgba(0,0,0,.4))}
h1{color:#4CAF50;font-size:22px;font-weight:800;margin-bottom:4px;letter-spacing:-0.3px}
.sub{color:#7a9e7e;font-size:13px;margin-bottom:32px}
.field{margin-bottom:14px;text-align:left}
.field label{display:block;font-size:11px;color:#7a9e7e;font-weight:700;
             text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
input{width:100%;background:#0f1f15;border:1.5px solid #2d4a35;
      border-radius:10px;padding:12px 15px;font-size:14px;
      color:#e0f0e3;outline:none;transition:border .2s,box-shadow .2s}
input:focus{border-color:#4CAF50;box-shadow:0 0 0 3px rgba(76,175,80,.15)}
button{width:100%;background:#1A5C38;color:white;border:none;
       border-radius:10px;padding:13px;font-size:15px;font-weight:700;
       cursor:pointer;transition:all .2s;margin-top:8px;letter-spacing:.3px}
button:hover{background:#2e7d32;transform:translateY(-1px);box-shadow:0 4px 16px rgba(26,92,56,.4)}
button:active{transform:translateY(0)}
.err{background:#3b1f1f;color:#ef9a9a;border:1px solid #c62828;border-radius:10px;
     padding:11px 14px;font-size:13px;margin-bottom:14px;display:none;text-align:left}
.footer{margin-top:24px;font-size:11px;color:#4a6e50}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🌿</div>
  <h1>Panel Operativo</h1>
  <p class="sub">Eco Módulos &amp; Piscinas — Sistema IA</p>
  <div class="err" id="err">❌ Credenciales incorrectas. Verificá tu email y contraseña.</div>
  <form id="f">
    <div class="field">
      <label>Email</label>
      <input type="email" id="email" placeholder="tu@email.com" autocomplete="username" autofocus>
    </div>
    <div class="field">
      <label>Contraseña</label>
      <input type="password" id="pw" placeholder="••••••••" autocomplete="current-password">
    </div>
    <button type="submit" id="btn">Ingresar al sistema →</button>
  </form>
  <p class="footer">15 agentes IA activos · Fly.io · Sistema operativo ✅</p>
</div>
<script>
document.getElementById('f').onsubmit = async function(e) {
  e.preventDefault();
  const btn = document.getElementById('btn');
  btn.textContent = 'Verificando...'; btn.disabled = true;
  const email = document.getElementById('email').value.trim();
  const pw    = document.getElementById('pw').value;
  const r = await fetch('/panel/check', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email, password: pw})
  });
  const d = await r.json();
  if (d.ok) {
    sessionStorage.setItem('eco_panel_pw', pw);
    sessionStorage.setItem('eco_panel_email', email);
    window.location.href = '/panel/home';
  } else {
    document.getElementById('err').style.display = 'block';
    document.getElementById('pw').value = '';
    btn.textContent = 'Ingresar al sistema →'; btn.disabled = false;
    document.getElementById('pw').focus();
  }
};
</script>
</body></html>"""


# ── HTML PANEL ─────────────────────────────────────────────────────────────

_PANEL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel Operativo — Eco Módulos IA</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0a1a0f;color:#e0f0e3;height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* ── TOPBAR ── */
.topbar{background:#111f15;border-bottom:1px solid #1e3a24;
        padding:0 20px;display:flex;align-items:center;gap:16px;height:52px;flex-shrink:0}
.topbar-logo{font-size:22px}
.topbar-title{font-size:14px;color:#4CAF50;font-weight:800;letter-spacing:-.2px}
.topbar-sub{font-size:11px;color:#4a6e50}
.topbar-right{margin-left:auto;display:flex;align-items:center;gap:6px}
.topbar-link{color:#4a6e50;text-decoration:none;font-size:12px;padding:5px 10px;
             border-radius:6px;transition:all .2s;border:1px solid transparent}
.topbar-link:hover{background:#1a2e20;border-color:#2d4a35;color:#a5d6a7}
.status-dot{width:7px;height:7px;border-radius:50%;background:#4CAF50;
            box-shadow:0 0 6px #4CAF50;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* ── LAYOUT ── */
.layout{display:flex;flex:1;overflow:hidden}

/* ── SIDEBAR ── */
.sidebar{width:210px;background:#0d1a10;border-right:1px solid #1e3a24;
         overflow-y:auto;flex-shrink:0;padding:8px 0}
.sidebar-section{padding:10px 14px 4px;font-size:9px;font-weight:800;
                 color:#3a5a40;text-transform:uppercase;letter-spacing:1px}
.agent-item{display:flex;align-items:center;gap:9px;padding:9px 14px;
            cursor:pointer;transition:all .15s;border-left:3px solid transparent}
.agent-item:hover{background:#122018;border-left-color:#2d4a35}
.agent-item.active{background:#1A5C38 !important;border-left-color:#4CAF50}
.agent-item.active .ag-name{color:#fff}
.ag-emoji{font-size:17px;width:24px;text-align:center;flex-shrink:0}
.ag-name{font-size:12px;font-weight:700;color:#b8d6ba}
.ag-rol{font-size:10px;color:#4a6e50;margin-top:1px}
.agent-item.active .ag-rol{color:#a5d6a7}

/* ── MAIN ── */
.main{flex:1;overflow-y:auto;display:flex;flex-direction:column}

/* ── AGENT HEADER ── */
.agent-header{background:#111f15;border-bottom:1px solid #1e3a24;
              padding:16px 24px;display:flex;align-items:center;gap:14px;flex-shrink:0}
.agent-avatar{font-size:32px;width:48px;height:48px;background:#0a1a0f;
              border-radius:12px;display:flex;align-items:center;justify-content:center;
              border:1px solid #2d4a35}
.agent-title h2{font-size:17px;color:#e8f5e9;font-weight:800}
.role-badge{display:inline-block;background:#0a2015;color:#4CAF50;border-radius:20px;
            padding:3px 10px;font-size:11px;font-weight:700;margin-top:4px;border:1px solid #1e5c28}
.model-badge{display:inline-block;background:#111f15;border:1px solid #2d4a35;
             color:#7a9e7e;border-radius:20px;padding:3px 10px;font-size:11px;margin-left:6px}
.custom-badge{display:inline-block;background:#2d1a0e;border:1px solid #bf360c;
              color:#ff8a65;border-radius:20px;padding:3px 10px;font-size:11px;margin-left:6px}
.canal-badge{margin-left:auto;font-size:11px;color:#4a6e50;
             background:#111f15;border:1px solid #1e3a24;border-radius:6px;padding:4px 10px}

/* ── TABS ── */
.tabs{display:flex;background:#0d1a10;border-bottom:1px solid #1e3a24;padding:0 20px;flex-shrink:0}
.tab{padding:10px 16px;font-size:12px;font-weight:700;color:#4a6e50;
     cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;letter-spacing:.2px}
.tab:hover{color:#a5d6a7}
.tab.active{color:#4CAF50;border-bottom-color:#4CAF50}

/* ── TAB CONTENT ── */
.tab-content{display:none;padding:20px 24px;flex:1}
.tab-content.active{display:flex;flex-direction:column;gap:16px}

/* ── SHORTCUTS ── */
.shortcuts-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.shortcut-btn{border:none;border-radius:10px;padding:13px 15px;cursor:pointer;
              text-align:left;transition:all .2s;display:flex;align-items:center;gap:10px;
              font-size:13px;font-weight:700;color:white;opacity:.92}
.shortcut-btn:hover{opacity:1;transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.4)}
.shortcut-btn:active{transform:translateY(0)}
.shortcuts-hint{font-size:11px;color:#4a6e50;margin-bottom:4px}

/* ── INFO ── */
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.info-card{background:#111f15;border:1px solid #1e3a24;border-radius:10px;padding:14px}
.info-card h4{font-size:10px;text-transform:uppercase;letter-spacing:.6px;
              color:#4a6e50;margin-bottom:8px;font-weight:800}
.info-card p{font-size:13px;color:#c8e6c9}
.func-list{list-style:none}
.func-list li{padding:6px 0;font-size:13px;color:#b8d6ba;
              border-bottom:1px solid #111f15;display:flex;gap:8px;align-items:flex-start}
.func-list li:last-child{border-bottom:none}
.func-list li::before{content:"→";color:#4CAF50;flex-shrink:0;margin-top:1px}
.hierarch{display:flex;flex-wrap:wrap;gap:7px;margin-top:4px}
.h-chip{background:#0a2015;color:#a5d6a7;border-radius:20px;padding:3px 10px;
        font-size:11px;cursor:pointer;border:1px solid #1e3a24;font-weight:700;transition:all .15s}
.h-chip:hover{background:#1A5C38;border-color:#4CAF50}

/* ── CHAT ── */
.chat-wrapper{display:flex;flex-direction:column;flex:1;min-height:0;gap:12px}
.chat-messages{flex:1;min-height:200px;max-height:380px;background:#070f09;
               border:1px solid #1e3a24;border-radius:12px;padding:16px;
               overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.msg-user{align-self:flex-end;background:#1A5C38;color:#fff;border-radius:16px 16px 4px 16px;
          padding:10px 14px;font-size:13px;max-width:78%;line-height:1.5;
          box-shadow:0 2px 8px rgba(0,0,0,.3)}
.msg-agent{align-self:flex-start;background:#111f15;color:#e0f0e3;
           border:1px solid #1e3a24;border-radius:16px 16px 16px 4px;
           padding:10px 14px;font-size:13px;max-width:82%;white-space:pre-wrap;
           line-height:1.5;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.msg-system{align-self:center;color:#3a5a40;font-size:11px;font-style:italic;
            padding:4px 12px;background:#0d1a10;border-radius:20px;border:1px solid #1e3a24}
.msg-name{font-size:10px;color:#4CAF50;font-weight:800;margin-bottom:3px}
.typing-dots{display:flex;gap:4px;padding:6px 0}
.typing-dots span{width:7px;height:7px;border-radius:50%;background:#4a6e50;
                  animation:bounce .8s infinite}
.typing-dots span:nth-child(2){animation-delay:.15s}
.typing-dots span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}

.chat-bottom{display:flex;gap:8px;align-items:flex-end}
.chat-input{flex:1;background:#0d1a10;border:1.5px solid #2d4a35;border-radius:12px;
            color:#e0f0e3;font-size:13px;padding:11px 14px;resize:none;outline:none;
            font-family:inherit;line-height:1.5;max-height:120px;min-height:44px;
            transition:border .2s}
.chat-input:focus{border-color:#4CAF50}
.send-btn{background:#1A5C38;color:white;border:none;border-radius:10px;
          padding:11px 18px;font-size:13px;font-weight:800;cursor:pointer;
          transition:all .2s;white-space:nowrap;height:44px}
.send-btn:hover{background:#2e7d32}
.chat-actions{display:flex;gap:6px;flex-wrap:wrap}
.chat-action-btn{background:#111f15;border:1px solid #2d4a35;color:#7a9e7e;
                 border-radius:6px;padding:5px 10px;font-size:11px;cursor:pointer;
                 transition:all .15s;font-weight:600}
.chat-action-btn:hover{background:#1a2e20;color:#c8e6c9;border-color:#4a6e50}

/* ── PROMPT ── */
.prompt-toolbar{display:flex;gap:8px;align-items:center}
.prompt-label{font-size:11px;color:#4a6e50;flex:1}
textarea.prompt-area{background:#070f09;border:1.5px solid #2d4a35;border-radius:10px;
  color:#c8e6c9;font-family:'SF Mono','Fira Code',monospace;font-size:11.5px;
  line-height:1.6;padding:14px;resize:vertical;min-height:360px;outline:none;width:100%;
  transition:border .2s}
textarea.prompt-area:focus{border-color:#4CAF50}
.save-status{font-size:12px;color:#4CAF50;display:none;font-weight:700}

/* ── HISTORY ── */
.hist-item{background:#111f15;border:1px solid #1e3a24;border-radius:10px;padding:14px;margin-bottom:10px}
.hist-meta{display:flex;gap:8px;margin-bottom:8px;align-items:center}
.hist-session{font-size:10px;color:#4a6e50;font-family:monospace}
.hist-canal{background:#0a2015;color:#4CAF50;border-radius:4px;padding:2px 7px;font-size:10px;font-weight:800}
.hist-user{color:#a5d6a7;font-size:13px;margin-bottom:5px}
.hist-reply{color:#4a6e50;font-size:12px;border-left:2px solid #1e3a24;padding-left:8px;margin-top:4px;line-height:1.5}

/* ── WELCOME ── */
.welcome{display:flex;flex-direction:column;align-items:center;justify-content:center;
         flex:1;gap:12px;color:#3a5a40;padding:40px}
.welcome .big{font-size:60px;filter:drop-shadow(0 4px 8px rgba(0,0,0,.4))}
.welcome h2{color:#4CAF50;font-size:20px;font-weight:800}
.welcome p{font-size:13px;max-width:400px;text-align:center;line-height:1.7;color:#4a6e50}

/* ── BUTTONS ── */
.btn{padding:7px 14px;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;
     border:none;transition:all .2s}
.btn-primary{background:#1A5C38;color:white}
.btn-primary:hover{background:#2e7d32}
.btn-danger{background:#2a0f0f;color:#ef9a9a;border:1px solid #c62828}
.btn-danger:hover{background:#c62828;color:white}
.btn-ghost{background:#111f15;color:#7a9e7e;border:1px solid #1e3a24}
.btn-ghost:hover{background:#1a2e20;color:#c8e6c9}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:#070f09}
::-webkit-scrollbar-thumb{background:#1e3a24;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#2d4a35}
</style>
</head>
<body>

<!-- TOPBAR -->
<div class="topbar">
  <span class="topbar-logo">🌿</span>
  <div>
    <div class="topbar-title">Eco Módulos &amp; Piscinas — Sistema IA</div>
    <div class="topbar-sub">15 agentes activos</div>
  </div>
  <div class="topbar-right">
    <span class="status-dot" title="Sistema operativo"></span>
    <a class="topbar-link" href="/admin">⚙️ Config</a>
    <a class="topbar-link" href="/dashboard">📊 Dashboard</a>
    <a class="topbar-link" href="/" >🏠 Inicio</a>
    <a class="topbar-link" href="#" onclick="logout()">Salir</a>
  </div>
</div>

<div class="layout">

  <!-- SIDEBAR -->
  <div class="sidebar" id="sidebar"></div>

  <!-- MAIN -->
  <div class="main" id="main">
    <div class="welcome">
      <div class="big">🤖</div>
      <h2>Seleccioná un agente</h2>
      <p>Hacé clic en cualquier agente del panel izquierdo para hablar con él, darle órdenes, editar su comportamiento o revisar su historial.</p>
    </div>
  </div>

</div>

<script>
const PW    = sessionStorage.getItem('eco_panel_pw') || '';
const EMAIL = sessionStorage.getItem('eco_panel_email') || '';
if (!PW) window.location.href = '/panel';

const AGENTS = __AGENTS_JSON__;
const ORDER  = __ORDER_JSON__;
let currentAgent = null;
let testHistory  = [];

// ── SIDEBAR ──────────────────────────────────────────────────────────────
function buildSidebar() {
  const sb = document.getElementById('sidebar');
  const sections = {
    '🏢 Dirección': ['maximo','aurora','tomas'],
    '💼 Vendedores': ['valentina','camila','mateo','nicolas','luciano'],
    '⚙️ Operaciones': ['renata','bruno','ezequiel','ignacio','elena','daniela','sebastian'],
  };
  let html = '';
  for (const [sec, ids] of Object.entries(sections)) {
    html += `<div class="sidebar-section">${sec}</div>`;
    for (const id of ids) {
      const a = AGENTS[id];
      html += `<div class="agent-item" id="item-${id}" onclick="selectAgent('${id}')">
        <span class="ag-emoji">${a.emoji}</span>
        <div>
          <div class="ag-name">${a.nombre}</div>
          <div class="ag-rol">${a.rol.split(' — ')[0].split(' y ')[0].substring(0,22)}</div>
        </div>
      </div>`;
    }
  }
  sb.innerHTML = html;
}

// ── SELECCIONAR AGENTE ────────────────────────────────────────────────────
async function selectAgent(name) {
  currentAgent = name;
  testHistory  = [];
  document.querySelectorAll('.agent-item').forEach(el => el.classList.remove('active'));
  document.getElementById('item-' + name)?.classList.add('active');
  await renderAgent(name);
}

async function renderAgent(name) {
  const a = AGENTS[name];
  const promptRes  = await fetch(`/panel/api/agents/${name}/prompt`, { headers:{'X-Panel-Password':PW} });
  const promptData = await promptRes.json();
  const prompt     = promptData.prompt  || '';
  const isCustom   = promptData.is_custom || false;

  const modelBadge  = `<span class="model-badge">⚡ ${a.modelo_key || 'flash'}</span>`;
  const customBadge = isCustom ? `<span class="custom-badge">✏️ Prompt editado</span>` : '';
  const supervisa   = a.supervisa.length
    ? a.supervisa.map(s=>`<span class="h-chip" onclick="selectAgent('${s}')">${AGENTS[s].emoji} ${AGENTS[s].nombre}</span>`).join('')
    : '<span style="color:#2d4a35;font-size:12px">—</span>';
  const reporta = a.reporta_a
    ? `<span class="h-chip" onclick="selectAgent('${a.reporta_a}')">${AGENTS[a.reporta_a].emoji} ${AGENTS[a.reporta_a].nombre}</span>`
    : '<span style="color:#2d4a35;font-size:12px">Solo a Rodrigo</span>';
  const funcItems = a.funciones.map(f=>`<li>${f}</li>`).join('');

  // Shortcuts — usar data-idx + listener (evita romper el HTML con comillas)
  const shortcutBtns = (a.shortcuts||[]).map((s, i) =>
    `<button class="shortcut-btn" data-sc-idx="${i}" style="background:${s.color}20;border:1px solid ${s.color}40;color:${s.color === '#fff' ? '#fff' : lightenColor(s.color)}">${s.label}</button>`
  ).join('');

  document.getElementById('main').innerHTML = `
    <div class="agent-header">
      <div class="agent-avatar">${a.emoji}</div>
      <div class="agent-title">
        <h2>${a.nombre}</h2>
        <div>${'<span class="role-badge">'+a.rol+'</span>'}${modelBadge}${customBadge}</div>
      </div>
      <span class="canal-badge">📡 ${a.canal}</span>
    </div>

    <div class="tabs">
      <div class="tab active"  onclick="switchTab('acciones')">⚡ Acciones</div>
      <div class="tab"         onclick="switchTab('chat')">💬 Conversar</div>
      <div class="tab"         onclick="switchTab('info')">📋 Info</div>
      <div class="tab"         onclick="switchTab('prompt')">✏️ Prompt</div>
      <div class="tab"         onclick="switchTab('history')">📂 Historial</div>
    </div>

    <!-- ACCIONES -->
    <div class="tab-content active" id="tab-acciones">
      <p class="shortcuts-hint">Tocá una acción para enviársela directamente a ${a.nombre} y ver su respuesta →</p>
      <div class="shortcuts-grid">${shortcutBtns}</div>
      <div id="shortcut-result" style="display:none">
        <div style="font-size:11px;color:#4a6e50;margin-bottom:8px">Respuesta de ${a.nombre}:</div>
        <div class="msg-agent" id="shortcut-reply" style="max-width:100%"></div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="btn btn-ghost" onclick="switchTab('chat');continueConversation('${name}')">
            💬 Continuar conversación
          </button>
          <button class="btn btn-ghost" onclick="document.getElementById('shortcut-result').style.display='none'">
            ✕ Cerrar
          </button>
        </div>
      </div>
    </div>

    <!-- CHAT -->
    <div class="tab-content" id="tab-chat">
      <div class="chat-wrapper">
        <div class="chat-messages" id="chat-msgs">
          <div class="msg-system">Iniciá la conversación con ${a.nombre}</div>
        </div>
        <div class="chat-actions" id="chat-quick"></div>
        <div class="chat-bottom">
          <textarea class="chat-input" id="chat-input"
            placeholder="Escribile a ${a.nombre}..." rows="2"></textarea>
          <button class="send-btn" onclick="sendChat('${name}')">Enviar ➤</button>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" style="font-size:11px" onclick="clearChat()">🗑 Limpiar chat</button>
          <button class="btn btn-ghost" style="font-size:11px" onclick="clearCache('${name}')">🔄 Limpiar caché</button>
        </div>
      </div>
    </div>

    <!-- INFO -->
    <div class="tab-content" id="tab-info">
      <div class="info-grid">
        <div class="info-card">
          <h4>Reporta a</h4>
          <div class="hierarch">${reporta}</div>
        </div>
        <div class="info-card">
          <h4>Supervisa</h4>
          <div class="hierarch">${supervisa}</div>
        </div>
        <div class="info-card">
          <h4>Canal de operación</h4>
          <p>${a.canal}</p>
        </div>
        <div class="info-card">
          <h4>Modelo IA</h4>
          <p>${a.modelo_key || 'Gemini Flash (default)'}</p>
        </div>
      </div>
      <div class="info-card">
        <h4>Funciones principales</h4>
        <ul class="func-list" style="margin-top:8px">${funcItems}</ul>
      </div>
    </div>

    <!-- PROMPT -->
    <div class="tab-content" id="tab-prompt">
      <div class="prompt-toolbar">
        <span class="prompt-label">${isCustom ? '✏️ Usando prompt personalizado' : '📄 Usando prompt del código'}</span>
        ${isCustom ? `<button class="btn btn-danger" onclick="resetPrompt('${name}')">↩ Restaurar default</button>` : ''}
        <button class="btn btn-primary" onclick="savePrompt('${name}')">💾 Guardar</button>
        <span class="save-status" id="save-status">✅ Guardado</span>
      </div>
      <textarea class="prompt-area" id="prompt-area">${escHtml(prompt)}</textarea>
      <p style="font-size:11px;color:#3a5a40;margin-top:6px">
        Los cambios se aplican en conversaciones nuevas. Usá "Limpiar caché" en la pestaña Conversar para afectar sesiones activas.
      </p>
    </div>

    <!-- HISTORIAL -->
    <div class="tab-content" id="tab-history">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;color:#4a6e50">Conversaciones recientes donde participó ${a.nombre}</span>
        <button class="btn btn-ghost" onclick="loadHistory('${name}')">🔄 Actualizar</button>
      </div>
      <div id="history-list">
        <div class="msg-system" style="margin-top:20px">Cargando historial desde CRM...</div>
      </div>
    </div>
  `;

  // Enlazar clicks de las tarjetas de acción (data-idx → mensaje real)
  document.querySelectorAll('#tab-acciones .shortcut-btn[data-sc-idx]').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.scIdx, 10);
      const sc  = (a.shortcuts || [])[idx];
      if (sc) sendShortcut(name, sc.msg);
    });
  });

  // Atajos rápidos en el chat
  buildQuickReplies(name);

  // Enter para enviar
  document.getElementById('chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(name); }
  });

  loadHistory(name);
}

// ── TABS ──────────────────────────────────────────────────────────────────
function switchTab(tab) {
  const tabNames = ['acciones','chat','info','prompt','history'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', tabNames[i] === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const el = document.getElementById('tab-' + tab);
  if (el) el.classList.add('active');
}

// ── SHORTCUTS ────────────────────────────────────────────────────────────
async function sendShortcut(name, msg) {
  const resultBox = document.getElementById('shortcut-result');
  const replyEl   = document.getElementById('shortcut-reply');
  resultBox.style.display = 'block';
  replyEl.textContent = '...';
  replyEl.style.fontStyle = 'italic';
  try {
    const r = await fetch(`/panel/api/agents/${name}/test`, {
      method:'POST', headers:{'Content-Type':'application/json','X-Panel-Password':PW},
      body: JSON.stringify({message:msg, history:[]})
    });
    const d = await r.json();
    replyEl.textContent = d.reply || d.error || '(sin respuesta)';
    replyEl.style.fontStyle = 'normal';
    // Guardar en historial de chat para poder continuar
    testHistory = [{role:'user',content:msg},{role:'assistant',content:d.reply||''}];
  } catch(e) {
    replyEl.textContent = '❌ Error: ' + e.message;
  }
  resultBox.scrollIntoView({behavior:'smooth', block:'nearest'});
}

function continueConversation(name) {
  // El historial ya tiene los mensajes del shortcut
  const box = document.getElementById('chat-msgs');
  if (testHistory.length >= 2) {
    box.innerHTML = '';
    addMsg(testHistory[0].content, 'user');
    addMsg(testHistory[1].content, 'agent', name);
  }
}

// ── CHAT ──────────────────────────────────────────────────────────────────
function buildQuickReplies(name) {
  const box = document.getElementById('chat-quick');
  if (!box) return;
  const a = AGENTS[name];
  const top = (a.shortcuts || []).slice(0, 3);
  box.innerHTML = top.map((s, i) =>
    `<button class="chat-action-btn" data-qr-idx="${i}">${s.label}</button>`
  ).join('');
  box.querySelectorAll('.chat-action-btn[data-qr-idx]').forEach(btn => {
    btn.addEventListener('click', () => {
      const sc = top[parseInt(btn.dataset.qrIdx, 10)];
      if (sc) fillChat(sc.msg);
    });
  });
}

function fillChat(msg) {
  const el = document.getElementById('chat-input');
  if (el) { el.value = msg; el.focus(); }
}

async function sendChat(name) {
  const input = document.getElementById('chat-input');
  const msg   = input.value.trim();
  if (!msg) return;
  input.value = '';
  input.style.height = 'auto';

  addMsg(msg, 'user');
  const typingEl = addTyping();

  try {
    const r = await fetch(`/panel/api/agents/${name}/test`, {
      method:'POST', headers:{'Content-Type':'application/json','X-Panel-Password':PW},
      body: JSON.stringify({message:msg, history:testHistory})
    });
    const d = await r.json();
    typingEl.remove();
    const actualAgent = d.agent || name;

    // Si hubo derivación, mostrar aviso de transición
    if (d.derivado_de && d.derivado_de !== actualAgent) {
      const fromInfo = AGENTS[d.derivado_de] || {};
      const toInfo   = AGENTS[actualAgent]   || {};
      const transMsg = d.derivacion_msg ||
        `${fromInfo.emoji||'💬'} ${fromInfo.nombre||d.derivado_de} te deriva con ${toInfo.emoji||'🤝'} ${toInfo.nombre||actualAgent}.`;
      const sysEl = document.createElement('div');
      sysEl.className = 'msg-system';
      sysEl.style.cssText = 'background:#1a2e20;border:1px solid #2d7a45;border-radius:8px;padding:8px 12px;font-size:12px;color:#7fbf8a;margin:4px 0;text-align:center';
      sysEl.textContent = '🔀 ' + transMsg;
      document.getElementById('chat-msgs').appendChild(sysEl);
    }

    addMsg(d.reply || d.error || '(sin respuesta)', 'agent', actualAgent);
    testHistory.push({role:'user',content:msg});
    testHistory.push({role:'assistant',content:d.reply||''});
    if (testHistory.length > 24) testHistory = testHistory.slice(-24);
  } catch(e) {
    typingEl.remove();
    addMsg('❌ Error: ' + e.message, 'agent', name);
  }
}

function addMsg(text, type, agentName) {
  const box = document.getElementById('chat-msgs');
  const d   = document.createElement('div');
  if (type === 'user') {
    d.className = 'msg-user';
    d.textContent = text;
  } else {
    d.className = 'msg-agent';
    if (agentName && AGENTS[agentName]) {
      const nameEl = document.createElement('div');
      nameEl.className = 'msg-name';
      nameEl.textContent = AGENTS[agentName].emoji + ' ' + AGENTS[agentName].nombre;
      d.appendChild(nameEl);
    }
    const textEl = document.createElement('div');
    textEl.textContent = text;
    d.appendChild(textEl);
  }
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

function addTyping() {
  const box = document.getElementById('chat-msgs');
  const d   = document.createElement('div');
  d.className = 'msg-agent';
  d.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

function clearChat() {
  testHistory = [];
  const box = document.getElementById('chat-msgs');
  if (box) box.innerHTML = '<div class="msg-system">Chat limpiado</div>';
}

// ── PROMPT ────────────────────────────────────────────────────────────────
async function savePrompt(name) {
  const prompt = document.getElementById('prompt-area').value;
  const r = await fetch(`/panel/api/agents/${name}/prompt`, {
    method:'POST', headers:{'Content-Type':'application/json','X-Panel-Password':PW},
    body: JSON.stringify({prompt})
  });
  const d = await r.json();
  if (d.ok) {
    const s = document.getElementById('save-status');
    s.style.display = 'inline';
    setTimeout(() => { s.style.display='none'; selectAgent(name); }, 2200);
  }
}

async function resetPrompt(name) {
  if (!confirm('¿Restaurar el prompt original del código para ' + AGENTS[name].nombre + '?')) return;
  await fetch(`/panel/api/agents/${name}/prompt/reset`, { method:'POST', headers:{'X-Panel-Password':PW} });
  selectAgent(name);
}

// ── HISTORIAL ─────────────────────────────────────────────────────────────
async function loadHistory(name) {
  const box = document.getElementById('history-list');
  if (!box) return;
  box.innerHTML = '<div class="msg-system" style="text-align:center;padding:24px">Consultando CRM...</div>';
  try {
    const r = await fetch(`/panel/api/agents/${name}/history`, { headers:{'X-Panel-Password':PW} });
    const d = await r.json();
    if (!d.conversations || !d.conversations.length) {
      box.innerHTML = '<div class="msg-system" style="text-align:center;padding:24px">No hay conversaciones recientes en el CRM para este agente.</div>';
      return;
    }
    box.innerHTML = d.conversations.map(c => `
      <div class="hist-item">
        <div class="hist-meta">
          <span class="hist-canal">${c.canal||'WA'}</span>
          <span class="hist-session">${c.session_id||''}</span>
          <span style="margin-left:auto;font-size:10px;color:#3a5a40">${c.fecha||''}</span>
        </div>
        <div class="hist-user">👤 ${escHtml(c.user_msg||'')}</div>
        <div class="hist-reply">🤖 ${escHtml(c.agent_reply||'')}</div>
      </div>`).join('');
  } catch(e) {
    box.innerHTML = `<div class="msg-system" style="text-align:center;padding:24px">CRM no disponible: ${e.message}</div>`;
  }
}

// ── CACHÉ ─────────────────────────────────────────────────────────────────
async function clearCache(name) {
  await fetch('/panel/api/cache/clear', {
    method:'POST', headers:{'Content-Type':'application/json','X-Panel-Password':PW},
    body: JSON.stringify({agent:name})
  });
  addMsg('🔄 Caché de sesiones activas limpiado.', 'agent', name);
}

// ── UTILS ─────────────────────────────────────────────────────────────────
function escHtml(t) {
  return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function lightenColor(hex) {
  // Devuelve el color un poco más claro para texto legible sobre fondo oscuro
  return hex; // Los colores ya son suficientemente brillantes para texto
}

function logout() {
  sessionStorage.removeItem('eco_panel_pw');
  sessionStorage.removeItem('eco_panel_email');
  window.location.href = '/panel';
}

// ── INIT ──────────────────────────────────────────────────────────────────
buildSidebar();
</script>
</body></html>"""


# ── RUTAS ──────────────────────────────────────────────────────────────────

@router.get("/panel", response_class=HTMLResponse)
async def panel_login():
    return _LOGIN_HTML


@router.post("/panel/check")
async def panel_check(request: Request):
    from auth import check_credentials, check_password
    body = await request.json()
    email    = body.get("email", "")
    password = body.get("password", "")
    # Si viene con email, validar email+password; si solo password (legacy), aceptar
    if email:
        ok = check_credentials(email, password)
    else:
        ok = check_password(password)
    return JSONResponse({"ok": ok})


@router.get("/panel/home", response_class=HTMLResponse)
async def panel_home():
    import json as _json
    agents_json = _json.dumps(AGENTS_INFO)
    order_json  = _json.dumps(AGENTS_ORDER)
    html = _PANEL_HTML \
        .replace("__AGENTS_JSON__", agents_json) \
        .replace("__ORDER_JSON__",  order_json)
    return html


# ── API: prompt ────────────────────────────────────────────────────────────

@router.get("/panel/api/agents/{name}/prompt")
async def api_get_prompt(name: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    if name not in AGENTS_INFO:
        return JSONResponse({"error": "agente no encontrado"}, status_code=404)
    custom    = _load_custom_prompts().get(name)
    is_custom = bool(custom)
    prompt    = custom if custom else _get_default_prompt(name)
    return JSONResponse({"prompt": prompt, "is_custom": is_custom})


@router.post("/panel/api/agents/{name}/prompt")
async def api_save_prompt(name: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
    if name not in AGENTS_INFO:
        return JSONResponse({"ok": False, "error": "agente no encontrado"}, status_code=404)
    body   = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt vacío"})
    try:
        _save_custom_prompt(name, prompt)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/panel/api/agents/{name}/prompt/reset")
async def api_reset_prompt(name: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"ok": False}, status_code=401)
    _delete_custom_prompt(name)
    return JSONResponse({"ok": True})


# ── API: test ──────────────────────────────────────────────────────────────

import re as _re
_DERIVAR_RE = _re.compile(r"\[DERIVAR:(\w+)\]", _re.IGNORECASE)
# Limpia cualquier señal interna que pudiera filtrarse al texto visible
# (LLAMADA_SUP, AGENDA_VV, y cualquier otra [XXX:...] que no sea de acción CRM).
_SIGNAL_LEAK_RE = _re.compile(
    r"\[(?:LLAMADA_SUP|AGENDA_VV|DERIVAR|ALERTA|NOTIF|SEGUIMIENTO|LEAD_CALIENTE|SIMULAR)[^\]]*\]",
    _re.IGNORECASE,
)


def _limpiar_señales_visibles(texto: str) -> str:
    return _SIGNAL_LEAK_RE.sub("", texto).strip()


@router.post("/panel/api/agents/{name}/test")
async def api_test_agent(name: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    if name not in AGENTS_INFO:
        return JSONResponse({"error": "agente no encontrado"}, status_code=404)
    body    = await request.json()
    message = body.get("message", "").strip()
    history = body.get("history", [])
    if not message:
        return JSONResponse({"error": "mensaje vacío"})
    try:
        from tools.crm_actions import detectar_acciones, limpiar_acciones, ejecutar_acciones

        info   = AGENTS_INFO[name]
        module = importlib.import_module(info["modulo"])
        agent  = module.get_agent()
        agent.history = history
        reply = await agent.respond(message)

        # ── Detectar derivación ──────────────────────────────────────────
        actual_agent = name
        derivacion_msg = None
        match = _DERIVAR_RE.search(reply)
        if match:
            nuevo = match.group(1).lower()
            if nuevo in AGENTS_INFO:
                actual_agent = nuevo
                # Guardar mensaje de transición antes de limpiar
                clean_reply = _limpiar_señales_visibles(limpiar_acciones(reply))
                derivacion_msg = clean_reply if clean_reply else None
                # Instanciar el agente nuevo y que tome el hilo
                nuevo_info   = AGENTS_INFO[nuevo]
                nuevo_module = importlib.import_module(nuevo_info["modulo"])
                nuevo_agent  = nuevo_module.get_agent()
                nuevo_agent.history = history
                reply = await nuevo_agent.respond(message)

        # ── Ejecutar acciones REALES emitidas por el agente ──────────────
        acciones = detectar_acciones(reply)
        acciones_ejecutadas = []
        resultado_acciones = ""
        if acciones:
            resultado_acciones = await ejecutar_acciones(acciones)
            acciones_ejecutadas = [a.get("tipo", "accion") for a in acciones]
            logger.info(f"[Panel] {name} ejecutó acciones reales: {acciones_ejecutadas}")

        # Simulador de cuotas exacto: reemplazar [SIMULAR:...] por el cálculo real
        try:
            from tools.cuota_sim import procesar_simulaciones
            reply = procesar_simulaciones(reply)
        except Exception:
            pass

        # Limpiar marcas internas (derivación + acciones + cualquier señal) de la respuesta visible
        reply = _limpiar_señales_visibles(limpiar_acciones(reply))
        if resultado_acciones:
            reply = f"{reply}\n\n{resultado_acciones}".strip()

        return JSONResponse({
            "reply":         reply,
            "agent":         actual_agent,
            "derivado_de":   name if actual_agent != name else None,
            "derivacion_msg": derivacion_msg,
            "acciones":      acciones_ejecutadas,
        })
    except Exception as e:
        logger.error(f"[Panel] Error testeando {name}: {e}")
        return JSONResponse({"reply": f"❌ Error al conectar con el agente: {e}", "agent": name})


# ── API: historial ─────────────────────────────────────────────────────────

@router.get("/panel/api/agents/{name}/history")
async def api_agent_history(name: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    try:
        from tools import crm_client
        leads = await crm_client.get_leads_sin_respuesta(0)
        agent_leads = [l for l in leads if l.get("agente_asignado","").lower() == name][:10]
        conversations = []
        for lead in agent_leads:
            sid  = lead.get("session_id") or lead.get("lead_id","")
            hist = await crm_client.get_conversation_history(sid, limit=3)
            if hist:
                lines = hist.strip().split("\n")
                conversations.append({
                    "session_id":  sid[:20] + "...",
                    "canal":       lead.get("canal_origen","WA"),
                    "fecha":       lead.get("updated_at",""),
                    "user_msg":    lines[0].replace("Cliente: ","") if lines else "",
                    "agent_reply": lines[1].replace(f"{name.capitalize()}: ","") if len(lines)>1 else "",
                })
        return JSONResponse({"conversations": conversations})
    except Exception as e:
        return JSONResponse({"conversations": [], "error": str(e)})


# ── API: caché ─────────────────────────────────────────────────────────────

@router.post("/panel/api/cache/clear")
async def api_clear_cache(request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"ok": False}, status_code=401)
    body = await request.json()
    try:
        from orchestrator.router import clear_agent_cache
        clear_agent_cache(lead_id=None)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ── API: lista de agentes ──────────────────────────────────────────────────

@router.get("/panel/api/agents")
async def api_list_agents(request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Panel-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    custom = _load_custom_prompts()
    result = [{"id":n,"nombre":AGENTS_INFO[n]["nombre"],"rol":AGENTS_INFO[n]["rol"],
               "canal":AGENTS_INFO[n]["canal"],"is_custom":n in custom} for n in AGENTS_ORDER]
    return JSONResponse({"agents": result})
