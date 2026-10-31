"""
Compuerta de contactos comerciales automáticos: horario y estado del agente,
baja comercial, ventana de 24 h de WhatsApp (fuera de ella hace falta plantilla
aprobada por Meta) y deduplicación entre tareas — lo decide el CRM.

Todo envío que el sistema inicia por su cuenta a un cliente o lead —seguimientos,
nutrición, reactivación, primer contacto, contacto pedido a un agente interno—
pasa por puede_contactar() antes de enviar. Si el contacto pidió la baja, no se
envía. Si no se puede confirmar con el CRM, tampoco (falla cerrado: perder un
seguimiento cuesta menos que escribirle a quien pidió que no le escriban).

No aplica a responder cuando el contacto escribe por iniciativa propia, ni a
avisos contractuales (cuotas, videollamada agendada por el cliente).
"""
from __future__ import annotations

import logging
from typing import Optional

from tools import crm_client

logger = logging.getLogger(__name__)

_stats = {"bloqueados_baja": 0, "bloqueados_sin_confirmar": 0, "bloqueados_horario_o_estado": 0, "permitidos": 0}


async def modo_contacto(telefono: str, origen: str = "", agente: str = "valentina", plantilla: bool = False,
                        contractual: bool = False) -> Optional[str]:
    """'texto' (ventana de 24 h abierta), 'plantilla' (fuera de ella, plantillas habilitadas por el
    propietario) o None (no se envía). Lo comercial además exige agente activo y horario."""
    if not contractual:
        from tools.control_agentes import puede_iniciar_saliente
        permitido, motivo = await puede_iniciar_saliente(agente)
        if not permitido:
            _stats["bloqueados_horario_o_estado"] = _stats.get("bloqueados_horario_o_estado", 0) + 1
            logger.info(f"[Contacto] {origen}: {motivo} → no se envía")
            return None
    r = await crm_client.autorizar_saliente(telefono, origen, agente, con_plantilla=plantilla, contractual=contractual)
    if r is None:
        _stats["bloqueados_sin_confirmar"] += 1
        logger.warning(f"[Contacto] {origen}: no se pudo confirmar con el CRM → no se envía")
        return None
    if not r.get("permitido"):
        motivo = r.get("motivo", "no_autorizado")
        clave = {"baja_comercial": "bloqueados_baja"}.get(motivo, f"bloqueados_{motivo}")
        _stats[clave] = _stats.get(clave, 0) + 1
        logger.info(f"[Contacto] {origen}: {motivo} → no se envía")
        return None
    modo = r.get("modo", "texto")
    _stats["permitidos" if modo == "texto" else "plantillas"] = _stats.get(
        "permitidos" if modo == "texto" else "plantillas", 0) + 1
    return modo


async def puede_contactar(telefono: str, origen: str = "", agente: str = "valentina") -> bool:
    """Contacto comercial con texto libre: agente activo, horario, sin baja y dentro de la ventana de 24 h."""
    return await modo_contacto(telefono, origen, agente) == "texto"


def stats() -> dict:
    return dict(_stats)
