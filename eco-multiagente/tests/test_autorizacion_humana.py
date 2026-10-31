"""La marca X-Autorizacion-Humana solo viaja cuando la operación la dictó el propietario o la aprobó una persona."""
import os

import httpx
import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import crm_actions, crm_client
from tools.action_policy import ActionContext


@pytest.fixture
def capturas(monkeypatch):
    vistas = []

    def handler(req):
        vistas.append(dict(req.headers))
        return httpx.Response(200, json={"ok": True, "cuotas_pagas": 1, "recibo": None})
    real = httpx.AsyncClient
    monkeypatch.setattr(crm_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return vistas


@pytest.mark.asyncio
async def test_canal_del_propietario_lleva_la_marca(capturas):
    await crm_actions.ejecutar_acciones([{"tipo": "pagar_cuota", "datos": {"venta_id": 9, "monto": 1000}}],
                                        ActionContext(agente="maximo", canal="confiable", origen="whatsapp_admin"))
    assert capturas[0]["x-autorizacion-humana"] == "canal:whatsapp_admin"
    assert capturas[0]["x-origen-cliente"] == "multiagente"


@pytest.mark.asyncio
async def test_aprobacion_humana_lleva_la_marca(capturas):
    await crm_actions.ejecutar_acciones([{"tipo": "pagar_cuota", "datos": {"venta_id": 9, "monto": 1000}}],
                                        ActionContext(agente="maximo", canal="confiable", origen="aprobacion:12",
                                                      extra={"aprobado_por": 1}))
    assert capturas[0]["x-autorizacion-humana"] == "aprobacion:aprobacion:12:usuario:1"


@pytest.mark.asyncio
async def test_sin_contexto_confiable_no_hay_marca_ni_envio(capturas):
    out = await crm_actions.ejecutar_acciones([{"tipo": "pagar_cuota", "datos": {"venta_id": 9, "monto": 1000, "lead_id": 3}}],
                                              ActionContext(agente="maximo", canal="cliente", lead_id=3, origen="whatsapp"))
    assert out.startswith("⛔") and capturas == []
    assert crm_client.autorizacion_humana.get() == ""
