"""
Política: TODO el consumo de IA pasa por OpenRouter.
Ejecutar: pytest tests/test_openrouter_unico.py -v
"""
import json
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import ai_metrics


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    ai_metrics._reset_para_tests()
    from providers import factory
    factory._instances.clear()
    yield
    factory._instances.clear()


def _prohibir_otros_proveedores():
    """Si algún código instancia un proveedor que no es OpenRouter, el test falla."""
    def boom(*a, **k):
        raise AssertionError("Se instanció un proveedor que no es OpenRouter")
    return [
        patch("providers.groq_provider.GroqProvider.__init__", side_effect=boom),
        patch("providers.grok_provider.GrokProvider.__init__", side_effect=boom),
        patch("providers.gemini_provider.GeminiProvider.__init__", side_effect=boom),
    ]


class TestFactory:

    @pytest.mark.parametrize("valor", ["grok", "groq", "gemini", "claude", "openai", "", "openrouter"])
    def test_siempre_openrouter(self, monkeypatch, valor):
        from providers import factory
        from providers.openrouter_provider import OpenRouterProvider
        monkeypatch.setenv("AI_PROVIDER", valor)
        monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        assert factory.get_active_provider_name() == "openrouter"
        p = factory.get_provider()
        assert isinstance(p, OpenRouterProvider) and p._model == "openai/gpt-4o-mini"

    def test_modelos_de_respaldo(self, monkeypatch):
        from providers.factory import modelos_respaldo
        assert modelos_respaldo("openai/gpt-4o-mini") == ["google/gemini-2.5-flash"]
        monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "a/x, b/y ,a/x,,principal")
        assert modelos_respaldo("principal") == ["a/x", "b/y"]


class TestRespaldoSoloOpenRouter:

    @pytest.mark.asyncio
    async def test_falla_principal_y_responde_otro_modelo_de_openrouter(self, monkeypatch):
        from agents.base_agent import BaseAgent
        from providers.openrouter_provider import OpenRouterProvider
        monkeypatch.setenv("AI_PROVIDER", "groq")  # aunque el volumen diga otra cosa
        monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        llamados = []

        async def fake_generate(self, system_prompt, history, message):
            llamados.append(self._model)
            if self._model == "openai/gpt-4o-mini":
                raise RuntimeError("402 sin créditos")
            return f"respuesta de {self._model}"

        ps = _prohibir_otros_proveedores()
        for p in ps:
            p.start()
        try:
            with patch.object(OpenRouterProvider, "generate", fake_generate), \
                 patch("tools.crm_context.get_crm_context", new_callable=AsyncMock, return_value=""):
                out = await BaseAgent(name="Camila", system_prompt="x", atiende_clientes=False).respond("hola")
        finally:
            for p in ps:
                p.stop()
        assert out == "respuesta de google/gemini-2.5-flash"
        assert llamados == ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]
        r = ai_metrics.resumen()
        assert r["totales"]["fallback_ok"] == 1 and r["totales"]["errores"] == 1

    @pytest.mark.asyncio
    async def test_todo_falla_respuesta_generica_sin_otros_proveedores(self, monkeypatch):
        from agents.base_agent import BaseAgent
        from providers.openrouter_provider import OpenRouterProvider
        ps = _prohibir_otros_proveedores()
        for p in ps:
            p.start()
        try:
            with patch.object(OpenRouterProvider, "generate", AsyncMock(side_effect=RuntimeError("caído"))), \
                 patch("tools.crm_context.get_crm_context", new_callable=AsyncMock, return_value=""), \
                 patch.object(ai_metrics, "_alertar"):
                out = await BaseAgent(name="Camila", system_prompt="x", atiende_clientes=False).respond("hola")
        finally:
            for p in ps:
                p.stop()
        assert out.startswith("Dame un momentito")
        assert ai_metrics.resumen()["totales"]["sin_respuesta"] == 1

    def test_modelo_propio_tambien_va_por_openrouter(self):
        from agents.base_agent import BaseAgent
        from providers.openrouter_provider import OpenRouterProvider
        a = BaseAgent(name="X", system_prompt="x", model="anthropic/claude-sonnet-4", atiende_clientes=False)
        p = a._get_provider()
        assert isinstance(p, OpenRouterProvider) and p._model == "anthropic/claude-sonnet-4"


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=self)


class TestAudioSoloOpenRouter:

    def _cliente(self, respuestas):
        enviados = []

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, content=None, headers=None, **k):
                enviados.append((url, json.loads(content)))
                return respuestas.pop(0)
        return FakeClient, enviados

    @pytest.mark.asyncio
    async def test_input_audio_mp3_y_solo_openrouter(self, monkeypatch):
        from tools import audio_transcriber as at
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        FakeClient, enviados = self._cliente([_Resp(200, {"choices": [{"message": {"content": "Hola quiero una pileta"}}]})])
        with patch.object(at, "_a_mp3", AsyncMock(return_value=b"MP3DATA")), patch.object(at.httpx, "AsyncClient", FakeClient):
            out = await at.transcribir_bytes(b"OGGDATA", "audio/ogg; codecs=opus")
        assert out == "Hola quiero una pileta"
        url, payload = enviados[0]
        assert url.startswith("https://openrouter.ai/")
        audio = [c for c in payload["messages"][0]["content"] if c["type"] == "input_audio"][0]["input_audio"]
        assert audio["format"] == "mp3"
        assert ai_metrics.resumen()["por_agente"]["transcripcion"]["llamadas"] == 1

    @pytest.mark.asyncio
    async def test_sin_ffmpeg_manda_formato_original_y_prueba_siguiente_modelo(self, monkeypatch):
        from tools import audio_transcriber as at
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.setenv("AUDIO_OPENROUTER_MODELS", "m/uno,m/dos")
        FakeClient, enviados = self._cliente([
            _Resp(400, {"error": "formato"}),
            _Resp(200, {"choices": [{"message": {"content": "Transcripcion: buen día"}}]}),
        ])
        with patch.object(at, "_a_mp3", AsyncMock(return_value=None)), patch.object(at.httpx, "AsyncClient", FakeClient):
            out = await at.transcribir_bytes(b"OGG", "audio/ogg")
        assert out == "buen día"
        assert [p["model"] for _, p in enviados] == ["m/uno", "m/dos"]
        assert enviados[0][1]["messages"][0]["content"][1]["input_audio"]["format"] == "ogg"

    @pytest.mark.asyncio
    async def test_sin_clave_devuelve_mensaje_que_los_canales_ya_manejan(self, monkeypatch):
        from tools import audio_transcriber as at
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        out = await at.transcribir_bytes(b"x", "audio/ogg")
        assert out.startswith("(Audio recibido")

    @pytest.mark.asyncio
    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado en este entorno")
    async def test_conversion_real_con_ffmpeg(self):
        import asyncio
        from tools import audio_transcriber as at
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:a", "libopus", "-f", "ogg", "pipe:1", stdout=asyncio.subprocess.PIPE)
        ogg, _ = await proc.communicate()
        mp3 = await at._a_mp3(ogg)
        assert mp3 and len(mp3) > 1000
