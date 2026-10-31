"""
Notas de voz: transcripción que no es transcripción, respuesta cuando falla y
marca de nota de voz para el agente.
Ejecutar: pytest tests/test_notas_de_voz.py -v
"""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from channels import whatsapp as wa
from tools import ai_metrics
from tools.audio_transcriber import no_es_transcripcion

ADMIN = "5491135164644"
CLIENTE = "5491199990000"
LINEA_AGENTES = "1037947576071396"


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    ai_metrics._reset_para_tests()


class TestDeteccion:

    @pytest.mark.parametrize("texto", [
        "I'm sorry, I can't help with that.",
        "Sorry, I cannot transcribe audio.",
        "Lo siento, no puedo ayudar con eso.",
        "Lo siento, pero no puedo transcribir este contenido.",
        "No puedo transcribir el audio.",
        "The audio contains background music only.",
        "El audio parece estar vacío.",
    ])
    def test_respuestas_que_no_son_transcripcion(self, texto):
        assert no_es_transcripcion(texto)

    @pytest.mark.parametrize("texto", [
        "Hola, quiero una pileta de 6 metros en cuotas",
        "No puedo pagar esta semana, ¿puedo pagar el lunes?",
        "Lo siento, no pude ir ayer, ¿podemos reprogramar la visita?",
        "Máximo, pasame el resumen de ventas de hoy",
        "Sorry por la demora, ya te mando los datos",
    ])
    def test_mensajes_reales_no_se_descartan(self, texto):
        assert not no_es_transcripcion(texto)


class _Resp:
    def __init__(self, contenido):
        self.status_code = 200
        self._data = {"choices": [{"message": {"content": contenido}}],
                      "usage": {"prompt_tokens": 240, "completion_tokens": 20}}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


@pytest.mark.asyncio
async def test_negativa_del_modelo_pasa_al_siguiente(monkeypatch):
    from tools import audio_transcriber as at
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AUDIO_OPENROUTER_MODELS", "m/uno,m/dos")
    respuestas = [_Resp("I'm sorry, I can't help with that."), _Resp("Pasame el resumen de ventas")]
    modelos = []

    class Cliente:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, content=None, headers=None, **k):
            modelos.append(json.loads(content)["model"])
            return respuestas.pop(0)

    with patch.object(at, "_a_mp3", AsyncMock(return_value=b"MP3")), patch.object(at.httpx, "AsyncClient", Cliente):
        out = await at.transcribir_bytes(b"OGG", "audio/ogg")
    assert out == "Pasame el resumen de ventas"
    assert modelos == ["m/uno", "m/dos"]
    assert ai_metrics.resumen()["por_agente"]["transcripcion"]["errores"] == 1


def _batch(*items, phone_id=LINEA_AGENTES):
    out = []
    for i, (tipo, valor) in enumerate(items):
        msg = {"id": f"wamid.{i}", "type": tipo}
        if tipo == "text":
            msg["text"] = {"body": valor}
        else:
            msg["audio"] = {"id": valor}
        out.append({"msg_type": tipo, "message": msg, "phone_number_id": phone_id, "nombre_contacto": "T"})
    return out


@pytest.fixture
def canal():
    with patch.object(wa, "route_message", AsyncMock(return_value={"reply": "ok", "agent": "maximo"})) as rm, \
         patch.object(wa, "enviar_mensaje_wa", AsyncMock()) as env, \
         patch.object(wa, "_crm_push_mensaje", AsyncMock()) as push, \
         patch.object(wa, "_crm_get_modo", AsyncMock(return_value="bot")) as modo:
        yield rm, env, push, modo


class TestProcesamiento:

    @pytest.mark.asyncio
    async def test_audio_transcripto_llega_marcado_como_nota_de_voz(self, canal):
        rm, env, _, _ = canal
        with patch.object(wa, "_transcribir_audio", AsyncMock(return_value="Pasame el resumen de ventas")):
            await wa._process_batch(ADMIN, _batch(("audio", "a1")))
        args = rm.await_args.args
        assert args[0] == "whatsapp_admin"
        assert args[2] == f"{wa.MARCA_NOTA_DE_VOZ} Pasame el resumen de ventas"
        assert args[3] == "audio_transcripto"

    @pytest.mark.asyncio
    async def test_audio_fallido_responde_pidiendo_que_lo_escriba(self, canal):
        rm, env, _, _ = canal
        with patch.object(wa, "_transcribir_audio",
                          AsyncMock(return_value="(Audio recibido -- sin metodo de transcripcion activo)")):
            await wa._process_batch(ADMIN, _batch(("audio", "a1")))
        rm.assert_not_called()
        assert env.await_args.args[1] == wa.RESPUESTA_AUDIO_FALLIDO

    @pytest.mark.asyncio
    async def test_audio_fallido_de_cliente_queda_en_inbox_y_se_le_responde(self, canal):
        rm, env, push, _ = canal
        with patch.object(wa, "_transcribir_audio", AsyncMock(return_value="(inaudible)")):
            await wa._process_batch(CLIENTE, _batch(("audio", "a1")))
        assert push.await_args.kwargs["contenido"] == wa.NOTA_DE_VOZ_NO_TRANSCRIPTA
        rm.assert_not_called()
        assert env.await_args.args[1] == wa.RESPUESTA_AUDIO_FALLIDO

    @pytest.mark.asyncio
    async def test_audio_fallido_en_modo_humano_no_responde(self, canal):
        rm, env, _, modo = canal
        modo.return_value = "humano"
        with patch.object(wa, "_transcribir_audio", AsyncMock(return_value="(inaudible)")):
            await wa._process_batch(CLIENTE, _batch(("audio", "a1")))
        rm.assert_not_called()
        env.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_fallido_en_linea_supervisada_solo_registra(self, canal, monkeypatch):
        rm, env, push, _ = canal
        monkeypatch.setattr(wa, "WA_SUPERVISOR_PHONE_IDS", {"1383774158147416"})
        with patch.object(wa, "_transcribir_audio", AsyncMock(return_value="(inaudible)")):
            await wa._process_batch(CLIENTE, _batch(("audio", "a1"), phone_id="1383774158147416"))
        push.assert_awaited_once()
        rm.assert_not_called()
        env.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_fallido_con_texto_en_el_mismo_lote_usa_el_texto(self, canal):
        rm, env, _, _ = canal
        with patch.object(wa, "_transcribir_audio", AsyncMock(return_value="(inaudible)")):
            await wa._process_batch(ADMIN, _batch(("audio", "a1"), ("text", "Resumen de hoy")))
        assert rm.await_args.args[2] == "Resumen de hoy"
        assert rm.await_args.args[3] == "text"

    @pytest.mark.asyncio
    async def test_texto_sin_cambios(self, canal):
        rm, env, _, _ = canal
        await wa._process_batch(ADMIN, _batch(("text", "Hola Máximo")))
        assert rm.await_args.args[2] == "Hola Máximo"
        assert rm.await_args.args[3] == "text"
        assert env.await_args.args[1] == "ok"
