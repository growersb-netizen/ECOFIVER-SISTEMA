"""
Regresión del incidente de enrutamiento del 28/10/2026 (canal admin de WhatsApp).

Evidencia de producción (/health/ia): en la conversación whatsapp_admin
respondieron Máximo (5 llamadas) y Valentín (8 llamadas, agente terapeuta
personal, sin datos del negocio). La prueba de Rodrigo cayó en Valentín.

Ejecutar: pytest tests/test_enrutamiento_incidente.py -v
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from orchestrator import router
from orchestrator.router import _detectar_switch_agente, es_despedida, es_consulta_comercial


# ─── Detección determinística ────────────────────────────────────────────────

@pytest.mark.parametrize("mensaje,esperado", [
    # Casos del incidente
    ("Quiero hablar con Máximo", "maximo"),
    ("Quiero hablar con Maximo", "maximo"),
    ("quiero hablar con maximo", "maximo"),
    ("No quiero hablar más con Valentín", "salir"),
    ("No quiero hablar mas con Valentina", "salir"),
    # "pasame" = "mandame": no es un cambio de agente
    ("Pasame el resumen de operaciones de hoy", None),
    ("pasame los cobros de la semana", None),
    ("Pasame las finanzas del mes", None),
    ("¿Cómo viene Valentina con los leads?", None),
    ("Decime los precios actuales de las piscinas", None),
    # Pedidos explícitos
    ("Pasame con Ignacio", "ignacio"),
    ("pasame con el cobrador", "ignacio"),
    ("Quiero hablar con la gerente comercial", "aurora"),
    ("Quiero hablar con Valentina", "valentina"),
    ("Quiero hablar con Valentín", "valentin"),
    ("Volvé con Máximo", "maximo"),
    ("volve a maximo", "maximo"),
    ("Necesito hablar con Tomás", "tomas"),
    ("No me pases con Tomás", "salir"),
    ("Basta de Valentín", "salir"),
])
def test_deteccion_de_cambio_de_agente(mensaje, esperado):
    assert _detectar_switch_agente(mensaje) == esperado


@pytest.mark.parametrize("mensaje", ["Chau", "chau!", "Chau, gracias", "listo gracias", "Hasta luego 👋",
                                     "adiós", "Gracias, chau", "nos vemos"])
def test_despedidas(mensaje):
    assert es_despedida(mensaje)


@pytest.mark.parametrize("mensaje", ["Chau, pero antes pasame el stock de piscinas",
                                     "Fin de mes: ¿cómo vienen las ventas?", "hola", "basta de promociones en los posts"])
def test_no_son_despedidas(mensaje):
    assert not es_despedida(mensaje)


def test_consulta_comercial():
    assert es_consulta_comercial("Decime los precios actuales de las piscinas")
    assert not es_consulta_comercial("Estoy cansado, dormí mal")


# ─── Flujo real del canal admin (agentes simulados) ──────────────────────────

class _AgenteFalso:
    def __init__(self, nombre, llamadas):
        self.nombre, self.llamadas, self.history = nombre, llamadas, []

    async def respond(self, message, context=""):
        self.llamadas.append(self.nombre)
        return f"respuesta de {self.nombre}"


@pytest.fixture
def admin():
    llamadas = []
    instancias = {}

    def fake_instance(lead_id, agent_name):
        return instancias.setdefault(agent_name, _AgenteFalso(agent_name, llamadas))

    router._agent_assignments.pop("admin_rodrigo", None)
    with patch.object(router, "_get_agent_instance", side_effect=fake_instance), \
         patch.object(router, "crm_client") as crm, \
         patch.object(router, "registrar_interaccion"):
        crm.get_conversation_history = AsyncMock(return_value="")
        crm.save_message = AsyncMock()

        async def enviar(texto):
            return await router.route_message("whatsapp_admin", "5491135164644", texto, "text")
        yield enviar, llamadas
    router._agent_assignments.pop("admin_rodrigo", None)


@pytest.mark.asyncio
async def test_conversacion_del_incidente(admin):
    enviar, llamadas = admin
    router._agent_assignments["admin_rodrigo"] = "valentin"   # estado en que quedó producción

    r = await enviar("Quiero hablar con Maximo")
    assert r["agent"] == "maximo"
    assert r["reply"].startswith("🔀 Ahora estás hablando con Máximo")

    r = await enviar("Decime los precios actuales de las piscinas")
    assert r["agent"] == "maximo" and not r["reply"].startswith("🔀")

    r = await enviar("Pasame con Valentín")
    assert r["agent"] == "valentin" and "[Dr. Valentín]" in r["reply"]

    # Consulta del negocio estando con Valentín → vuelve sola a Máximo
    r = await enviar("Decime los precios actuales de las piscinas")
    assert r["agent"] == "maximo" and "Ahora estás hablando con Máximo" in r["reply"]

    router._agent_assignments["admin_rodrigo"] = "valentin"
    r = await enviar("No quiero hablar más con Valentín")
    assert r["agent"] == "maximo"

    r = await enviar("No quiero hablar mas con Valentina")
    assert r["agent"] == "maximo"

    antes = len(llamadas)
    r = await enviar("Chau")
    assert r["agent"] == "sistema" and "cierro la conversación" in r["reply"]
    assert len(llamadas) == antes                                  # sin IA, sin promociones
    assert router._agent_assignments.get("admin_rodrigo") == "maximo"


@pytest.mark.asyncio
async def test_despedida_borra_la_memoria_de_la_conversacion(admin):
    enviar, _ = admin
    router._agent_cache["admin_rodrigo:valentin"] = MagicMock()
    router._agent_cache["admin_rodrigo:maximo"] = MagicMock()
    await enviar("chau")
    assert not [k for k in router._agent_cache if k.startswith("admin_rodrigo:")]


@pytest.mark.asyncio
async def test_pasame_el_resumen_no_cambia_de_agente(admin):
    enviar, llamadas = admin
    r = await enviar("Pasame el resumen de operaciones de hoy")
    assert r["agent"] == "maximo" and llamadas == ["maximo"]


# ─── Canal de clientes ───────────────────────────────────────────────────────

@pytest.fixture
def cliente():
    respuestas = {}
    llamadas = []

    class Agente:
        def __init__(self, nombre):
            self.nombre, self.history = nombre, []

        async def respond(self, message, context=""):
            llamadas.append(self.nombre)
            return respuestas.get(self.nombre, f"hola, soy {self.nombre}")

    session = "5491100001111"
    router._agent_assignments.pop(session, None)
    with patch.object(router, "_get_agent_instance", side_effect=lambda lid, n: Agente(n)), \
         patch.object(router, "crm_client") as crm, \
         patch.object(router, "registrar_interaccion"), \
         patch.object(router, "_evaluar_y_alertar_lead", AsyncMock()), \
         patch.object(router, "_procesar_señales_agenda", AsyncMock()), \
         patch.object(router, "_procesar_señal_aliado", AsyncMock(return_value=None)), \
         patch.object(router, "_es_canal_aliados", AsyncMock(return_value=False)):
        crm.get_lead = AsyncMock(return_value={"id": 9, "agente_asignado": "valentina"})
        crm.get_conversation_history = AsyncMock(return_value="")
        crm.save_message = AsyncMock()
        crm.update_lead = AsyncMock(return_value=True)

        async def enviar(texto):
            return await router.route_message("whatsapp", session, texto, "text")
        yield enviar, respuestas, llamadas, crm
    router._agent_assignments.pop(session, None)


@pytest.mark.asyncio
async def test_cliente_no_puede_ser_derivado_a_maximo(cliente):
    enviar, respuestas, llamadas, crm = cliente
    respuestas["valentina"] = "Te paso con Máximo. [DERIVAR:maximo]"
    r = await enviar("Quiero hablar con Máximo")
    assert r["agent"] == "valentina"
    assert "DERIVAR" not in r["reply"]
    assert "maximo" not in llamadas
    crm.update_lead.assert_not_called()


@pytest.mark.asyncio
async def test_cliente_derivado_a_vendedor_si_funciona(cliente):
    enviar, respuestas, llamadas, crm = cliente
    respuestas["valentina"] = "Te paso con Camila. [DERIVAR:camila]"
    r = await enviar("Quiero una pileta al contado")
    assert r["agent"] == "camila" and llamadas == ["valentina", "camila"]


@pytest.mark.asyncio
async def test_cliente_que_se_despide_no_recibe_promociones(cliente):
    enviar, respuestas, llamadas, crm = cliente
    r = await enviar("Chau")
    assert llamadas == []
    assert r["reply"] == "¡Gracias por escribirnos! Cuando quieras, acá estamos. 👋"
    crm.save_message.assert_awaited_once()


# ─── Datos comerciales vigentes ──────────────────────────────────────────────

def test_maximo_y_vendedores_reciben_precios_del_crm_y_valentin_no():
    from tools.crm_context import AGENT_CRM_NEEDS
    for agente in ("Máximo", "Valentina", "Camila", "Nicolás", "Luciano", "Mateo"):
        assert "precios" in AGENT_CRM_NEEDS[agente], agente
    assert "Valentín" not in AGENT_CRM_NEEDS
