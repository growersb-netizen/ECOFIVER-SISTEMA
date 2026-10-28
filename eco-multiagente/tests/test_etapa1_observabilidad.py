"""
Tests Etapa 1 — Observabilidad e informes ejecutivos.
Ejecutar: pytest tests/test_etapa1_observabilidad.py -v

Sin red: proveedores de IA, CRM y Telegram están simulados.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tools import ai_metrics


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AI_PRICES_JSON", raising=False)
    monkeypatch.setenv("AI_DAILY_COST_LIMIT_USD", "5")
    ai_metrics._reset_para_tests()
    from scheduler import run_log
    run_log._reset_para_tests()
    yield


class FakeOpenRouterProvider:
    def __init__(self, model="openai/gpt-4o-mini", reply="hola", usage=None, exc=None):
        self._model, self._reply, self._usage, self._exc = model, reply, usage, exc

    async def generate(self, system_prompt, history, message):
        if self._exc:
            raise self._exc
        if self._usage is not None:
            ai_metrics.informar_uso(self._usage)
        return self._reply


async def _llamar(provider, agente="valentina", fallback=False):
    return await ai_metrics.generar_medido(agente=agente, provider=provider, fallback=fallback,
                                           system_prompt="s" * 400, history=[], message="m" * 400)


# ─── Métricas de IA ───────────────────────────────────────────────────────────

class TestMetricasIA:

    @pytest.mark.asyncio
    async def test_costo_real_informado_por_el_proveedor(self):
        await _llamar(FakeOpenRouterProvider(usage={"prompt_tokens": 1000, "completion_tokens": 100, "cost": 0.0042}))
        r = ai_metrics.resumen()
        assert r["totales"]["costo_usd"] == pytest.approx(0.0042)
        assert r["totales"]["tokens_in"] == 1000 and r["totales"]["tokens_out"] == 100
        assert r["por_agente"]["valentina"]["llamadas"] == 1
        assert r["ultimo_proveedor_efectivo"]["proveedor"] == "fakeopenrouter"

    @pytest.mark.asyncio
    async def test_costo_por_tabla_de_precios(self):
        await _llamar(FakeOpenRouterProvider(usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}))
        assert ai_metrics.resumen()["totales"]["costo_usd"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_tokens_estimados_si_no_hay_usage(self):
        await _llamar(FakeOpenRouterProvider(usage=None, reply="x" * 400))
        t = ai_metrics.resumen()["totales"]
        assert t["tokens_in"] == 200 and t["tokens_out"] == 100 and t["tokens_estimados"] == 300

    @pytest.mark.asyncio
    async def test_modelo_free_cuesta_cero_y_desconocido_sin_precio(self):
        await _llamar(FakeOpenRouterProvider(model="openrouter/auto:free"))
        await _llamar(FakeOpenRouterProvider(model="modelo/desconocido"))
        t = ai_metrics.resumen()["totales"]
        assert t["costo_usd"] == 0 and t["llamadas_sin_precio"] == 1

    @pytest.mark.asyncio
    async def test_error_se_registra_y_se_propaga(self):
        with pytest.raises(RuntimeError):
            await _llamar(FakeOpenRouterProvider(exc=RuntimeError("401 credit")))
        r = ai_metrics.resumen()
        assert r["totales"]["errores"] == 1
        assert "401 credit" in r["errores_recientes"][0]["error"]

    @pytest.mark.asyncio
    async def test_respaldo_y_sin_respuesta(self):
        await _llamar(FakeOpenRouterProvider(), fallback=True)
        await _llamar(FakeOpenRouterProvider(), fallback=False)
        with patch.object(ai_metrics, "_alertar") as al:
            ai_metrics.registrar_sin_respuesta("camila")
        r = ai_metrics.resumen()
        assert r["totales"]["fallback_ok"] == 1 and r["pct_respaldo"] == 50.0
        assert r["totales"]["sin_respuesta"] == 1
        al.assert_called_once()

    @pytest.mark.asyncio
    async def test_atribucion_por_proceso(self):
        token = ai_metrics.proceso_actual.set("cron:reporte_aurora_manana")
        try:
            await _llamar(FakeOpenRouterProvider(), agente="Aurora")
        finally:
            ai_metrics.proceso_actual.reset(token)
        await _llamar(FakeOpenRouterProvider())
        p = ai_metrics.resumen()["por_proceso"]
        assert p["cron:reporte_aurora_manana"]["llamadas"] == 1 and p["otro"]["llamadas"] == 1

    @pytest.mark.asyncio
    async def test_alerta_de_limite_diario_una_sola_vez(self, monkeypatch):
        monkeypatch.setenv("AI_DAILY_COST_LIMIT_USD", "0.01")
        with patch.object(ai_metrics, "_alertar", wraps=ai_metrics._alertar) as al, \
             patch("channels.telegram_bot.send_alert", new_callable=AsyncMock):
            for costo in (0.0085, 0.002, 0.002):   # cruza 80 %, luego 100 %, luego nada nuevo
                await _llamar(FakeOpenRouterProvider(usage={"cost": costo}))
        claves = [c.args[0] for c in al.call_args_list]
        assert claves[0] == "limite_80" and "limite_100" in claves
        assert ai_metrics._estado._alertas_enviadas == {"limite_80", "limite_100"}

    @pytest.mark.asyncio
    async def test_base_agent_mide_la_llamada_principal(self):
        from agents.base_agent import BaseAgent
        agente = BaseAgent(name="Camila", system_prompt="Sos Camila", atiende_clientes=False)
        with patch.object(BaseAgent, "_get_provider", return_value=FakeOpenRouterProvider(reply="¡Hola!")), \
             patch("tools.crm_context.get_crm_context", new_callable=AsyncMock, return_value=""):
            out = await agente.respond("hola")
        assert out == "¡Hola!"
        assert ai_metrics.resumen()["por_agente"]["Camila"]["llamadas"] == 1

    def test_persistencia_del_dia(self, tmp_path):
        ai_metrics._guardar_si_corresponde(force=True)
        assert list(tmp_path.glob("ai_metrics_*.json"))


# ─── Registro de ejecuciones del scheduler ───────────────────────────────────

class TestRunLog:

    @pytest.mark.asyncio
    async def test_ok_error_y_resultado(self, tmp_path):
        from scheduler.run_log import tracked, resumen

        async def ok():
            return {"enviados": 3}

        async def explota():
            raise ValueError("CRM 500")

        async def error_controlado():
            return {"error": "sin datos"}

        await tracked("t_ok", ok)()
        assert await tracked("t_err", explota)() is None
        await tracked("t_ctrl", error_controlado)()
        r = resumen(detalle=True)
        assert r["tareas"]["t_ok"]["estado"] == "ok" and r["tareas"]["t_ok"]["resultado"] == {"enviados": 3}
        assert r["tareas"]["t_err"]["estado"] == "error" and "CRM 500" in r["tareas"]["t_err"]["error"]
        assert r["tareas"]["t_ctrl"]["estado"] == "error"
        assert (tmp_path / "scheduler_runs.jsonl").read_text().count("\n") == 3
        publico = resumen(detalle=False)
        assert "error" not in publico["tareas"]["t_err"] and publico["tareas"]["t_err"]["con_error"]

    @pytest.mark.asyncio
    async def test_proceso_cron_y_restauracion(self):
        from scheduler.run_log import tracked
        visto = {}

        async def tarea():
            visto["p"] = ai_metrics.proceso_actual.get()

        await tracked("cobros_ignacio", tarea)()
        assert visto["p"] == "cron:cobros_ignacio"
        assert ai_metrics.proceso_actual.get() == "otro"

    def test_instrumentar_envuelve_todas_las_tareas_una_vez(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from scheduler.run_log import instrumentar

        async def a():
            pass

        sch = AsyncIOScheduler()
        sch.add_job(a, CronTrigger(hour=1), id="tarea_a")
        sch.add_job(a, CronTrigger(hour=2), id="tarea_b")
        assert instrumentar(sch) == 2
        assert instrumentar(sch) == 0
        assert all(getattr(j.func, "__wrapped_tarea__", None) for j in sch.get_jobs())

    def test_el_scheduler_real_queda_instrumentado(self):
        """Todas las tareas de cron.py quedan con registro de ejecución (sin arrancar el loop)."""
        from scheduler import cron
        with patch.object(cron, "AsyncIOScheduler") as cls:
            real = __import__("apscheduler.schedulers.asyncio", fromlist=["AsyncIOScheduler"]).AsyncIOScheduler()
            real.start = MagicMock()
            cls.return_value = real
            cron.start_scheduler()
        jobs = real.get_jobs()
        assert len(jobs) >= 20
        assert all(getattr(j.func, "__wrapped_tarea__", None) for j in jobs)


# ─── Tomás y Aurora → canal ejecutivo ────────────────────────────────────────

def _lead(i, **kw):
    d = {"id": i, "nombre": f"Cliente {i}", "telefono": f"54911000{i:04d}", "producto_interes": "PISCINA",
         "forma_pago": "CONTADO", "estado": "NUEVO", "agente_asignado": "camila",
         "updated_at": "2026-10-27T10:00:00+00:00"}
    d.update(kw)
    return d


class TestInformesEjecutivos:

    def setup_method(self):
        from scheduler import cron
        cron._tomas_alertados.clear()

    def test_alerta_tomas_formato_y_sin_repetir(self):
        from scheduler.cron import armar_alerta_tomas, _tomas_alertados
        texto, ids = armar_alerta_tomas([_lead(1), _lead(2)], ahora=1_000_000)
        assert "Cliente 1" in texto and "PISCINA/CONTADO" in texto and ids == ["1", "2"]
        for i in ids:
            _tomas_alertados[i] = 1_000_000
        texto2, ids2 = armar_alerta_tomas([_lead(1), _lead(2), _lead(3)], ahora=1_000_100)
        assert ids2 == ["3"] and "3 lead(s)" in texto2
        texto3, _ = armar_alerta_tomas([_lead(1)], ahora=1_000_000 + 7 * 3600)
        assert "Cliente 1" in texto3  # pasadas 6 h se vuelve a informar

    @pytest.mark.asyncio
    async def test_tarea_tomas_no_usa_ia_ni_escribe_a_clientes(self):
        from scheduler import cron
        with patch("tools.crm_client.get_leads_sin_respuesta", new_callable=AsyncMock, return_value=[_lead(7)]), \
             patch.object(cron, "_enviar_ejecutivo", new_callable=AsyncMock, return_value=True) as env, \
             patch("agents.tomas.get_agent") as ga, \
             patch("channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as wa:
            r = await cron.tarea_check_leads_sin_respuesta()
        ga.assert_not_called()
        wa.assert_not_called()
        env.assert_awaited_once()
        assert r == {"leads_sin_respuesta": 1, "alertados": 1, "enviado_telegram": True}

    @pytest.mark.asyncio
    async def test_tarea_aurora_envia_informe(self):
        from scheduler import cron
        aurora = MagicMock()
        aurora.respond = AsyncMock(return_value="Pipeline: 12 leads. Prioridad: ...")
        with patch("agents.aurora.get_agent", return_value=aurora), \
             patch("tools.crm_client.get_pipeline_stats", new_callable=AsyncMock, return_value={"leads": 12}), \
             patch.object(cron, "_enviar_ejecutivo", new_callable=AsyncMock, return_value=True) as env:
            r = await cron.tarea_reporte_aurora_manana()
        assert "Pipeline: 12 leads" in env.await_args.args[0]
        assert r["enviado_telegram"] is True

    @pytest.mark.asyncio
    async def test_flag_desactiva_envio(self, monkeypatch):
        from scheduler import cron
        monkeypatch.setenv("ETAPA1_INFORMES_TELEGRAM", "0")
        aurora = MagicMock()
        aurora.respond = AsyncMock(return_value="x")
        with patch("agents.aurora.get_agent", return_value=aurora), \
             patch("tools.crm_client.get_pipeline_stats", new_callable=AsyncMock, return_value={}), \
             patch.object(cron, "_enviar_ejecutivo", new_callable=AsyncMock) as env:
            r = await cron.tarea_reporte_aurora_manana()
        env.assert_not_called()
        assert r["enviado_telegram"] is False

    @pytest.mark.asyncio
    async def test_enviar_ejecutivo_parte_mensajes_largos(self):
        from scheduler import cron
        from channels import telegram_bot as tg
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with patch.object(tg, "_app", MagicMock(bot=bot)), patch.object(tg, "TELEGRAM_CHAT_ID_RODRIGO", 123):
            assert await cron._enviar_ejecutivo("a" * 9000) is True
        assert bot.send_message.await_count == 3

    @pytest.mark.asyncio
    async def test_enviar_ejecutivo_sin_telegram(self):
        from scheduler import cron
        from channels import telegram_bot as tg
        with patch.object(tg, "_app", None):
            assert await cron._enviar_ejecutivo("x") is False


# ─── Endpoints ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
    os.environ.setdefault("CRM_API_KEY", "test-key")
    import main
    return TestClient(main.app)


class TestEndpointsEtapa1:

    @pytest.mark.asyncio
    async def test_health_ia_publico_sin_textos_de_error(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "pw-e1")
        with pytest.raises(RuntimeError):
            await _llamar(FakeOpenRouterProvider(exc=RuntimeError("Incorrect API key sk-abc123")))
        r = client.get("/health/ia")
        assert r.status_code == 200
        assert "sk-abc123" not in r.text and r.json()["errores_recientes_cantidad"] == 1
        assert client.get("/health/ia?detalle=true").status_code == 401
        d = client.get("/health/ia?detalle=true", headers={"X-Api-Key": "pw-e1"})
        assert d.status_code == 200 and "sk-abc123" in d.text

    def test_health_scheduler(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "pw-e1")
        assert client.get("/health/scheduler").status_code == 200
        assert client.get("/health/scheduler?detalle=true").status_code == 401
        assert client.get("/health/scheduler?detalle=true", headers={"X-Api-Key": "pw-e1"}).status_code == 200


def test_informe_no_muestra_senales_internas():
    from scheduler.cron import _limpiar_senales
    t = 'Prioridad: llamar a Juan. [CRM_ACTION:{"tipo":"pagar_cuota","datos":{"venta_id":1}}] [DERIVAR:tomas] Fin.'
    limpio = _limpiar_senales(t)
    assert "CRM_ACTION" not in limpio and "DERIVAR" not in limpio and "llamar a Juan" in limpio
