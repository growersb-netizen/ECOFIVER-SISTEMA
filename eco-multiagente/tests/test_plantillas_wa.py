"""Plantillas de WhatsApp fuera de la ventana de 24 h: formato para Meta, flujos que las usan y límites."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import contacto_comercial, crm_client, plantillas_wa

FUERA = "5491133333333"


@pytest.mark.asyncio
async def test_payload_de_plantilla_para_meta_y_registro_en_inbox(monkeypatch):
    enviados, inbox = [], []

    def handler(req):
        enviados.append(__import__("json").loads(req.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(plantillas_wa.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with patch("channels.whatsapp._get_wa_token", return_value="t"), \
         patch("channels.whatsapp._get_wa_phone_id", return_value="111"), \
         patch("channels.whatsapp._crm_push_mensaje", AsyncMock(side_effect=lambda **k: inbox.append(k))):
        assert await plantillas_wa.enviar(FUERA, "primer_contacto", ["Ana\nPérez", "piscinas    de fibra"])
    t = enviados[0]["template"]
    assert (enviados[0]["type"], t["name"], t["language"]["code"]) == ("template", "ecofiver_primer_contacto", "es_AR")
    assert [p["text"] for p in t["components"][0]["parameters"]] == ["Ana Pérez", "piscinas de fibra"]
    assert "Recibimos tu consulta por piscinas de fibra" in inbox[0]["contenido"] and inbox[0]["wa_message_id"] == "wamid.X"


def test_las_cinco_plantillas_tienen_dos_parametros_y_no_prometen_precios():
    for clave, (nombre, texto) in plantillas_wa.PLANTILLAS.items():
        assert nombre.startswith("ecofiver_") and "{{1}}" in texto and "{{2}}" in texto and "{{3}}" not in texto
        assert "$" not in texto and "aprob" not in texto.lower()


@pytest.mark.asyncio
async def test_lead_de_meta_fuera_de_ventana_recibe_la_plantilla_sin_generar_texto():
    from channels import meta_leads
    valentina = MagicMock(); valentina.respond = AsyncMock(return_value="no debería usarse")
    with patch("tools.control_agentes.puede_iniciar_saliente", AsyncMock(return_value=(True, ""))), \
         patch.object(crm_client, "autorizar_saliente", AsyncMock(return_value={"permitido": True, "modo": "plantilla"})) as aut, \
         patch.object(plantillas_wa, "enviar", AsyncMock(return_value=True)) as env, \
         patch("channels.whatsapp.send_whatsapp_message", AsyncMock()) as texto, \
         patch("agents.valentina.get_agent", return_value=valentina):
        await meta_leads._contactar_lead_wa({"telefono": FUERA, "nombre": "Ana", "producto_interes": "piscinas"})
        await meta_leads._contactar_lead_wa({"telefono": FUERA, "nombre": "", "producto_interes": "general"})
    assert aut.await_args.kwargs["con_plantilla"] is True
    assert [c.args for c in env.await_args_list] == [(FUERA, "primer_contacto", ["Ana", "piscinas"]),
                                                     (FUERA, "primer_contacto", ["vecino", "nuestros productos"])]
    texto.assert_not_awaited(); valentina.respond.assert_not_awaited()


@pytest.mark.asyncio
async def test_puede_contactar_sigue_siendo_solo_texto():
    """Los flujos sin plantilla (acciones de agentes, email, scraper) nunca reciben modo plantilla."""
    with patch("tools.control_agentes.puede_iniciar_saliente", AsyncMock(return_value=(True, ""))), \
         patch.object(crm_client, "autorizar_saliente", AsyncMock(return_value={"permitido": False, "motivo": "fuera_de_ventana_24h"})) as aut:
        assert not await contacto_comercial.puede_contactar(FUERA, "scraper")
    assert aut.await_args.kwargs["con_plantilla"] is False


@pytest.mark.asyncio
async def test_recordatorio_de_videollamada_es_contractual_y_usa_plantilla():
    from scheduler import cron
    with patch.object(crm_client, "get_videollamadas_proximas", AsyncMock(return_value=[{"telefono": FUERA, "nombre": "Ana", "hora": "18:00"}])), \
         patch.object(crm_client, "autorizar_saliente", AsyncMock(return_value={"permitido": True, "modo": "plantilla"})) as aut, \
         patch.object(plantillas_wa, "enviar", AsyncMock(return_value=True)) as env, \
         patch("channels.whatsapp.send_whatsapp_message", AsyncMock()) as texto:
        await cron.tarea_recordatorio_videollamadas()
    assert aut.await_args.kwargs["contractual"] is True
    env.assert_awaited_once_with(FUERA, "recordatorio_videollamada", ["Ana", "18:00"], remitente="recordatorio")
    texto.assert_not_awaited()
