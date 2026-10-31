"""Fase 3: capas de instrucciones, acciones de dirección y panel económico de Máximo."""
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")

from tools import capas, crm_actions, crm_client
from tools.action_policy import ActionContext, CANAL_CONFIABLE, evaluar


@pytest.mark.asyncio
@pytest.mark.capas_reales
async def test_capas_con_precedencia_y_politicas_activas():
    capas._reset_para_tests()

    def handler(req):
        assert req.headers["x-agente"] == "camila"
        return httpx.Response(200, json={"politicas": [{"titulo": "Venta consultiva", "version": 2,
                                                         "instruccion": "Hacé dos preguntas de diagnóstico."}]})
    real = httpx.AsyncClient
    with patch.object(capas.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
        texto = await capas.componer("Camila", "Sos Camila...")
    i1, i2, i3 = texto.index("[CAPA 1"), texto.index("[CAPA 2"), texto.index("[CAPA 3")
    assert i1 < i2 < i3 and "Venta consultiva (v2)" in texto and texto.endswith("Sos Camila...")


@pytest.mark.asyncio
@pytest.mark.capas_reales
async def test_valentin_no_recibe_capas_y_sin_crm_queda_la_capa_1():
    capas._reset_para_tests()
    assert await capas.componer("Dr. Valentín", "privado") == "privado"
    with patch.object(capas.httpx, "AsyncClient", side_effect=RuntimeError("sin red")):
        texto = await capas.componer("Aurora", "Sos Aurora")
    assert "[CAPA 1" in texto and "[CAPA 2" not in texto


def test_politica_de_acciones_de_direccion():
    for tipo in ("crear_tarea", "proponer_politica"):
        for ag in ("maximo", "aurora", "tomas"):
            assert evaluar(tipo, {}, ActionContext(ag, CANAL_CONFIABLE)).permitido
        assert not evaluar(tipo, {}, ActionContext("camila", CANAL_CONFIABLE)).permitido
        assert not evaluar(tipo, {"lead_id": 1}, ActionContext("maximo", "cliente", lead_id=1)).permitido
    assert evaluar("fijar_objetivo", {}, ActionContext("maximo", CANAL_CONFIABLE)).permitido
    assert not evaluar("fijar_objetivo", {}, ActionContext("aurora", CANAL_CONFIABLE)).permitido


@pytest.mark.asyncio
async def test_maximo_encarga_tarea_desde_su_canal():
    with patch("tools.motor_tareas.crear_tarea", AsyncMock(return_value={"id": 31, "agente": "aurora"})) as ct:
        out = await crm_actions.ejecutar_acciones(
            [{"tipo": "crear_tarea", "datos": {"agente": "aurora", "instruccion": "Analizá la conversión"}}],
            ActionContext(agente="maximo", canal=CANAL_CONFIABLE, origen="whatsapp_admin"))
    assert "Tarea #31" in out and ct.await_args.kwargs["creado_por_agente"] == "maximo"


@pytest.mark.asyncio
async def test_objetivo_viaja_con_la_autorizacion_del_canal():
    vistos = []

    def handler(req):
        vistos.append(dict(req.headers))
        return httpx.Response(200, json={"ok": True, "objetivo": {"id": 1, "version": 3, "valor": 1500000}})
    real = httpx.AsyncClient
    with patch("httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
        out = await crm_actions.ejecutar_acciones(
            [{"tipo": "fijar_objetivo", "datos": {"periodo": "2026-11", "indicador": "comisiones_generadas", "valor": 1500000}}],
            ActionContext(agente="maximo", canal=CANAL_CONFIABLE, origen="whatsapp_admin"))
    assert "versión 3" in out
    assert vistos[0]["x-autorizacion-humana"] == "canal:whatsapp_admin" and vistos[0]["x-agente"] == "maximo"


def test_contexto_de_maximo_incluye_su_panel_economico():
    from tools.crm_context import AGENT_CRM_NEEDS, _panel_propietario
    assert "panel_propietario" in AGENT_CRM_NEEDS["Máximo"]
    for otro in ("Aurora", "Camila", "Elena"):
        assert "panel_propietario" not in AGENT_CRM_NEEDS.get(otro, [])
    parts = []
    _panel_propietario(parts, {"periodo": "2026-10", "comisiones_generadas": {"total": 949000}, "comisiones_cobradas": {"total": 700000},
                               "comisiones_pendientes": {"total": 249000}, "comisiones_proyectadas": {"total": 0},
                               "inversion_publicitaria": {"gasto_real": 0}, "resultado_personal": {"total": 700000},
                               "objetivos": {}, "proyeccion_cierre_mes": {"comisiones_generadas": 949000}, "datos_faltantes": []})
    assert "$949.000" in parts[0] and "NO es la contabilidad de la cooperativa" in parts[0]


def test_maximo_conoce_el_modelo_y_las_acciones():
    from agents.maximo import _SYSTEM_PROMPT as p
    for x in ("CONSULTA", "INSTRUCCIÓN AUTORIZADA", "10% del producto", "2 cuotas iniciales", "crear_tarea",
              "proponer_politica", "fijar_objetivo", "Vos no aprobás créditos"):
        assert x in p, x
