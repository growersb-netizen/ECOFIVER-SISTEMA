"""
Control Center del Sistema Multiagente — EcoFiver.

Permite enviar instrucciones al orquestador, monitorear el estado de los agentes
y ejecutar flujos predefinidos desde una interfaz centralizada dentro del CRM.

Configuración necesaria en ConfiguracionSistema:
  orquestador_url       → URL base del sistema multiagente (ej: https://eco-multiagente.fly.dev)
  orquestador_endpoint  → Endpoint de comandos (default: /api/comando)
  orquestador_api_key   → API Key para autenticación
"""
import asyncio
import httpx
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ComandoAgente, ConfiguracionSistema, Usuario
from routers.auth import require_auth, get_user_roles

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


# ─── CATÁLOGO DE AGENTES ──────────────────────────────────────────────────────
# 15 agentes especializados + 1 orquestador central

AGENTES_CATALOGO = [
    # ORQUESTADOR
    {
        "id": "orquestador",
        "nombre": "Claudio",
        "rol": "Orquestador Central",
        "area": "SISTEMA",
        "descripcion": "Distribuye tareas, coordina agentes y gestiona flujos complejos.",
        "icono": "🧠",
        "color": "#6366f1",
        "capacidades": ["Distribuir tareas", "Coordinar flujos multi-agente", "Reportes consolidados", "Escalamiento inteligente"],
    },
    # VENTAS (4)
    {
        "id": "pablo",
        "nombre": "Pablo",
        "rol": "Asesor de Apertura",
        "area": "VENTAS",
        "descripcion": "Recibe consultas de WhatsApp, califica leads y agenda videollamadas.",
        "icono": "🎯",
        "color": "#16a34a",
        "capacidades": ["Captar leads de WhatsApp", "Calificar prospectos", "Agendar VLs", "Cotizar productos"],
    },
    {
        "id": "laura",
        "nombre": "Laura",
        "rol": "Seguimiento de Leads",
        "area": "VENTAS",
        "descripcion": "Hace seguimiento automático de leads inactivos y programa recordatorios.",
        "icono": "📞",
        "color": "#22c55e",
        "capacidades": ["Seguimiento de leads fríos", "Reactivar prospectos inactivos", "Programar callbacks", "Actualizar estados CRM"],
    },
    {
        "id": "sabrina",
        "nombre": "Sabrina",
        "rol": "Cierre de Ventas",
        "area": "VENTAS",
        "descripcion": "Asiste en videollamadas y procesa cierres de ventas al contado y financiadas.",
        "icono": "💰",
        "color": "#f59e0b",
        "capacidades": ["Asistir en videollamadas", "Procesar ventas contado", "Registrar ventas financiadas", "Enviar contratos"],
    },
    {
        "id": "valentina",
        "nombre": "Valentina",
        "rol": "Post-Venta",
        "area": "VENTAS",
        "descripcion": "Gestiona satisfacción del cliente, reclamos y referidos.",
        "icono": "⭐",
        "color": "#ec4899",
        "capacidades": ["Encuestas de satisfacción", "Gestionar reclamos", "Solicitar referidos", "Postventa y garantías"],
    },
    # COBRANZAS (2)
    {
        "id": "carlos",
        "nombre": "Carlos",
        "rol": "Cobranzas",
        "area": "COBRANZAS",
        "descripcion": "Gestiona cuotas vencidas, envía recordatorios y registra pagos.",
        "icono": "💳",
        "color": "#ef4444",
        "capacidades": ["Detectar cuotas vencidas", "Enviar recordatorios de pago", "Registrar pagos recibidos", "Reportar morosos"],
    },
    {
        "id": "marina",
        "nombre": "Marina",
        "rol": "Acuerdos de Pago",
        "area": "COBRANZAS",
        "descripcion": "Negocia refinanciaciones y acuerdos especiales con clientes en mora.",
        "icono": "🤝",
        "color": "#f97316",
        "capacidades": ["Negociar refinanciaciones", "Proponer acuerdos especiales", "Gestionar mora avanzada", "Escalar a cobranza judicial"],
    },
    # LOGÍSTICA / CARGO (2)
    {
        "id": "diego",
        "nombre": "Diego",
        "rol": "Coordinación de Entregas",
        "area": "LOGISTICA",
        "descripcion": "Coordina entregas de instalación propia: equipo, flota y calendario.",
        "icono": "🚚",
        "color": "#06b6d4",
        "capacidades": ["Programar entregas", "Asignar equipo y vehículo", "Notificar clientes", "Registrar instalaciones"],
    },
    {
        "id": "ana",
        "nombre": "Ana",
        "rol": "Envíos Vía Cargo",
        "area": "LOGISTICA",
        "descripcion": "Gestiona envíos por transporte terrestre: empaque, despacho y seguimiento.",
        "icono": "📦",
        "color": "#8b5cf6",
        "capacidades": ["Crear envíos cargo", "Actualizar tracking", "Notificar estado al cliente", "Resolver problemas de entrega"],
    },
    # FÁBRICA (2)
    {
        "id": "marcos",
        "nombre": "Marcos",
        "rol": "Control de Producción",
        "area": "FABRICA",
        "descripcion": "Monitorea órdenes de producción, detecta retrasos y prioriza urgentes.",
        "icono": "⚙️",
        "color": "#64748b",
        "capacidades": ["Supervisar OPs activas", "Detectar retrasos", "Escalar urgentes", "Registrar avances de producción"],
    },
    {
        "id": "elena",
        "nombre": "Elena",
        "rol": "Gestión de Materiales",
        "area": "FABRICA",
        "descripcion": "Controla stock de materiales, genera pedidos y alerta por faltantes.",
        "icono": "🔩",
        "color": "#78716c",
        "capacidades": ["Alertar faltantes de materiales", "Generar pedidos de compra", "Actualizar stock", "Controlar recepción de materiales"],
    },
    # ADMINISTRACIÓN (2)
    {
        "id": "gabriel",
        "nombre": "Gabriel",
        "rol": "Reportes y Análisis",
        "area": "ADMIN",
        "descripcion": "Genera reportes ejecutivos, KPIs y análisis de negocio automáticos.",
        "icono": "📊",
        "color": "#3b82f6",
        "capacidades": ["Resumen ejecutivo diario", "KPIs de ventas y fábrica", "Análisis de rentabilidad", "Reporte de gastos por sector"],
    },
    {
        "id": "patricia",
        "nombre": "Patricia",
        "rol": "Control de Gastos",
        "area": "ADMIN",
        "descripcion": "Registra y categoriza gastos operativos, detecta anomalías.",
        "icono": "💸",
        "color": "#84cc16",
        "capacidades": ["Registrar gastos", "Clasificar por sector", "Detectar gastos fuera de rango", "Reportes de costo por entrega"],
    },
    # MARKETING (1)
    {
        "id": "sofia",
        "nombre": "Sofía",
        "rol": "Marketing y Redes",
        "area": "MARKETING",
        "descripcion": "Gestiona contenido para Instagram, MercadoLibre y el sitio web.",
        "icono": "📸",
        "color": "#a855f7",
        "capacidades": ["Publicar en Instagram", "Actualizar MercadoLibre", "Gestionar web CMS", "Responder consultas de ML"],
    },
    # SOPORTE (1)
    {
        "id": "rodrigo_ia",
        "nombre": "Rodrigo IA",
        "rol": "Asistente CEO",
        "area": "ADMIN",
        "descripcion": "Asistente personal del CEO: resúmenes, alertas y decisiones estratégicas.",
        "icono": "🤖",
        "color": "#0ea5e9",
        "capacidades": ["Resumen matutino al CEO", "Alertas críticas en tiempo real", "Recomendaciones estratégicas", "Acceso a todos los módulos"],
    },
]

# ─── MENÚ DE ACCIONES RÁPIDAS ─────────────────────────────────────────────────

ACCIONES_RAPIDAS = {
    "VENTAS": [
        {"id": "leads_sin_contactar", "titulo": "Listar leads sin contactar", "icono": "👥",
         "instruccion": "Listar todos los leads en estado NUEVO o NO_CONTACTADO. Enviar lista a Rodrigo con nombre, teléfono y fecha de creación. Asignar a Pablo para contactar hoy.",
         "agente": "pablo"},
        {"id": "seguimientos_vencidos", "titulo": "Seguimientos vencidos hoy", "icono": "⏰",
         "instruccion": "Identificar todos los leads con seguimiento programado para hoy o anterior sin gestionar. Notificar a cada asesor responsable y registrar en CRM.",
         "agente": "laura"},
        {"id": "pipeline_ventas", "titulo": "Resumen del pipeline", "icono": "📊",
         "instruccion": "Generar resumen del pipeline de ventas actual: leads por etapa, VLs agendadas esta semana, ventas cerradas este mes vs. mes anterior. Enviar reporte a Rodrigo.",
         "agente": "gabriel"},
        {"id": "ranking_vendedores", "titulo": "Ranking de vendedores", "icono": "🏆",
         "instruccion": "Calcular ranking de vendedores del mes actual por monto total de ventas cerradas (contado + financiadas). Mostrar top 5 con nombre y monto.",
         "agente": "gabriel"},
        {"id": "reactivar_leads_frios", "titulo": "Reactivar leads fríos (+30 días)", "icono": "🔥",
         "instruccion": "Identificar leads sin actividad por más de 30 días que estén en estado CONTACTADO o EN_SEGUIMIENTO. Enviar mensaje de reactivación personalizado por WhatsApp. Registrar gestión en CRM.",
         "agente": "laura"},
        {"id": "vls_semana", "titulo": "Estado de VLs de la semana", "icono": "📹",
         "instruccion": "Listar todas las videollamadas agendadas para los próximos 7 días. Confirmar con cada cliente 24hs antes vía WhatsApp. Reportar resultado.",
         "agente": "sabrina"},
    ],
    "COBRANZAS": [
        {"id": "cuotas_vencidas", "titulo": "Cuotas vencidas hoy", "icono": "🔴",
         "instruccion": "Listar todas las cuotas vencidas de ventas financiadas. Enviar recordatorio de pago por WhatsApp a cada cliente moroso. Registrar gestión de cobranza en CRM.",
         "agente": "carlos"},
        {"id": "morosos_criticos", "titulo": "Morosos críticos (+60 días)", "icono": "⚠️",
         "instruccion": "Identificar clientes con cuotas vencidas hace más de 60 días. Escalar a negociación de acuerdo especial. Proponer plan de regularización. Reportar a Rodrigo.",
         "agente": "marina"},
        {"id": "recaudacion_mes", "titulo": "Recaudación del mes", "icono": "💰",
         "instruccion": "Calcular total de pagos recibidos en el mes actual vs. total facturado en cuotas. Calcular tasa de cumplimiento. Generar reporte ejecutivo.",
         "agente": "gabriel"},
        {"id": "recordatorios_proximos", "titulo": "Recordatorios cuotas próximas", "icono": "📅",
         "instruccion": "Enviar recordatorio preventivo a todos los clientes con cuota que vence en los próximos 5 días. Mensaje amigable por WhatsApp.",
         "agente": "carlos"},
    ],
    "FABRICA": [
        {"id": "ops_activas", "titulo": "Estado de producción actual", "icono": "⚙️",
         "instruccion": "Listar todas las órdenes de producción activas con su estado actual, operario asignado y fecha estimada de término. Alertar las que estén retrasadas.",
         "agente": "marcos"},
        {"id": "ops_urgentes", "titulo": "OPs urgentes pendientes", "icono": "🚨",
         "instruccion": "Identificar todas las órdenes de producción marcadas como URGENTE que estén en estado PENDIENTE o EN_PROCESO. Asignar prioridad máxima y notificar al jefe de fábrica.",
         "agente": "marcos"},
        {"id": "materiales_faltantes", "titulo": "Alertas de materiales", "icono": "📦",
         "instruccion": "Revisar stock de todos los materiales. Identificar los que están por debajo del mínimo. Generar pedido de compra para los críticos y enviar lista a responsable de compras.",
         "agente": "elena"},
        {"id": "produccion_semana", "titulo": "Plan de producción semanal", "icono": "📋",
         "instruccion": "Generar plan de producción para los próximos 7 días basado en órdenes pendientes y capacidad de fábrica. Incluir materiales necesarios. Enviar a Rodrigo para aprobación.",
         "agente": "marcos"},
    ],
    "LOGISTICA": [
        {"id": "entregas_hoy", "titulo": "Entregas programadas hoy", "icono": "🚚",
         "instruccion": "Listar todas las entregas/instalaciones programadas para hoy. Confirmar con cada equipo asignado. Notificar a los clientes con horario estimado de llegada.",
         "agente": "diego"},
        {"id": "envios_cargo_estado", "titulo": "Estado de envíos Vía Cargo", "icono": "📦",
         "instruccion": "Revisar todos los envíos por transporte en estado DESPACHADO o EN_TRANSITO. Actualizar tracking. Notificar a clientes con novedades. Reportar los que tienen problema.",
         "agente": "ana"},
        {"id": "coordinar_semana", "titulo": "Coordinar entregas de la semana", "icono": "📅",
         "instruccion": "Revisar todas las ventas con fecha de instalación programada para esta semana. Confirmar disponibilidad de equipo y vehículo. Notificar a clientes. Reportar conflictos.",
         "agente": "diego"},
        {"id": "flota_disponible", "titulo": "Estado de la flota", "icono": "🚗",
         "instruccion": "Revisar disponibilidad de todos los vehículos de la flota para la semana. Identificar conflictos de asignación. Reportar a Rodrigo.",
         "agente": "diego"},
    ],
    "ADMIN": [
        {"id": "resumen_ejecutivo", "titulo": "Resumen ejecutivo del día", "icono": "📊",
         "instruccion": "Generar resumen ejecutivo completo del día: ventas cerradas, leads nuevos, producción activa, entregas realizadas, cobranzas recibidas, gastos del día. Enviar a Rodrigo vía WhatsApp.",
         "agente": "gabriel"},
        {"id": "gastos_mes", "titulo": "Gastos del mes por sector", "icono": "💸",
         "instruccion": "Calcular total de gastos del mes actual por sector (Ventas, Fábrica, Operaciones, Administración). Comparar con mes anterior. Identificar desvíos significativos.",
         "agente": "patricia"},
        {"id": "stock_disponible", "titulo": "Stock disponible para venta", "icono": "🏊",
         "instruccion": "Generar resumen de stock disponible: piscinas por modelo y color con cantidad y precio, paneles NCE con alertas de mínimo. Texto listo para compartir con asesores.",
         "agente": "pablo"},
        {"id": "kpis_semana", "titulo": "KPIs de la semana", "icono": "📈",
         "instruccion": "Calcular KPIs semanales: leads generados, tasa de conversión, ventas cerradas, monto total vendido, OPs completadas, entregas realizadas. Comparar con semana anterior.",
         "agente": "gabriel"},
    ],
    "MARKETING": [
        {"id": "actualizar_ml", "titulo": "Actualizar MercadoLibre", "icono": "🛒",
         "instruccion": "Revisar publicaciones activas en MercadoLibre. Actualizar stock según inventario actual. Responder preguntas pendientes. Reportar estado de cada publicación.",
         "agente": "sofia"},
        {"id": "publicar_instagram", "titulo": "Publicar en Instagram", "icono": "📸",
         "instruccion": "Generar contenido para publicar en Instagram hoy: imagen de producto con precio y descripción. Usar el catálogo actual. Programar para el horario de mayor engagement.",
         "agente": "sofia"},
        {"id": "actualizar_web", "titulo": "Actualizar precios en la web", "icono": "🌐",
         "instruccion": "Actualizar los precios y modelos disponibles en el sitio web según el catálogo actual del CRM. Verificar que los formularios de contacto estén funcionando.",
         "agente": "sofia"},
    ],
}

# ─── OBJETIVOS CEO ─────────────────────────────────────────────────────────────
# Flujos estratégicos multi-agente activados con un clic

OBJETIVOS_CEO = [
    {
        "id": "maximizar_ventas",
        "titulo": "🎯 Maximizar ventas este mes",
        "descripcion": "Activa todos los agentes de ventas: reactivación de leads fríos, seguimientos pendientes, confirmación de VLs y cierre de negociaciones activas.",
        "color": "#16a34a",
        "instruccion": """OBJETIVO CEO — MAXIMIZAR VENTAS DEL MES:
1. Pablo: Contactar todos los leads NUEVO sin gestión en las últimas 48hs.
2. Laura: Reactivar los 20 leads más antiguos en estado CONTACTADO o EN_SEGUIMIENTO sin actividad reciente.
3. Sabrina: Confirmar todas las videollamadas de la semana y preparar material de cierre.
4. Gabriel: Generar reporte del pipeline con leads más calientes para priorizar.
Prioridad: URGENTE. Reportar resultados a Rodrigo al final del día.""",
        "area": "VENTAS",
    },
    {
        "id": "reducir_morosidad",
        "titulo": "💳 Reducir deuda de cobranzas",
        "descripcion": "Activa los agentes de cobranzas para un operativo integral: recordatorios, negociaciones y registro de pagos.",
        "color": "#ef4444",
        "instruccion": """OBJETIVO CEO — REDUCIR MOROSIDAD:
1. Carlos: Enviar recordatorio de pago a TODOS los clientes con cuota vencida hoy o en los últimos 30 días.
2. Marina: Contactar a los 5 clientes con mayor deuda y proponer acuerdo de regularización.
3. Carlos: Registrar en CRM todos los compromisos de pago obtenidos.
4. Gabriel: Calcular monto total de deuda actual y proyección de recupero.
Prioridad: URGENTE. Reportar resultados a Rodrigo.""",
        "area": "COBRANZAS",
    },
    {
        "id": "optimizar_produccion",
        "titulo": "🏭 Optimizar producción",
        "descripcion": "Revisa el estado de fábrica, prioriza órdenes urgentes y gestiona materiales faltantes.",
        "color": "#78716c",
        "instruccion": """OBJETIVO CEO — OPTIMIZAR PRODUCCIÓN:
1. Marcos: Revisar todas las OPs activas y reordenar por prioridad (urgentes primero).
2. Elena: Generar lista de materiales faltantes para las OPs de esta semana. Crear pedidos de compra urgentes.
3. Marcos: Estimar fecha de término realista para cada OP activa y actualizar en sistema.
4. Gabriel: Reportar % de OPs en tiempo vs. retrasadas.
Prioridad: ALTA. Reportar a Rodrigo con plan de acción.""",
        "area": "FABRICA",
    },
    {
        "id": "operar_dia",
        "titulo": "☀️ Arrancar el día operativo",
        "descripcion": "Resumen matutino completo: producción, entregas del día, seguimientos y novedades de cobranzas.",
        "color": "#f59e0b",
        "instruccion": """ARRANQUE DIARIO — OPERATIVO COMPLETO:
1. Gabriel: Generar resumen ejecutivo del día con estado general del negocio.
2. Diego: Confirmar entregas e instalaciones programadas para hoy y notificar a los clientes.
3. Ana: Revisar envíos por cargo en tránsito y actualizar tracking.
4. Carlos: Enviar recordatorio a clientes con cuota que vence hoy.
5. Pablo: Asignar leads nuevos recibidos durante la noche a los asesores.
Enviar todo a Rodrigo vía WhatsApp antes de las 9:00 AM.""",
        "area": "GENERAL",
    },
    {
        "id": "cierre_semana",
        "titulo": "📅 Cierre de semana",
        "descripcion": "Consolida los resultados de la semana: ventas, producción, cobros, entregas y gastos.",
        "color": "#3b82f6",
        "instruccion": """CIERRE SEMANAL — REPORTE EJECUTIVO:
1. Gabriel: Consolidar KPIs de la semana: leads, ventas, monto, OPs completadas, entregas, cobros.
2. Gabriel: Comparar vs. semana anterior y mes en curso.
3. Patricia: Totalizar gastos de la semana por sector.
4. Todas las áreas: Reportar pendientes más importantes para la semana siguiente.
Enviar reporte completo a Rodrigo para revisión.""",
        "area": "ADMIN",
    },
    {
        "id": "emergencia_cliente",
        "titulo": "🚨 Atender emergencia de cliente",
        "descripcion": "Activa el protocolo de atención urgente: reclamo, seguimiento y resolución rápida.",
        "color": "#ef4444",
        "instruccion": """PROTOCOLO DE EMERGENCIA — ATENCIÓN URGENTE:
1. Valentina: Contactar al cliente de inmediato vía WhatsApp para escuchar el problema.
2. Valentina: Crear reclamo en el sistema con todos los detalles.
3. Diego/Ana (según tipo de entrega): Evaluar solución técnica y timeline de resolución.
4. Gabriel: Notificar a Rodrigo con el detalle del caso y solución propuesta.
Prioridad: MÁXIMA. Respuesta al cliente en menos de 2 horas.""",
        "area": "GENERAL",
    },
]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _get_config(db: Session, clave: str, default: str = "") -> str:
    cfg = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    return cfg.valor if cfg and cfg.valor else default


@router.get("/api/control-agentes/debug-orquestador-url")
async def debug_orquestador_url(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    corregir: bool = False,
):
    """Diagnóstico temporal (sin sesión): ver/corregir orquestador_url si quedó apuntando a Fly.io."""
    if not (x_api_key and x_api_key == API_KEY):
        raise HTTPException(403, "Sin permisos")
    cfg = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "orquestador_url").first()
    valor_actual = cfg.valor if cfg else None
    correcto = "https://eco-multiagente-production.up.railway.app"
    resultado = {"valor_en_bd": valor_actual, "valor_correcto": correcto, "coincide": valor_actual == correcto}
    if corregir and valor_actual != correcto:
        if cfg:
            cfg.valor = correcto
            cfg.estado = "activa"
        else:
            cfg = ConfiguracionSistema(clave="orquestador_url", valor=correcto, es_secreto=False, estado="activa")
            db.add(cfg)
        db.commit()
        resultado["corregido"] = True
    return resultado


def _comando_dict(c: ComandoAgente) -> dict:
    return {
        "id": c.id,
        "tipo": c.tipo,
        "area": c.area,
        "prioridad": c.prioridad,
        "titulo": c.titulo or c.instruccion[:60] + "…" if len(c.instruccion) > 60 else c.instruccion,
        "instruccion": c.instruccion,
        "agente_destino": c.agente_destino,
        "estado": c.estado,
        "respuesta": c.respuesta or "",
        "error_detalle": c.error_detalle or "",
        "http_status": c.http_status,
        "enviado_por": c.enviado_por.nombre if c.enviado_por else "",
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


async def _enviar_al_orquestador(instruccion: str, contexto: dict, prioridad: str,
                                   titulo: str, agente: str,
                                   orquestador_url: str, orquestador_endpoint: str,
                                   api_key: str) -> tuple[str, str, int]:
    """
    Intenta enviar la instrucción al orquestador vía HTTP.
    Retorna (estado, respuesta_texto, http_status).
    """
    url = orquestador_url.rstrip("/") + orquestador_endpoint
    payload = {
        "instruccion": instruccion,
        "titulo": titulo,
        "agente": agente,
        "prioridad": prioridad,
        "contexto": contexto,
        "origen": "crm_control_center",
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code < 300:
            return "ENVIADO", r.text[:500], r.status_code
        else:
            return "ERROR", f"HTTP {r.status_code}: {r.text[:300]}", r.status_code
    except httpx.ConnectError:
        return "ERROR", "No se pudo conectar al orquestador. Verificá la URL en Configuración.", 0
    except httpx.TimeoutException:
        return "ERROR", "Timeout: el orquestador no respondió en 10 segundos.", 0
    except Exception as e:
        return "ERROR", str(e)[:200], 0


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/control-agentes", response_class=HTMLResponse)
async def control_agentes_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = get_user_roles(current_user)
    orq_url = _get_config(db, "orquestador_url")
    return templates.TemplateResponse("control_agentes.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "agentes": AGENTES_CATALOGO,
        "acciones": ACCIONES_RAPIDAS,
        "objetivos_ceo": OBJETIVOS_CEO,
        "orquestador_configurado": bool(orq_url),
        "orquestador_url": orq_url,
    })


# ─── API: STATUS ──────────────────────────────────────────────────────────────

@router.get("/api/control-agentes/status")
async def get_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    orq_url = _get_config(db, "orquestador_url")
    orq_endpoint = _get_config(db, "orquestador_status_endpoint", "/health")
    api_key = _get_config(db, "orquestador_api_key")

    orquestador_online = False
    orquestador_respuesta = ""

    if orq_url:
        try:
            headers = {}
            if api_key:
                headers["X-Api-Key"] = api_key
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(orq_url.rstrip("/") + orq_endpoint, headers=headers)
            orquestador_online = r.status_code < 400
            orquestador_respuesta = r.text[:200] if orquestador_online else f"HTTP {r.status_code}"
        except Exception as e:
            orquestador_respuesta = str(e)[:100]

    # Comandos recientes para calcular actividad por agente
    hace_24h = datetime.utcnow() - timedelta(hours=24)
    recientes = db.query(ComandoAgente).filter(
        ComandoAgente.created_at >= hace_24h
    ).all()

    actividad = {}
    for c in recientes:
        ag = c.agente_destino or "orquestador"
        actividad[ag] = {
            "ultimo_comando": c.created_at.isoformat(),
            "estado": c.estado,
        }

    total_comandos = db.query(ComandoAgente).count()
    comandos_hoy = db.query(ComandoAgente).filter(
        ComandoAgente.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()

    return {
        "orquestador_online": orquestador_online,
        "orquestador_url": orq_url or "No configurado",
        "orquestador_respuesta": orquestador_respuesta,
        "configurado": bool(orq_url),
        "actividad_agentes": actividad,
        "total_comandos": total_comandos,
        "comandos_hoy": comandos_hoy,
        "agentes_total": len(AGENTES_CATALOGO),
    }


# ─── API: ENVIAR COMANDO ──────────────────────────────────────────────────────

@router.post("/api/control-agentes/comando")
async def enviar_comando(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    data = await request.json()
    instruccion = (data.get("instruccion") or "").strip()
    if not instruccion:
        raise HTTPException(400, "La instrucción no puede estar vacía")

    orq_url = _get_config(db, "orquestador_url")
    orq_endpoint = _get_config(db, "orquestador_endpoint", "/api/comando")
    api_key = _get_config(db, "orquestador_api_key")

    titulo = data.get("titulo") or instruccion[:80]
    agente = data.get("agente_destino") or "orquestador"
    prioridad = data.get("prioridad") or "NORMAL"
    tipo = data.get("tipo") or "LIBRE"
    area = data.get("area") or "GENERAL"

    # Crear registro en DB
    cmd = ComandoAgente(
        tipo=tipo,
        area=area,
        prioridad=prioridad,
        titulo=titulo,
        instruccion=instruccion,
        agente_destino=agente,
        contexto=data.get("contexto") or {},
        estado="PENDIENTE",
        enviado_por_id=current_user.id,
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)

    # Intentar enviar al orquestador si está configurado
    if orq_url:
        estado, respuesta, http_status = await _enviar_al_orquestador(
            instruccion=instruccion,
            contexto=data.get("contexto") or {},
            prioridad=prioridad,
            titulo=titulo,
            agente=agente,
            orquestador_url=orq_url,
            orquestador_endpoint=orq_endpoint,
            api_key=api_key,
        )
        cmd.estado = estado
        cmd.respuesta = respuesta
        cmd.http_status = http_status
        if estado == "ERROR":
            cmd.error_detalle = respuesta
    else:
        # Sin orquestador configurado: se guarda como "PENDIENTE" en cola local
        cmd.estado = "PENDIENTE"
        cmd.respuesta = "Guardado localmente. Configurá la URL del orquestador para envío automático."

    db.commit()
    return {"ok": True, "id": cmd.id, "estado": cmd.estado, "respuesta": cmd.respuesta}


# ─── API: HISTORIAL ───────────────────────────────────────────────────────────

@router.get("/api/control-agentes/historial")
async def get_historial(
    area: Optional[str] = None,
    tipo: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    q = db.query(ComandoAgente)
    if area:
        q = q.filter(ComandoAgente.area == area.upper())
    if tipo:
        q = q.filter(ComandoAgente.tipo == tipo.upper())
    comandos = q.order_by(ComandoAgente.created_at.desc()).limit(limit).all()
    return {"comandos": [_comando_dict(c) for c in comandos]}


# ─── API: CATÁLOGO ────────────────────────────────────────────────────────────

@router.get("/api/control-agentes/catalogo")
async def get_catalogo(current_user: Usuario = Depends(require_auth)):
    return {
        "agentes": AGENTES_CATALOGO,
        "acciones": ACCIONES_RAPIDAS,
        "objetivos_ceo": OBJETIVOS_CEO,
    }
