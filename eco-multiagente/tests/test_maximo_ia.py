"""
Tests de recuperación de Máximo (respuesta "Dame un momentito" en loop).
Ejecutar: pytest tests/test_maximo_ia.py -v

No llaman a ningún proveedor real: todo está mockeado.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agents.base_agent import BaseAgent
from providers.base_provider import BaseProvider
from providers.openrouter_provider import OpenRouterProvider, normalizar_modelo

ESPERA = "Dame un momentito y te respondo enseguida 🙏"
CONTEXTO_CRM_GIGANTE = "[DATOS CRM EN TIEMPO REAL]\n" + ("  [#123] NUEVO — Nombre Apellido — 1155554444 — Tigre — piscina — Camila — 01/10\n" * 400)
UN_TURNO = len(CONTEXTO_CRM_GIGANTE) + 30000  # contexto CRM + prompt de sistema + mensaje, con margen


def _tamano(system_prompt, history, message):
    return len(system_prompt) + len(message) + sum(len(h["content"]) for h in history)


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
        total = _tamano(system_prompt, history, message)
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
    """Aísla respond() del CRM, la KB y de claves reales."""
    import tools.crm_context as crm_context
    import tools.knowledge_base as kb

    async def _ctx(_name):
        return CONTEXTO_CRM_GIGANTE
    monkeypatch.setattr(crm_context, "get_crm_context", _ctx)
    monkeypatch.setattr(kb, "get_runtime_context", lambda _n: "")
    for k in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODELS", "HISTORY_MAX_CHARS"):
        monkeypatch.delenv(k, raising=False)


# ─── Causa raíz: el historial guardaba el contexto CRM completo en cada turno ──

class TestHistorial:

    @pytest.mark.asyncio
    async def test_maximo_sigue_respondiendo_en_conversacion_larga(self):
        """Con el código anterior el request crecía en cada turno hasta exceder la ventana
        del modelo y todos los turnos siguientes fallaban (desde el turno 3 en este test)."""
        prov = ProveedorConVentana(max_chars=UN_TURNO * 3)
        ag = _agente(prov)
        for i in range(20):
            reply = await ag.respond(f"pregunta {i}")
            assert reply != ESPERA, f"turno {i} cayó en respuesta de espera"
        assert max(prov.llamadas) < UN_TURNO

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


# ─── Regresión de punta a punta: 20 mensajes de Rodrigo a Máximo por WhatsApp ──

class TestRegresionCanalAdmin:

    @pytest.mark.asyncio
    async def test_20_mensajes_consecutivos_a_maximo_memoria_acotada(self, monkeypatch):
        """Ruta real: route_message(canal="whatsapp_admin") → instancia cacheada del Máximo real
        (agents.maximo, con su prompt completo) → OpenRouterProvider. Solo se simulan la red y el CRM."""
        from orchestrator import router

        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        router.clear_agent_cache()
        tamanos = []

        async def fake_generate(self, system_prompt, history, message):
            total = _tamano(system_prompt, history, message)
            tamanos.append(total)
            if total > UN_TURNO * 3:
                raise ValueError("OpenRouter API error 400: maximum context length exceeded")
            return f"respuesta {len(tamanos)}"

        with patch.object(OpenRouterProvider, "generate", fake_generate), \
             patch.object(router.crm_client, "get_conversation_history", AsyncMock(return_value="")), \
             patch.object(router.crm_client, "save_message", AsyncMock(return_value=True)), \
             patch.object(router, "registrar_interaccion", lambda **kw: None):
            for i in range(20):
                res = await router.route_message(
                    canal="whatsapp_admin", session_id="5491135164644",
                    mensaje=f"Máximo, pregunta distinta número {i}", msg_type="text")
                assert res["agent"] == "maximo"
                assert res["reply"] != ESPERA, f"mensaje {i}: Máximo respondió con el mensaje de espera"

            maximo = router._agent_cache["admin_rodrigo:maximo"]
            # Memoria acotada: entradas y caracteres; sin el volcado del CRM adentro
            assert len(maximo.history) <= 30
            assert sum(len(h["content"]) for h in maximo.history) <= 24000
            assert "DATOS CRM" not in "".join(h["content"] for h in maximo.history)
            # El tamaño del request se estabiliza: el último no supera al primero por más que el historial acotado
            assert tamanos[-1] - tamanos[0] <= 24000
        router.clear_agent_cache()


# ─── Modelos ──────────────────────────────────────────────────────────────────

class TestModelos:

    def test_modelo_inexistente_se_normaliza(self):
        assert normalizar_modelo("openrouter/auto:free") == "openrouter/free"
        assert OpenRouterProvider(model="openrouter/auto:free")._model == "openrouter/free"
        assert OpenRouterProvider(model="openai/gpt-4o-mini")._model == "openai/gpt-4o-mini"

    def test_default_es_un_modelo_existente(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
        assert OpenRouterProvider()._model == "openrouter/free"
        monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/auto:free")
        assert OpenRouterProvider()._model == "openrouter/free"

    @pytest.mark.asyncio
    async def test_primario_falla_y_responde_un_respaldo_de_openrouter(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        usados = []

        async def fake_generate(self, system_prompt, history, message):
            usados.append(self._model)
            return "respuesta real"

        with patch.object(OpenRouterProvider, "generate", fake_generate):
            ag = _agente(ProveedorQueFalla(ValueError("OpenRouter API error 402: Insufficient credits")))
            reply = await ag.respond("hola")
        assert reply == "respuesta real"
        assert usados and "openrouter/auto:free" not in usados
        assert ag.history[0]["content"] == "hola"


# ─── Integración PR #4 + PR #5 ────────────────────────────────────────────────

def test_health_ia_tiene_una_sola_ruta_registrada():
    """Los dos PRs agregaban /health/ia: FastAPI no avisa y la segunda queda inalcanzable."""
    import main
    rutas = [r for r in main.app.routes if getattr(r, "path", "") == "/health/ia"]
    assert len(rutas) == 1
