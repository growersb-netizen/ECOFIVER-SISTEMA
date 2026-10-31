"""Control empresarial (Fase 2): estados por agente y departamento, horario, guardias, actividad real."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import AgenteControlEvento, Usuario
from routers import agentes_control, auth, tareas
from utils import control_agentes as ctl
from utils import motor_tareas as motor

SECRET = "secreto-de-prueba-control-" + "x" * 16
KEY = "clave-servicio-control"
H = {"Authorization": f"Bearer {KEY}"}


def utc_ar(y, mo, d, h, mi=0):
    """Hora argentina → UTC naive (ART = UTC-3, sin horario de verano)."""
    return datetime(y, mo, d, h, mi) + timedelta(hours=3)


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", KEY)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN"]', activo=True),
                Usuario(id=2, nombre="Vend", email="v@t", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True)])
    db.commit()
    app = FastAPI()
    app.include_router(tareas.router)
    app.include_router(agentes_control.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield TestClient(app), db, tok


@pytest.mark.parametrize("cuando,esperado", [
    (utc_ar(2026, 11, 2, 9, 0), True),     # lunes 09:00
    (utc_ar(2026, 11, 2, 20, 59), True),   # lunes 20:59
    (utc_ar(2026, 11, 2, 21, 0), False),   # lunes 21:00
    (utc_ar(2026, 11, 2, 8, 59), False),   # lunes 08:59
    (utc_ar(2026, 11, 7, 12, 0), True),    # sábado
    (utc_ar(2026, 11, 8, 12, 0), False),   # domingo
])
def test_horario_lunes_a_sabado_9_a_21_hora_argentina(cuando, esperado):
    assert ctl.en_horario(cuando) is esperado


def test_todos_activos_por_defecto_y_16_agentes_sin_valentin(m):
    c, _, tok = m
    d = c.get("/api/agentes/control", headers=tok(1)).json()
    nombres = {a["agente"] for a in d["agentes"]}
    assert len(nombres) == 16 and "valentin" not in nombres
    assert all(a["estado"] == "ACTIVO" for a in d["agentes"])


def test_pausar_requiere_motivo_y_queda_auditado(m):
    c, db, tok = m
    assert c.post("/api/agentes/camila/estado", headers=tok(1), json={"estado": "PAUSADO"}).status_code == 400
    r = c.post("/api/agentes/camila/estado", headers=tok(1), json={"estado": "PAUSADO", "motivo": "Revisión de guion"})
    assert r.json()["estado_anterior"] == "ACTIVO"
    ev = db.query(AgenteControlEvento).one()
    assert (ev.agente, ev.estado_nuevo, ev.usuario_id) == ("camila", "PAUSADO", 1)


def test_departamento_cambia_todos_sus_agentes(m):
    c, db, tok = m
    r = c.post("/api/departamentos/administracion/estado", headers=tok(1),
               json={"estado": "DESACTIVADO", "motivo": "Cierre contable"}).json()
    assert {x["agente"] for x in r["cambios"]} == {"ezequiel", "elena", "ignacio"}
    est = ctl.estados(db)
    assert est["elena"]["estado"] == "DESACTIVADO" and est["aurora"]["estado"] == "ACTIVO"


def test_permisos(m):
    c, _, tok = m
    assert c.post("/api/agentes/camila/estado", headers=tok(2), json={"estado": "PAUSADO", "motivo": "x x x"}).status_code == 403
    assert c.post("/api/agentes/camila/estado", headers=H, json={"estado": "PAUSADO", "motivo": "x x x"}).status_code == 401
    assert c.get("/api/agentes/control").status_code == 401
    assert c.get("/api/motor/control", headers=tok(1)).status_code == 401
    assert c.post("/api/agentes/valentin/estado", headers=tok(1), json={"estado": "ACTIVO"}).status_code == 404


def test_motor_no_da_tareas_a_agentes_pausados(m):
    c, db, tok = m
    motor.crear_tarea(db, agente="camila", instruccion="x")
    ctl.cambiar_estado(db, "camila", "PAUSADO", "prueba", 1)
    control = c.get("/api/motor/control", headers=H).json()
    activos = [a for a, e in control["estados"].items() if e == "ACTIVO"]
    assert "camila" not in activos
    assert motor.reclamar(db, "w", set(activos)) is None


def test_salientes_fuera_de_horario_solo_con_guardia(m):
    c, db, tok = m
    domingo = utc_ar(2026, 11, 8, 12)
    assert ctl.salida_permitida(db, "valentina", domingo) == (False, "fuera del horario (lunes a sábado 09–21)")
    r = c.post("/api/guardias", headers=tok(1), json={
        "alcance": "dep:comercial", "desde": (domingo - timedelta(hours=1)).isoformat() + "Z",
        "hasta": (domingo + timedelta(hours=4)).isoformat() + "Z", "motivo": "Lanzamiento de temporada"})
    assert r.status_code == 200, r.text
    assert ctl.salida_permitida(db, "valentina", domingo) == (True, "guardia autorizada")
    assert ctl.salida_permitida(db, "renata", domingo)[0] is False             # otro departamento
    ctl.cambiar_estado(db, "valentina", "PAUSADO", "pausa", 1)
    assert ctl.salida_permitida(db, "valentina", domingo) == (False, "agente pausado")


@pytest.mark.parametrize("cuerpo", [
    {"alcance": "dep:inexistente", "horas": 2},
    {"alcance": "agente:valentin", "horas": 2},
    {"alcance": "todos", "horas": 100},
    {"alcance": "todos", "horas": -1},
])
def test_guardias_invalidas(m, cuerpo):
    c, _, tok = m
    ahora = datetime.utcnow()
    r = c.post("/api/guardias", headers=tok(1), json={
        "alcance": cuerpo["alcance"], "desde": ahora.isoformat() + "Z",
        "hasta": (ahora + timedelta(hours=cuerpo["horas"])).isoformat() + "Z", "motivo": "prueba"})
    assert r.status_code == 400


def test_actividad_real_distinta_del_estado_administrativo(m):
    c, db, tok = m
    t, _ = motor.crear_tarea(db, agente="aurora", instruccion="Análisis")
    motor.reclamar(db, "w")
    ctl.cambiar_estado(db, "aurora", "PAUSADO", "pausa durante la ejecución", 1)
    a = next(x for x in c.get("/api/agentes/control", headers=tok(1)).json()["agentes"] if x["agente"] == "aurora")
    assert a["estado"] == "PAUSADO" and a["actividad"]["tarea_en_curso"]["id"] == t.id


def test_pagina_operaciones_solo_admin_humano(m):
    c, _, tok = m
    from fastapi.templating import Jinja2Templates  # noqa: F401
    r = c.get("/operaciones-ia", headers=tok(1))
    assert r.status_code == 200 and "Operaciones IA" in r.text and "esc(" in r.text
    assert c.get("/operaciones-ia", headers=tok(2)).status_code == 403
    assert c.get("/operaciones-ia").status_code == 401


def test_oficina_virtual_solo_admin_humano_y_sin_dependencias_externas(m):
    c, _, tok = m
    r = c.get("/oficina-ia", headers=tok(1))
    assert r.status_code == 200 and "/static/js/oficina-ia.js" in r.text and "/operaciones-ia" in r.text
    assert c.get("/oficina-ia", headers=tok(2)).status_code == 403
    assert c.get("/oficina-ia").status_code == 401
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(raiz, "static/js/oficina-ia.js"), encoding="utf-8").read()
    assert "http://" not in js and "https://" not in js                      # motor 3D vendorizado, sin CDN
    assert "MIT License" in open(os.path.join(raiz, "static/vendor/three/LICENSE"), encoding="utf-8").read()
    # la escena solo lee endpoints reales del motor; no fabrica estados
    for url in ("/api/agentes/control", "/api/aprobaciones", "/api/admision/resumen"):
        assert url in js
