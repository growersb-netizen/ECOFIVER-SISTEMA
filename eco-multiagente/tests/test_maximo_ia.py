"""
Tests de recuperación de Máximo (respuesta "Dame un momentito" en loop).
Ejecutar: pytest tests/test_maximo_ia.py -v

No llaman a ningún proveedor real: todo está mockeado.
"""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agents.base_agent import BaseAgent
from providers.base_provider import BaseProvider
from providers.openrouter_provider import OpenRouterProvider, fallback_models, normalizar_modelo
from tools import ai_monitor

ESPERA = "Dame un momentito y te respondo enseguida 🙏"
CONTEXTO_CRM_GIGANTE = "[DATOS CRM EN TIEMPO REAL]\n" + ("  [#123] NUEVO — Nombre Apellido — 1155554444 — Tigre — piscina — Camila — 01/10\n" * 400)


class ProveedorConVentana(BaseProvider):
    """Simula un modelo con ventana de contexto limitada (como cualquier proveedor real)."""

    def __init__(self, max_chars: int, label: str = "Fake (ventana)"):
        self.max_chars = max_chars
        self.label = label
        self.llamadas = []

    @property
    def name(self):
        return self.label

    async def generate(self, system_prompt, history, message):
        total = len(system_prompt) + len(message) + sum(len(h["content"]) for h in history)
        self.llamadas.append(total)
        if total > self.max_chars:
            raise ValueError("Error 400: This model's maximum context length is exceeded")
        return f"ok turno {len(self.llamadas)}"


class ProveedorQueFalla(BaseProvider):
    def __init__(self, exc, label="Fake (falla)"):
        self.exc, self.label = exc, label

    @property
    def name(self):
        return self.label

    async def generate(self, system_prompt, history, message):
        raise self.exc


def _agente(provider):
    ag = BaseAgent(name="Máximo", system_prompt="Sos Máximo.", atiende_clientes=False)
    ag._get_provider = lambda: provider
    return ag


@pytest.fixture(autouse=True)
def _sin_contexto_externo(monkeypatch):
    """Aísla respond() del CRM, la KB y de claves reales de fallback."""
    import tools.crm_context as crm_context
    import tools.knowledge_base as kb

    async def _ctx(_name):
        return CONTEXTO_CRM_GIGANTE
    monkeypatch.setattr(crm_context, "get_crm_context", _ctx)
    monkeypatch.setattr(kb, "get_runtime_context", lambda _n: "")
    for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GROK_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY",
              "OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODELS", "HISTORY_MAX_CHARS"):
        monkeypatch.delenv(k, raising=False)


# ─── Causa raíz: el historial guardaba el contexto CRM completo en cada turno ──

class TestHistorial:

    @pytest.mark.asyncio
    async def test_maximo_sigue_respondiendo_en_conversacion_larga(self):
        """Reproduce el bug: con el contexto CRM completo, antes el request crecía en cada
        turno hasta exceder la ventana del modelo y todos los turnos siguientes fallaban."""
        un_turno = len(CONTEXTO_CRM_GIGANTE) + 5000
        prov = ProveedorConVentana(max_chars=un_turno * 3)  # entra 1 turno con margen, no 15
        ag = _agente(prov)
        for i in range(20):
            reply = await ag.respond(f"pregunta {i}")
            assert reply != ESPERA, f"turno {i} cayó en respuesta de espera"
        # El tamaño del request no crece con los turnos (no se acumula el contexto)
        assert max(prov.llamadas) < un_turno + 30000

    @pytest.mark.asyncio
    async def test_historial_guarda_mensaje_original_sin_contexto(self):
        ag = _agente(ProveedorConVentana(max_chars=10**9))
        await ag.respond("¿cuántas ventas hubo hoy?")
        assert ag.history[0] == {"role": "user", "content": "¿cuántas ventas hubo hoy?"}
        assert "DATOS CRM" not in "".join(h["content"] for h in ag.history)

    @pytest.mark.asyncio
    async def test_historial_compartido_se_recorta_in_place(self):
        """Telegram asigna su lista de sesión al agente: debe quedar acotada, no crecer sin límite."""
        ag = _agente(ProveedorConVentana(max_chars=10**9))
        sesion_tg = []
        ag.history = sesion_tg
        for i in range(25):
            await ag.respond(f"msg {i}")
        assert ag.history is sesion_tg
        assert len(sesion_tg) <= 30

    @pytest.mark.asyncio
    async def test_historial_acotado_por_caracteres(self, monkeypatch):
        monkeypatch.setenv("HISTORY_MAX_CHARS", "1000")
        ag = _agente(ProveedorConVentana(max_chars=10**9))
        for i in range(10):
            await ag.respond("x" * 300)
        assert sum(len(h["content"]) for h in ag.history) <= 1000
        assert len(ag.history) % 2 == 0 and ag.history[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_turno_fallido_no_contamina_historial(self):
        ag = _agente(ProveedorQueFalla(ValueError("OpenRouter API error 402: Insufficient credits")))
        reply = await ag.respond("hola")
        assert reply == ESPERA
        assert ag.history == []


# ─── Cadena de fallback ───────────────────────────────────────────────────────

class TestFallback:

    def test_modelo_inexistente_se_normaliza(self):
        assert normalizar_modelo("openrouter/auto:free") == "openrouter/free"
        assert OpenRouterProvider(model="openrouter/auto:free")._model == "openrouter/free"
        assert OpenRouterProvider(model="openai/gpt-4o-mini")._model == "openai/gpt-4o-mini"

    def test_fallbacks_openrouter_validos_y_sin_duplicados(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/auto:free")
        fbs = fallback_models()
        assert "openrouter/auto:free" not in fbs
        assert fbs == ["openrouter/free", "openai/gpt-4o-mini"]
        monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "google/gemini-2.5-flash, openrouter/free")
        assert fallback_models() == ["google/gemini-2.5-flash", "openrouter/free"]

    @pytest.mark.asyncio
    async def test_primario_falla_y_responde_openrouter(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        usados = []

        async def fake_generate(self, system_prompt, history, message):
            usados.append(self._model)
            if self._model == "openai/gpt-4o-mini":
                raise ValueError("OpenRouter API error 402: Insufficient credits")
            return "respuesta real"

        with patch.object(OpenRouterProvider, "generate", fake_generate):
            ag = _agente(ProveedorQueFalla(ValueError("Groq 429 rate limit")))
            reply = await ag.respond("hola")
        assert reply == "respuesta real"
        assert usados == ["openai/gpt-4o-mini", "openrouter/free"]

    @pytest.mark.asyncio
    async def test_no_reintenta_el_mismo_modelo_que_fallo_como_primario(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        usados = []

        async def fake_generate(self, system_prompt, history, message):
            usados.append(self._model)
            return "ok"

        with patch.object(OpenRouterProvider, "generate", fake_generate):
            primario = ProveedorQueFalla(ValueError("timeout"), label="OpenRouter (openai/gpt-4o-mini)")
            await _agente(primario).respond("hola")
        assert usados == ["openrouter/free"]


# ─── Observabilidad ───────────────────────────────────────────────────────────

class TestHealthIA:

    def test_clasificacion_de_errores(self):
        c = lambda m: ai_monitor.clasificar_error(ValueError(m))[1]
        assert c("OpenRouter API error 402: Insufficient credits") == "sin_creditos"
        assert c("OpenRouter API error 404: No endpoints found for openrouter/auto:free") == "modelo_inexistente"
        assert c("OpenRouter API error 401: User not found") == "clave_invalida"
        assert c("Error 400: maximum context length is 128000 tokens") == "contexto_excedido"
        assert c("Groq 429 rate limit") == "rate_limit"
        assert c("OPENROUTER_API_KEY no configurada") == "sin_clave"

    def test_endpoint_publico_sin_secretos(self, monkeypatch):
        secreto = "sk-or-v1-SECRETO-DE-PRUEBA"
        monkeypatch.setenv("OPENROUTER_API_KEY", secreto)
        monkeypatch.setenv("AI_PROVIDER", "openrouter")
        ai_monitor.record_fail("OpenRouter (x)", ValueError(f"401 invalid key {secreto}"))
        import main
        r = TestClient(main.app).get("/health/ia")
        assert r.status_code == 200
        assert secreto not in r.text
        d = r.json()
        assert d["proveedor_primario"] == "openrouter"
        assert d["claves_presentes"]["OPENROUTER_API_KEY"] is True
        assert d["por_proveedor"]["OpenRouter (x)"]["last_categoria"] == "clave_invalida"
