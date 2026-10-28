"""
Modelo de IA por agente vía OpenRouter (tools.model_policy + tools.openrouter_catalog).
Ejecutar: pytest tests/test_modelos_por_agente.py -v
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from tools import ai_metrics, model_policy, openrouter_catalog as cat

CATALOGO = [
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o mini", "context_length": 128000,
     "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
     "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context_length": 1000000,
     "pricing": {"prompt": "0.0000003", "completion": "0.0000025"},
     "architecture": {"input_modalities": ["text", "image", "audio", "file"], "output_modalities": ["text"]}},
    {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "context_length": 1000000,
     "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
     "architecture": {"input_modalities": ["text", "image", "audio"], "output_modalities": ["text"]}},
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "context_length": 200000,
     "pricing": {"prompt": "0.000003", "completion": "0.000015"},
     "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
]


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for v in ("AI_PERFIL_MODELOS", "AI_MODELOS_JSON", "OPENROUTER_FALLBACK_MODELS",
              "AUDIO_OPENROUTER_MODELS", "OPENROUTER_VISION_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    cat._reset_para_tests()
    ai_metrics._reset_para_tests()
    from providers import factory
    factory._instances.clear()
    yield
    cat._reset_para_tests()
    factory._instances.clear()


def _con_catalogo(modelos=CATALOGO):
    cat.cargar_desde_datos(modelos, "test")


class TestPerfiles:

    def test_perfil_base_es_identico_al_comportamiento_anterior(self):
        for a in model_policy.AGENTES:
            if a in ("transcripcion", "vision"):
                continue
            c = model_policy.resolver(a)
            assert (c.modelo, c.temperatura, c.max_tokens) == ("openai/gpt-4o-mini", 0.7, 700), a
            assert c.respaldo == ["google/gemini-2.5-flash"]

    def test_perfil_recomendado_por_funcion(self, monkeypatch):
        monkeypatch.setenv("AI_PERFIL_MODELOS", "recomendado")
        _con_catalogo()
        maximo = model_policy.resolver("Máximo")
        camila = model_policy.resolver("Camila")
        aurora = model_policy.resolver("Aurora")
        assert (maximo.rol, maximo.modelo, maximo.temperatura, maximo.max_tokens) == \
               ("direccion", "anthropic/claude-sonnet-4", 0.3, 1500)
        assert (camila.rol, camila.modelo, camila.temperatura) == ("ventas", "openai/gpt-4o-mini", 0.6)
        assert (aurora.rol, aurora.modelo) == ("analisis", "google/gemini-2.5-flash")
        assert model_policy.resolver("Valentín").modelo == "openai/gpt-4o-mini"  # privado: base

    def test_perfil_desconocido_vuelve_a_base(self, monkeypatch):
        monkeypatch.setenv("AI_PERFIL_MODELOS", "carisimo")
        assert model_policy.perfil_activo() == "base"

    def test_ajuste_por_agente_y_por_rol(self, monkeypatch):
        monkeypatch.setenv("AI_MODELOS_JSON", json.dumps({
            "rol:ventas": {"temperatura": 0.5},
            "camila": {"modelo": "google/gemini-2.5-flash", "max_tokens": 400},
        }))
        c = model_policy.resolver("Camila")
        n = model_policy.resolver("Nicolás")
        assert (c.modelo, c.temperatura, c.max_tokens) == ("google/gemini-2.5-flash", 0.5, 400)
        assert (n.modelo, n.temperatura) == ("openai/gpt-4o-mini", 0.5)

    def test_json_invalido_no_rompe(self, monkeypatch):
        monkeypatch.setenv("AI_MODELOS_JSON", "{no es json")
        assert model_policy.resolver("Camila").modelo == "openai/gpt-4o-mini"


class TestValidacionConCatalogo:

    def test_modelo_inexistente_usa_respaldo_valido(self, monkeypatch):
        _con_catalogo([m for m in CATALOGO if m["id"] != "anthropic/claude-sonnet-4"])
        monkeypatch.setenv("AI_PERFIL_MODELOS", "recomendado")
        c = model_policy.resolver("Máximo")
        assert c.modelo == "google/gemini-2.5-flash"
        assert any("claude-sonnet-4" in a and "no existe" in a for a in c.avisos)

    def test_audio_exige_modelo_con_entrada_de_audio(self, monkeypatch):
        _con_catalogo()
        monkeypatch.setenv("AI_MODELOS_JSON", json.dumps({"transcripcion": {
            "modelo": "openai/gpt-4o-mini", "respaldo": ["google/gemini-2.0-flash-001"]}}))
        c = model_policy.resolver("transcripcion")
        assert c.modelo == "google/gemini-2.0-flash-001"
        assert any("audio" in a for a in c.avisos)

    def test_vision_exige_imagen(self, monkeypatch):
        _con_catalogo()
        assert model_policy.resolver("vision").modelo == "openai/gpt-4o-mini"

    def test_sin_catalogo_no_valida_y_avisa(self):
        c = model_policy.resolver("Camila")
        assert c.modelo == "openai/gpt-4o-mini"
        assert any("sin validar" in a for a in c.avisos)


class TestUsoReal:

    @pytest.mark.asyncio
    async def test_cada_agente_llama_con_su_modelo_y_parametros(self, monkeypatch):
        from agents.base_agent import BaseAgent
        from providers.openrouter_provider import OpenRouterProvider
        monkeypatch.setenv("AI_PERFIL_MODELOS", "recomendado")
        _con_catalogo()
        vistos = []

        async def fake(self, system_prompt, history, message):
            vistos.append((self._model, self._temperature, self._max_tokens))
            return "ok"

        with patch.object(OpenRouterProvider, "generate", fake), \
             patch("tools.crm_context.get_crm_context", new_callable=AsyncMock, return_value=""):
            await BaseAgent(name="Máximo", system_prompt="x", atiende_clientes=False).respond("hola")
            await BaseAgent(name="Camila", system_prompt="x", atiende_clientes=False).respond("hola")
        assert vistos == [("anthropic/claude-sonnet-4", 0.3, 1500), ("openai/gpt-4o-mini", 0.6, 600)]

    @pytest.mark.asyncio
    async def test_respaldo_usa_los_modelos_del_rol(self, monkeypatch):
        from agents.base_agent import BaseAgent
        from providers.openrouter_provider import OpenRouterProvider
        monkeypatch.setenv("AI_PERFIL_MODELOS", "recomendado")
        _con_catalogo()
        vistos = []

        async def fake(self, system_prompt, history, message):
            vistos.append(self._model)
            if self._model == "anthropic/claude-sonnet-4":
                raise RuntimeError("timeout")
            return "ok"

        with patch.object(OpenRouterProvider, "generate", fake), \
             patch("tools.crm_context.get_crm_context", new_callable=AsyncMock, return_value=""):
            out = await BaseAgent(name="Máximo", system_prompt="x", atiende_clientes=False).respond("hola")
        assert out == "ok"
        assert vistos == ["anthropic/claude-sonnet-4", "google/gemini-2.5-flash"]

    @pytest.mark.asyncio
    async def test_costo_con_precio_del_catalogo(self):
        _con_catalogo()

        class P:
            _model = "anthropic/claude-sonnet-4"

            async def generate(self, system_prompt, history, message):
                ai_metrics.informar_uso({"prompt_tokens": 1_000_000, "completion_tokens": 100_000})
                return "ok"

        await ai_metrics.generar_medido(agente="Máximo", provider=P(), fallback=False,
                                        system_prompt="", history=[], message="")
        assert ai_metrics.resumen()["totales"]["costo_usd"] == pytest.approx(3.0 + 1.5)

    def test_comparacion_de_perfiles_con_uso_del_dia(self):
        _con_catalogo()
        uso = {"Máximo": {"tokens_in": 1_000_000, "tokens_out": 0},
               "Camila": {"tokens_in": 1_000_000, "tokens_out": 0}}
        comp = model_policy.comparar_perfiles(uso)
        assert comp["base"]["usd_dia_estimado"] == pytest.approx(0.30)          # 2 × 0.15
        assert comp["recomendado"]["usd_dia_estimado"] == pytest.approx(3.15)   # 3.00 + 0.15


class TestCatalogo:

    @pytest.mark.asyncio
    async def test_descarga_cachea_y_sobrevive_falla(self, tmp_path):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return {"data": CATALOGO}

        class Cliente:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url): return Resp()

        with patch.object(cat.httpx, "AsyncClient", Cliente):
            assert await cat.actualizar(force=True) == 4
        assert (tmp_path / "openrouter_models.json").exists()
        assert cat.precio_por_millon("openai/gpt-4o-mini") == pytest.approx((0.15, 0.6))
        assert "audio" in cat.info("google/gemini-2.5-flash")["entradas"]

        cat._reset_para_tests()

        class Caido(Cliente):
            async def get(self, url): raise ConnectionError("sin red")

        with patch.object(cat.httpx, "AsyncClient", Caido):
            assert await cat.actualizar(force=True) == 4  # usa la cache del volumen
        assert cat.estado()["origen"] == "cache"


def test_endpoint_health_ia_modelos(monkeypatch):
    import os
    from fastapi.testclient import TestClient
    os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
    os.environ.setdefault("CRM_API_KEY", "test-key")
    import main
    _con_catalogo()
    r = TestClient(main.app).get("/health/ia/modelos")
    assert r.status_code == 200
    body = r.json()
    assert body["perfil_activo"] == "base" and len(body["agentes"]) == len(model_policy.AGENTES)
    assert {"base", "recomendado"} <= set(body["comparacion_perfiles_hoy"])
