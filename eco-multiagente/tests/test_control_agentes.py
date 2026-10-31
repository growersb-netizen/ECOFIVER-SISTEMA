"""Control empresarial (Fase 2) en el multiagente: estados, horario y fallback de atención."""
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from orchestrator import router
from tools import control_agentes, contacto_comercial, crm_client

pytestmark = pytest.mark.control_real
TEL = "5491122222222"


def _crm(estados=None, salientes=None, status=200):
    estados = {a: "ACTIVO" for a in ("maximo", "aurora", "valentina", "camila", "franco")} | (estados or {})
    datos = {"estados": estados, "salientes_permitidos": salientes or {}, "en_horario": True}

    def handler(req):
        assert req.url.path == "/api/motor/control"
        return httpx.Response(status, json=datos)
    real = httpx.AsyncClient
    return patch.object(control_agentes.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.fixture(autouse=True)
def _limpio():
    control_agentes._reset_para_tests()
    yield
    control_agentes._reset_para_tests()


@pytest.mark.asyncio
async def test_saliente_permitido_solo_si_el_crm_lo_confirma():
    with _crm(salientes={"valentina": True}), \
         patch.object(crm_client, "autorizar_saliente", AsyncMock(return_value={"permitido": True})):
        assert await contacto_comercial.puede_contactar(TEL, "prueba")
    control_agentes._reset_para_tests()
    with _crm(salientes={"valentina": False}), \
         patch.object(crm_client, "autorizar_saliente", AsyncMock(return_value={"permitido": True})) as baja:
        assert not await contacto_comercial.puede_contactar(TEL, "prueba")
        baja.assert_not_awaited()                     # ni siquiera consulta: fuera de horario


@pytest.mark.asyncio
async def test_crm_caido_saliente_falla_cerrado():
    with _crm(status=503):
        assert await control_agentes.puede_iniciar_saliente("valentina") == (False, "sin confirmación del CRM")


@pytest.mark.asyncio
async def test_agente_pausado_no_inicia_salientes():
    with _crm(estados={"franco": "PAUSADO"}):
        assert await control_agentes.puede_iniciar_saliente("franco") == (False, "agente pausado")


@pytest.mark.asyncio
async def test_motor_solo_toma_tareas_de_agentes_activos():
    with _crm(estados={"camila": "PAUSADO", "aurora": "DESACTIVADO"}):
        activos = await control_agentes.agentes_para_tareas()
    assert "camila" not in activos and "aurora" not in activos and "maximo" in activos


@pytest.mark.asyncio
@pytest.mark.parametrize("estados,esperado", [
    ({}, "camila"),
    ({"camila": "PAUSADO"}, "valentina"),
    ({"camila": "DESACTIVADO", "valentina": "PAUSADO"}, None),
])
async def test_fallback_de_atencion_al_cliente(estados, esperado):
    with _crm(estados=estados):
        assert await control_agentes.agente_para_cliente("camila") == esperado


@pytest.mark.asyncio
async def test_entrante_24x7_aunque_el_crm_no_responda():
    with _crm(status=503):
        assert await control_agentes.agente_para_cliente("camila") == "camila"


@pytest.mark.asyncio
async def test_router_sin_agentes_activos_responde_sin_ia():
    llamadas = []

    class Agente:
        history = []

        async def respond(self, m, context=""):
            llamadas.append(m)
            return "x"
    sid = "5491100009999"
    router._agent_assignments.pop(sid, None)
    with _crm(estados={"valentina": "PAUSADO", "camila": "PAUSADO"}), \
         patch.object(router, "_get_agent_instance", return_value=Agente()), \
         patch.object(router, "crm_client") as crm, patch.object(router, "registrar_interaccion"), \
         patch.object(router, "_es_canal_aliados", AsyncMock(return_value=False)):
        crm.get_lead = AsyncMock(return_value={"id": 1, "agente_asignado": "camila", "telefono": sid})
        crm.get_conversation_history = AsyncMock(return_value="")
        crm.save_message = AsyncMock()
        r = await router.route_message("whatsapp", sid, "Hola, precio de la piscina", "text")
    router._agent_assignments.pop(sid, None)
    assert r["agent"] == "sistema" and llamadas == []
    crm.save_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_usa_valentina_si_el_asignado_esta_pausado():
    vistos = []

    def inst(sid, nombre):
        class A:
            history = []

            async def respond(self, m, context=""):
                vistos.append(nombre)
                return "Hola!"
        return A()
    sid = "5491100008888"
    router._agent_assignments.pop(sid, None)
    with _crm(estados={"camila": "PAUSADO"}), \
         patch.object(router, "_get_agent_instance", side_effect=inst), \
         patch.object(router, "crm_client") as crm, patch.object(router, "registrar_interaccion"), \
         patch.object(router, "_evaluar_y_alertar_lead", AsyncMock()), \
         patch.object(router, "_procesar_señales_agenda", AsyncMock()), \
         patch.object(router, "_procesar_señal_aliado", AsyncMock(return_value=None)), \
         patch.object(router, "_es_canal_aliados", AsyncMock(return_value=False)):
        crm.get_lead = AsyncMock(return_value={"id": 1, "agente_asignado": "camila", "telefono": sid})
        crm.get_conversation_history = AsyncMock(return_value="")
        crm.save_message = AsyncMock()
        crm.update_lead = AsyncMock(return_value=True)
        r = await router.route_message("whatsapp", sid, "Hola", "text")
    router._agent_assignments.pop(sid, None)
    assert r["agent"] == "valentina" and vistos == ["valentina"]
    crm.update_lead.assert_not_called()               # la asignación del CRM no cambia
