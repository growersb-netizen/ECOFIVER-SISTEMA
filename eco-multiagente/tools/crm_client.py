"""
Cliente async para el CRM EcoFiver (FastAPI en Fly.io).
Si el CRM no está disponible, retorna datos vacíos para no romper el flujo.
"""

import httpx
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CRM_BASE_URL = os.getenv("CRM_BASE_URL", "https://eco-crm-dawn-fog-5476.fly.dev")
CRM_API_KEY = os.getenv("CRM_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {CRM_API_KEY}",
    "Content-Type": "application/json",
}

TIMEOUT = 10.0


async def get_lead(session_id: str) -> dict:
    """Obtiene un lead por session_id (teléfono o UUID de sesión web)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/by-session/{session_id}",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_lead({session_id}) falló: {e}")
        return {}


async def create_lead(data: dict) -> dict:
    """Crea un nuevo lead en el CRM (idempotente — retorna el existente si ya existe)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/leads/agent",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] create_lead falló: {e}")
        return {"session_id": data.get("session_id", "unknown"), "agente_asignado": "valentina", "error": str(e)}


async def update_lead(session_id: str, data: dict) -> bool:
    """Actualiza campos de un lead existente."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.patch(
                f"{CRM_BASE_URL}/api/leads/by-session/{session_id}",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] update_lead({session_id}) falló: {e}")
        return False


async def get_conversation_history(session_id: str, limit: int = 20) -> str:
    """
    Devuelve el historial de conversación como texto formateado.
    Retorna string vacío si no hay historial o el CRM no responde.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/by-session/{session_id}/messages",
                headers=HEADERS,
                params={"limit": limit},
            )
            r.raise_for_status()
            messages = r.json()
            if not messages:
                return ""
            lines = []
            for m in messages:
                lines.append(f"Cliente: {m.get('user_msg', '')}")
                lines.append(f"{m.get('agent_name', 'Agente')}: {m.get('agent_reply', '')}")
            return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[CRM] get_conversation_history({session_id}) falló: {e}")
        return ""


async def save_message(
    lead_id: str,
    user_msg: str,
    agent_reply: str,
    agent_name: str,
    msg_type: str = "text",
) -> bool:
    """Guarda un intercambio de mensajes en el CRM."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/leads/by-session/{lead_id}/messages",
                headers=HEADERS,
                json={
                    "user_msg": user_msg,
                    "agent_reply": agent_reply,
                    "agent_name": agent_name,
                    "msg_type": msg_type,
                },
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] save_message({lead_id}) falló: {e}")
        return False


async def get_leads_sin_respuesta(horas: int) -> list:
    """Devuelve leads sin respuesta hace más de N horas."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/sin-respuesta",
                headers=HEADERS,
                params={"horas": horas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_leads_sin_respuesta falló: {e}")
        return []


async def get_cuotas_vencidas(dias: int) -> list:
    """Devuelve cuotas vencidas hace más de N días."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/cuotas/vencidas",
                headers=HEADERS,
                params={"dias": dias},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_cuotas_vencidas falló: {e}")
        return []


async def get_pipeline_stats() -> dict:
    """Devuelve estadísticas del pipeline de ventas."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/stats/pipeline",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_pipeline_stats falló: {e}")
        return {
            "leads_recibidos": 0,
            "leads_calificados": 0,
            "cierres_contado": 0,
            "monto_contado": 0,
            "videollamadas": 0,
            "cuotas_cobradas": 0,
            "monto_cuotas": 0,
            "cuotas_vencidas": 0,
            "leads_web": 0,
            "publicaciones": 0,
        }


async def get_stock() -> dict:
    """Devuelve estado de stock actual."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/stock",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_stock falló: {e}")
        return {}


async def get_ventas_hoy() -> dict:
    """Devuelve resumen de ventas del día."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/stats/ventas-hoy",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_ventas_hoy falló: {e}")
        return {
            "cierres": 0,
            "monto_total": 0,
            "leads_nuevos": 0,
        }


async def simular_cuotas(tipo: str, precio: float, cuotas: int = None) -> dict:
    """
    Simulación de cuotas con la fórmula propia de EcoFiver.
    tipo: MODULO | PISCINA
    precio: precio de contado en ARS
    cuotas: número de cuotas (si None, devuelve tabla completa)
    """
    try:
        params = {"tipo": tipo, "precio": precio}
        if cuotas:
            params["cuotas"] = cuotas
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/simulador/cuotas",
                params=params,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] simular_cuotas falló: {e}")
        # Cálculo local de fallback
        factor = 2.0 if tipo.upper() == "MODULO" else 1.5
        if cuotas:
            cuota = precio / (cuotas + factor)
            ingreso = factor * cuota
            return {
                "tipo": tipo,
                "precio_contado": precio,
                "cuotas": cuotas,
                "cuota_mensual": round(cuota),
                "ingreso_inicial": round(ingreso),
                "total": round(ingreso + cuota * cuotas),
            }
        tabla = []
        for n in [6, 12, 18, 24, 36, 48]:
            c = precio / (n + factor)
            ing = factor * c
            tabla.append({"cuotas": n, "cuota_mensual": round(c), "ingreso_inicial": round(ing)})
        return {"tipo": tipo, "precio_contado": precio, "tabla": tabla}


async def get_precios_actuales() -> dict:
    """Obtiene el catálogo de productos con precios actuales (endpoint público)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{CRM_BASE_URL}/api/catalogo/publico")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_precios_actuales falló: {e}")
        return {"piscinas": {"modelos": [], "precios": {}}, "modulos": {"superficies_m2": [], "precios": {}}}


async def incrementar_intentos_seguimiento(lead_id: int) -> bool:
    """Incrementa el contador de intentos de seguimiento de un lead."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/leads/{lead_id}/incrementar-seguimiento",
                headers=HEADERS,
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] incrementar_intentos_seguimiento({lead_id}) falló: {e}")
        return False


# ── VIDEOLLAMADAS ────────────────────────────────────────────────────────────

async def get_videollamadas_proximas(horas: int = 2) -> list:
    """Devuelve videollamadas programadas en las próximas N horas."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/videollamadas/proximas",
                headers=HEADERS,
                params={"horas": horas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_videollamadas_proximas falló: {e}")
        return []


async def agendar_videollamada(
    lead_id: str,
    fecha_hora: str,
    tipo: str = "videollamada",
    agente: str = "",
) -> dict:
    """Registra una videollamada o llamada supervisora en el CRM."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/videollamadas",
                headers=HEADERS,
                json={
                    "lead_id":    lead_id,
                    "fecha_hora": fecha_hora,
                    "tipo":       tipo,
                    "agente":     agente,
                },
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] agendar_videollamada({lead_id}) falló: {e}")
        return {"ok": False, "error": str(e)}


async def get_llamadas_supervisora_pendientes() -> list:
    """Devuelve leads con llamada de supervisora pendiente de confirmación."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/videollamadas/supervisora-pendientes",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_llamadas_supervisora_pendientes falló: {e}")
        return []


# ── CAPTACIÓN AUTOMÁTICA DE LEADS ──────────────────────────────────────────

async def get_leads_nuevos_sin_contactar(minutos: int = 30) -> list:
    """
    Devuelve leads creados en los últimos N minutos que aún no recibieron
    primer mensaje del sistema (intentos_seguimiento == 0, sin reply del agente).
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/nuevos-sin-contactar",
                headers=HEADERS,
                params={"minutos": minutos},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_leads_nuevos_sin_contactar falló: {e}")
        return []


async def get_leads_para_nutrir(horas_desde: int = 20, horas_hasta: int = 30) -> list:
    """
    Devuelve leads que tienen entre N y M horas desde su último contacto
    y están en estado activo — listos para recibir contenido de nutrición a las 24hs.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/para-nutrir",
                headers=HEADERS,
                params={"horas_desde": horas_desde, "horas_hasta": horas_hasta},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_leads_para_nutrir falló: {e}")
        return []


async def get_leads_frios_para_reactivar(dias_inactivo: int = 30) -> list:
    """
    Devuelve leads en estado FRIO sin contacto en los últimos N días
    para campaña de reactivación mensual.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/frios-reactivar",
                headers=HEADERS,
                params={"dias": dias_inactivo},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_leads_frios_para_reactivar falló: {e}")
        return []


async def registrar_lead_meta(data: dict) -> dict:
    """
    Registra un lead proveniente de Meta Lead Ads o Instagram DM.
    Acepta: nombre, telefono, email, producto_interes, canal_origen, meta_lead_id.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/leads/meta",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] registrar_lead_meta falló: {e}")
        # Fallback: crear como lead normal
        return await create_lead({
            "session_id":      data.get("meta_lead_id", data.get("telefono", "meta_unknown")),
            "canal_origen":    data.get("canal_origen", "meta_ads"),
            "agente_asignado": "valentina",
            "estado":          "nuevo",
            "nombre":          data.get("nombre", ""),
            "telefono":        data.get("telefono", ""),
            "email":           data.get("email", ""),
        })


# ══════════════════════════════════════════════════════════════════════════════
# ESCRITURA / ACCIONES ADMIN
# Usadas por el control del CRM via WhatsApp con Máximo
# ══════════════════════════════════════════════════════════════════════════════

async def registrar_venta_contado(data: dict) -> dict:
    """Registra una venta al contado."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/ventas-contado",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] registrar_venta_contado falló: {e}")
        return {"error": str(e)}


async def registrar_venta_financiada(data: dict) -> dict:
    """Registra una venta financiada."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/ventas-financiadas",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] registrar_venta_financiada falló: {e}")
        return {"error": str(e)}


async def pagar_cuota(venta_id: int, monto: float, notas: str = "") -> bool:
    """Registra el pago de una cuota de una venta financiada."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/ventas-financiadas/{venta_id}/pago",
                headers=HEADERS,
                json={"monto": monto, "notas": notas},
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] pagar_cuota({venta_id}) falló: {e}")
        return False


async def agregar_stock_piscina(data: dict) -> dict:
    """Agrega stock de piscinas (modelo/color/cantidad)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/fabrica/stock-piscinas",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] agregar_stock_piscina falló: {e}")
        return {"error": str(e)}


async def movimiento_material(mat_id: int, tipo: str, cantidad: float, motivo: str) -> bool:
    """
    Registra un movimiento de inventario de materiales.
    tipo: ENTRADA | SALIDA
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/materiales/inventario/{mat_id}/movimiento",
                headers=HEADERS,
                json={"tipo": tipo, "cantidad": cantidad, "motivo": motivo},
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] movimiento_material({mat_id}, {tipo}) falló: {e}")
        return False


async def update_lead_by_id(lead_id: int, data: dict) -> bool:
    """Actualiza un lead por su ID numérico."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.put(
                f"{CRM_BASE_URL}/api/leads/{lead_id}",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] update_lead_by_id({lead_id}) falló: {e}")
        return False


async def registrar_gestion_cobranza(venta_id: int, canal: str, resultado: str, notas: str) -> bool:
    """Registra una gestión de cobranza sobre una venta financiada."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/cobranzas/{venta_id}/gestion",
                headers=HEADERS,
                json={"canal": canal, "resultado": resultado, "notas": notas},
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM] registrar_gestion_cobranza({venta_id}) falló: {e}")
        return False


async def get_materiales_inventario() -> list:
    """Obtiene el inventario completo de materiales."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/materiales/inventario",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_materiales_inventario falló: {e}")
        return []


async def get_ventas_financiadas_activas() -> list:
    """Obtiene ventas financiadas activas."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/ventas-financiadas",
                headers=HEADERS,
                params={"estado": "activa"},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_ventas_financiadas_activas falló: {e}")
        return []


async def get_stock_piscinas() -> list:
    """Obtiene el stock actual de piscinas en fábrica."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/fabrica/stock-piscinas",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_stock_piscinas falló: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXTO COMPLETO — DATOS PARA MÁXIMO ADMIN
# ══════════════════════════════════════════════════════════════════════════════

TIMEOUT_FULL = 20.0  # más tiempo para consultas pesadas


async def get_todos_leads(limit: int = 200) -> dict:
    """Obtiene todos los leads (paginados), ordenados por más recientes."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_FULL) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads",
                headers=HEADERS,
                params={"limit": limit, "skip": 0},
            )
            r.raise_for_status()
            return r.json()  # {"total": N, "leads": [...]}
    except Exception as e:
        logger.warning(f"[CRM] get_todos_leads falló: {e}")
        return {"total": 0, "leads": []}


async def get_ventas_contado_todas() -> list:
    """Obtiene todas las ventas al contado."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_FULL) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/ventas-contado",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_ventas_contado_todas falló: {e}")
        return []


async def get_ventas_financiadas_todas() -> list:
    """Obtiene todas las ventas financiadas (todos los estados)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_FULL) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/ventas-financiadas",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_ventas_financiadas_todas falló: {e}")
        return []


async def get_metricas_avanzadas() -> dict:
    """Obtiene métricas avanzadas del dashboard (funnel, ticket promedio, performance)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_FULL) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/dashboard/metricas-avanzadas",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_metricas_avanzadas falló: {e}")
        return {}


async def get_ranking_ventas(periodo: str = "mes") -> dict:
    """Obtiene el ranking de ventas por vendedor/asesor."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_FULL) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/dashboard/ranking",
                headers=HEADERS,
                params={"periodo": periodo},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM] get_ranking_ventas falló: {e}")
        return {}
