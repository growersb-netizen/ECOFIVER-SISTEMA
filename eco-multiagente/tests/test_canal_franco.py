"""Canal de WhatsApp de Franco: emisor (phone_id de Meta) y destinatario separados."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import franco_wa

PHONE_ID = "1037947576071396"     # formato de ID de Meta (no es un teléfono)
TEL = "5491135164644"

@pytest.fixture(autouse=True)
def _horario_autorizado():
    """Estas pruebas verifican otra compuerta; el horario/estado se prueba en test_control_agentes.py."""
    with patch("tools.control_agentes.puede_iniciar_saliente", AsyncMock(return_value=(True, ""))):
        yield



@pytest.fixture
def entorno(monkeypatch):
    for k in ("FRANCO_WA_PHONE_ID", "FRANCO_WHATSAPP_NUMBER"):
        monkeypatch.delenv(k, raising=False)
    envios = []

    async def fake(to, texto, phone_id=None, remitente="agente"):
        envios.append((to, phone_id))
        return True
    with patch("channels.whatsapp.enviar_mensaje_wa", side_effect=fake):
        yield monkeypatch, envios


def test_resolucion_del_emisor(entorno):
    mp, _ = entorno
    assert franco_wa.phone_id_franco() is None
    mp.setenv("FRANCO_WHATSAPP_NUMBER", TEL)              # un teléfono no sirve como emisor
    assert franco_wa.phone_id_franco() is None
    mp.setenv("FRANCO_WHATSAPP_NUMBER", PHONE_ID)         # compatibilidad: ya era un ID de Meta
    assert franco_wa.phone_id_franco() == PHONE_ID
    mp.setenv("FRANCO_WA_PHONE_ID", "999999999999999")     # la variable explícita manda
    assert franco_wa.phone_id_franco() == "999999999999999"


@pytest.mark.asyncio
async def test_sin_emisor_no_llama_a_meta(entorno):
    mp, envios = entorno
    mp.setenv("FRANCO_WHATSAPP_NUMBER", TEL)
    assert not await franco_wa.enviar_franco("5491100000000", "hola")
    assert envios == []


@pytest.mark.asyncio
async def test_envio_usa_emisor_y_destino_correctos(entorno):
    mp, envios = entorno
    mp.setenv("FRANCO_WA_PHONE_ID", PHONE_ID)
    assert await franco_wa.enviar_franco("5491100000000", "hola")
    assert envios == [("5491100000000", PHONE_ID)]


@pytest.mark.asyncio
async def test_aviso_a_aliados_nunca_se_envia_a_si_mismo(entorno):
    mp, envios = entorno
    from channels.telegram_bot import send_to_aliados_wa
    mp.setenv("FRANCO_WHATSAPP_NUMBER", PHONE_ID)          # emisor == destino (lo que pasaba antes)
    assert not await send_to_aliados_wa("material de la semana")
    mp.setenv("FRANCO_WA_PHONE_ID", PHONE_ID)
    mp.setenv("FRANCO_WHATSAPP_NUMBER", TEL)               # teléfono destino real, distinto del emisor
    assert await send_to_aliados_wa("material de la semana")
    assert envios == [(TEL, PHONE_ID)]


@pytest.mark.asyncio
async def test_reenganche_de_aliados_usa_el_emisor_resuelto(entorno):
    mp, envios = entorno
    mp.setenv("FRANCO_WA_PHONE_ID", PHONE_ID)
    from scheduler import cron
    franco = MagicMock(); franco.respond = AsyncMock(return_value="¡Hola! ¿Seguimos?")
    with patch("tools.crm_aliados.get_aliados_inactivos",
               AsyncMock(return_value=[{"telefono": TEL, "nombre": "Ana"}])), \
         patch("agents.franco.get_agent", return_value=franco):
        await cron.tarea_franco_reenganche_aliados()
    assert envios == [(TEL, PHONE_ID)]
