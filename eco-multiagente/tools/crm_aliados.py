"""
Cliente async para endpoints del módulo de Aliados en el CRM EcoFiver.
Contratos de integración definidos en FRANCO_spec_completa_v2.md, sección 9.1.
"""
import httpx
import logging
from tools.crm_client import CRM_BASE_URL, HEADERS, TIMEOUT

logger = logging.getLogger(__name__)


async def get_aliado(codigo: str) -> dict:
    """Datos + estado de un aliado por código."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{CRM_BASE_URL}/api/aliados/{codigo}", headers=HEADERS)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_aliado({codigo}) falló: {e}")
        return {}


async def get_aliado_ventas(codigo: str) -> list:
    """Historial de ventas del aliado."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{CRM_BASE_URL}/api/aliados/{codigo}/ventas", headers=HEADERS)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_aliado_ventas({codigo}) falló: {e}")
        return []


async def get_aliado_comisiones(codigo: str) -> list:
    """Comisiones pendientes y liquidadas del aliado."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{CRM_BASE_URL}/api/aliados/{codigo}/comisiones", headers=HEADERS)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_aliado_comisiones({codigo}) falló: {e}")
        return []


async def create_aliado(data: dict) -> dict:
    """Alta de aliado post-aprobación de postulación."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{CRM_BASE_URL}/api/aliados", headers=HEADERS, json=data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] create_aliado falló: {e}")
        return {}


async def create_lead_aliado(data: dict) -> dict:
    """Nuevo lead con aliado_codigo."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{CRM_BASE_URL}/api/leads", headers=HEADERS, json=data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] create_lead_aliado falló: {e}")
        return {}


async def check_dni_duplicado(dni: str) -> dict:
    """
    Verifica si el DNI ya existe asociado a otro aliado en el CRM.
    Retorna {"duplicado": True/False, "aliado_codigo": "..."}.
    Resultado positivo → caso 🔴 automático según sección 8.4.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/leads/check-dni/{dni}",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] check_dni_duplicado({dni}) falló: {e}")
        return {"duplicado": False}


async def get_ranking_aliados(periodo: str = "semana") -> list:
    """Ranking de aliados por periodo ('semana' o 'mes')."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/aliados/ranking",
                headers=HEADERS,
                params={"periodo": periodo},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_ranking_aliados({periodo}) falló: {e}")
        return []


async def get_aliados_inactivos(dias: int = 14) -> list:
    """Lista de aliados sin actividad en los últimos N días (para re-enganche)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/aliados",
                headers=HEADERS,
                params={"inactivos_dias": dias},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_aliados_inactivos({dias}d) falló: {e}")
        return []


async def get_aliados_activos() -> list:
    """Lista de aliados con estado 'activo' (para resumen mensual)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/aliados",
                headers=HEADERS,
                params={"estado": "activo"},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_aliados_activos falló: {e}")
        return []


async def log_paquete_auditoria(data: dict) -> bool:
    """
    Registra cada paquete 🟡 enviado a Rodrigo: timestamp, contenido, resultado.
    Protege a Rodrigo en caso de disputa sobre tiempos de respuesta (sección 8.3).
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{CRM_BASE_URL}/api/auditoria/paquete",
                headers=HEADERS,
                json=data,
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"[CRM/aliados] log_paquete_auditoria falló: {e}")
        return False


async def get_solicitudes_pendientes() -> list:
    """Cola de paquetes 🟡 activos pendientes de verificación por Rodrigo."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{CRM_BASE_URL}/api/solicitudes/pendientes-verificacion",
                headers=HEADERS,
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"[CRM/aliados] get_solicitudes_pendientes falló: {e}")
        return []
