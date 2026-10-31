"""
Bajas comerciales: ningún contacto automático le escribe a quien pidió la baja.
Ejecutar: pytest tests/test_bajas_contacto_automatico.py -v
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import crm_client, contacto_comercial

CON_BAJA = "5491111111111"
SIN_BAJA = "5491122222222"

@pytest.fixture(autouse=True)
def _horario_autorizado():
    """Estas pruebas verifican otra compuerta; el horario/estado se prueba en test_control_agentes.py."""
    with patch("tools.control_agentes.puede_iniciar_saliente", AsyncMock(return_value=(True, ""))):
        yield



def _consulta(tel):
    return {CON_BAJA: True, SIN_BAJA: False}.get(tel)      # otro → None (CRM no confirmó)


def _autorizar(tel, origen="", agente="", **_):
    return {CON_BAJA: {"permitido": False, "motivo": "baja_comercial"}, SIN_BAJA: {"permitido": True}}.get(tel)


@pytest.fixture
def envios():
    """Simula WhatsApp, Valentina y la consulta de bajas. Devuelve la lista de teléfonos enviados."""
    enviados = []
    valentina = MagicMock()
    valentina.respond = AsyncMock(return_value="Hola! Soy Valentina de EcoFiver.")
    with patch.object(crm_client, "autorizar_saliente", AsyncMock(side_effect=_autorizar)), \
         patch("channels.whatsapp.send_whatsapp_message",
               AsyncMock(side_effect=lambda tel, msg, *a, **k: enviados.append(tel) or True)), \
         patch("agents.valentina.get_agent", return_value=valentina), \
         patch("asyncio.sleep", AsyncMock()):
        yield enviados


@pytest.mark.asyncio
async def test_compuerta_falla_cerrado():
    with patch.object(crm_client, "autorizar_saliente", AsyncMock(side_effect=_autorizar)):
        assert await contacto_comercial.puede_contactar(SIN_BAJA)
        assert not await contacto_comercial.puede_contactar(CON_BAJA)
        assert not await contacto_comercial.puede_contactar("5491199999999")   # CRM caído / sin respuesta


@pytest.mark.asyncio
async def test_consultar_baja_devuelve_none_si_el_crm_falla():
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=RuntimeError("caído"))):
        assert await crm_client.consultar_baja(CON_BAJA) is None


LEADS = [{"id": 1, "telefono": CON_BAJA, "nombre": "Ana", "estado": "NUEVO", "intentos_seguimiento": 0},
         {"id": 2, "telefono": SIN_BAJA, "nombre": "Beto", "estado": "NUEVO", "intentos_seguimiento": 0},
         {"id": 3, "telefono": "5491199999999", "nombre": "Caro", "estado": "NUEVO", "intentos_seguimiento": 0}]


@pytest.mark.asyncio
@pytest.mark.parametrize("tarea,fuente", [
    ("tarea_seguimiento_leads_frios", "get_leads_sin_respuesta"),
    ("tarea_contacto_leads_nuevos", "get_leads_nuevos_sin_contactar"),
    ("tarea_nutricion_24h", "get_leads_para_nutrir"),
    ("tarea_reactivacion_leads_frios", "get_leads_frios_para_reactivar"),
])
async def test_tareas_programadas_respetan_la_baja(envios, tarea, fuente):
    import datetime as dt
    from scheduler import cron

    class PrimerLunes(dt.datetime):                       # la reactivación corre el 1er lunes del mes
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 11, 2, 10, 0, tzinfo=tz)
    with patch.object(crm_client, fuente, AsyncMock(return_value=LEADS)), \
         patch.object(crm_client, "incrementar_intentos_seguimiento", AsyncMock(), create=True), \
         patch("datetime.datetime", PrimerLunes):
        await getattr(cron, tarea)()
    assert envios == [SIN_BAJA]


@pytest.mark.asyncio
async def test_accion_contactar_lead_bloqueada_aunque_la_pida_maximo(envios):
    from tools import crm_actions
    r = await crm_actions._contactar_lead({"telefono": CON_BAJA, "mensaje": "Promo!", "nombre": "Ana"})
    assert r.startswith("⛔") and envios == []
    r = await crm_actions._contactar_lead({"telefono": SIN_BAJA, "mensaje": "Hola", "nombre": "Beto"})
    assert r.startswith("✅") and envios == [SIN_BAJA]


@pytest.mark.asyncio
async def test_acciones_masivas_omiten_bajas(envios):
    from tools import crm_actions
    with patch.object(crm_client, "get_leads_sin_respuesta", AsyncMock(return_value=LEADS)), \
         patch.object(crm_client, "get_leads_frios_para_reactivar", AsyncMock(return_value=LEADS)):
        r = await crm_actions._contactar_leads_sin_respuesta({})
        assert "omitidos" in r
        await crm_actions._reactivar_leads_frios({})
    assert envios == [SIN_BAJA, SIN_BAJA]


@pytest.mark.asyncio
async def test_primer_contacto_meta_respeta_la_baja(envios):
    from channels import meta_leads
    with patch("orchestrator.router.route_message", AsyncMock(return_value={"reply": "", "agent": "valentina"})):
        await meta_leads._contactar_lead_wa({"telefono": CON_BAJA, "nombre": "Ana"})
        await meta_leads._contactar_lead_wa({"telefono": SIN_BAJA, "nombre": "Beto"})
    assert envios == [SIN_BAJA]


@pytest.mark.asyncio
async def test_scraper_respeta_la_baja(envios):
    from tools import lead_scraper
    await lead_scraper._contactar_lead_proactivo({"telefono": CON_BAJA})
    await lead_scraper._contactar_lead_proactivo({"telefono": SIN_BAJA})
    assert envios == [SIN_BAJA]


@pytest.mark.asyncio
async def test_cada_lead_del_lote_usa_un_agente_sin_historial_de_otro_cliente():
    """Antes: una sola Valentina para todo el lote → el mensaje a Beto llevaba el historial de Ana."""
    from scheduler import cron
    historias = []

    class Valentina:
        def __init__(self):
            self.history = []

        async def respond(self, message, context=""):
            historias.append(list(self.history))
            self.history.append(message)
            return "Hola!"
    leads = [{"id": i, "telefono": f"54911000000{i}", "nombre": n, "estado": "NUEVO"} for i, n in enumerate(["Ana", "Beto", "Caro"])]
    with patch.object(crm_client, "get_leads_nuevos_sin_contactar", AsyncMock(return_value=leads)), \
         patch("scheduler.cron.modo_contacto", AsyncMock(return_value="texto")), \
         patch("channels.whatsapp.send_whatsapp_message", AsyncMock(return_value=True)), \
         patch("agents.valentina.get_agent", side_effect=lambda: Valentina()), \
         patch("asyncio.sleep", AsyncMock()):
        await cron.tarea_contacto_leads_nuevos()
    assert historias == [[], [], []]
