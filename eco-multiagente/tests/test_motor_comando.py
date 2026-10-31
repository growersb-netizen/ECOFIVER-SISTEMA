"""/api/comando encola tareas en el motor; nunca informa una orden como ejecutada."""
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CRM_BASE_URL", "http://mock-crm")
os.environ.setdefault("CRM_API_KEY", "test-key")


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "pw-motor-123")
    monkeypatch.delenv("MULTIAGENTE_API_KEY", raising=False)
    import main
    return TestClient(main.app)


H = {"X-Api-Key": "pw-motor-123"}


def test_aviso_con_tarea_existente_despierta_al_motor(web):
    from tools import motor_tareas
    with patch.object(motor_tareas, "despertar") as d, patch.object(motor_tareas, "crear_tarea", AsyncMock()) as crear:
        r = web.post("/api/comando", headers=H, json={"instruccion": "x", "agente": "aurora",
                                                       "contexto": {"tarea_id": 42}})
    assert r.json() == {"ok": True, "tarea_id": 42, "estado": "EN_COLA", "motor_activo": True}
    d.assert_called_once()
    crear.assert_not_called()


def test_aviso_sin_tarea_la_crea_en_el_crm(web):
    from tools import motor_tareas
    with patch.object(motor_tareas, "crear_tarea", AsyncMock(return_value={"id": 7})) as crear, \
         patch.object(motor_tareas, "despertar"):
        r = web.post("/api/comando", headers=H, json={"instruccion": "Resumen del pipeline", "agente": "aurora"})
    assert r.json()["tarea_id"] == 7 and r.json()["estado"] == "EN_COLA"
    assert crear.await_args.args == ("aurora", "Resumen del pipeline")


def test_si_el_crm_no_registra_la_tarea_no_responde_ok(web):
    from tools import motor_tareas
    with patch.object(motor_tareas, "crear_tarea", AsyncMock(side_effect=RuntimeError("CRM caído"))):
        r = web.post("/api/comando", headers=H, json={"instruccion": "x", "agente": "aurora"})
    assert r.status_code == 502 and r.json()["ok"] is False


def test_requiere_clave(web):
    assert web.post("/api/comando", json={"instruccion": "x"}).status_code == 401
    assert web.post("/api/comando", headers={"X-Api-Key": "otra"}, json={"instruccion": "x"}).status_code == 401


def test_motor_se_puede_apagar(monkeypatch):
    from tools import motor_tareas
    monkeypatch.setenv("MOTOR_TAREAS", "off")
    assert not motor_tareas.habilitado()
    monkeypatch.delenv("MOTOR_TAREAS")
    assert motor_tareas.habilitado()


def test_health_motor_sin_contenido(web):
    d = web.get("/health/motor").json()
    assert {"habilitado", "ejecutadas", "fallidas", "worker"} <= set(d)
