"""
Identidad del cliente que llama al CRM con API key.

La API key general la comparten varios clientes (multiagente, MCP, Zapia,
scripts internos). El multiagente —los 16 agentes IA— se identifica:
  - con su clave propia AGENTES_IA_API_KEY (recomendado, cuando se configure), o
  - con el encabezado X-Origen-Cliente: multiagente (lo envía tools/crm_client).
A esa identidad se le niegan las operaciones reservadas a personas: registrar
pagos o cobros, confirmar entregas, crear o modificar ventas financiadas,
emitir contratos y liquidar comisiones. Un prompt no puede cambiar esto.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

ENCABEZADO = "X-Origen-Cliente"
VALOR_AGENTES = "multiagente"


def _clave_de(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Api-Key") or request.headers.get("X-API-Key") or "").strip()


def es_agente_ia(request: Request) -> bool:
    if (request.headers.get(ENCABEZADO) or "").strip().lower() == VALOR_AGENTES:
        return True
    propia = os.getenv("AGENTES_IA_API_KEY", "").strip()
    return bool(propia) and hmac.compare_digest(_clave_de(request), propia)


def negar_a_agentes_ia(request: Request) -> None:
    """Dependencia FastAPI para operaciones que solo puede hacer una persona."""
    if es_agente_ia(request):
        raise HTTPException(403, "Operación reservada a personas autorizadas: los agentes IA no pueden "
                                 "registrar pagos, cobros, entregas, financiaciones, contratos ni comisiones")
