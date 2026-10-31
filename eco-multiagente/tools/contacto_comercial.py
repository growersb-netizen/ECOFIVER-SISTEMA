"""
Compuerta de contactos comerciales automáticos (bajas registradas en el CRM).

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

from tools import crm_client

logger = logging.getLogger(__name__)

_stats = {"bloqueados_baja": 0, "bloqueados_sin_confirmar": 0, "permitidos": 0}


async def puede_contactar(telefono: str, origen: str = "") -> bool:
    excluido = await crm_client.consultar_baja(telefono)
    if excluido is None:
        _stats["bloqueados_sin_confirmar"] += 1
        logger.warning(f"[Contacto] {origen}: no se pudo confirmar la baja con el CRM → no se envía")
        return False
    if excluido:
        _stats["bloqueados_baja"] += 1
        logger.info(f"[Contacto] {origen}: contacto con baja comercial → no se envía")
        return False
    _stats["permitidos"] += 1
    return True


def stats() -> dict:
    return dict(_stats)
