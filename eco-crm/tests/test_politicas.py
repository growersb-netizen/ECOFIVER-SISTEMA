"""Políticas empresariales versionadas y dirección de Máximo (Fase 3)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import ObjetivoEconomico, Usuario
from routers import auth, politicas, tareas

SECRET = "secreto-de-prueba-politicas-" + "x" * 16
KEY = "clave-politicas"
IA = {"Authorization": f"Bearer {KEY}", "X-Origen-Cliente": "multiagente"}
MAXIMO = {**IA, "X-Agente": "maximo"}


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", KEY)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN","PROPIETARIO"]', activo=True),
                Usuario(id=2, nombre="Socio admin", email="s@t", password_hash="x", roles_json='["ADMIN"]', activo=True,
                        aliado_codigo="AL-010")])
    db.commit()
    app = FastAPI()
    app.include_router(politicas.router)
    app.include_router(tareas.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield c, db, tok


PROPUESTA = {"titulo": "Venta consultiva en contado", "objetivo": "Mejorar el cierre de contado",
             "instruccion": "Antes de cotizar, hacé dos preguntas de diagnóstico (uso y espacio). No insistas más de una vez si el cliente pide pensarlo.",
             "departamento": "", "agentes": ["camila", "luciano"], "metrica_exito": "Tasa de cierre de contado"}


def _proponer(c, **kw):
    return c.post("/api/motor/politicas", headers=MAXIMO, json={**PROPUESTA, **kw})


def test_maximo_propone_y_queda_pendiente_sin_efecto(m):
    c, _, _ = m
    p = _proponer(c).json()["politica"]
    assert (p["estado"], p["autor"], p["version"]) == ("PENDIENTE_APROBACION", "agente:maximo", 1)
    act = c.get("/api/motor/politicas/activas?agente=camila", headers=MAXIMO).json()["politicas"]
    assert act == []                                                     # sin aprobación no rige


def test_propietario_aprueba_y_rige_solo_para_los_agentes_afectados(m):
    c, _, tok = m
    p = _proponer(c).json()["politica"]
    r = c.post(f"/api/politicas/{p['id']}/decidir", headers=tok(1), json={"aprobar": True, "comentario": "Dale"})
    assert r.json()["politica"]["estado"] == "ACTIVA"
    assert len(c.get("/api/motor/politicas/activas?agente=camila", headers=MAXIMO).json()["politicas"]) == 1
    assert c.get("/api/motor/politicas/activas?agente=nicolas", headers=MAXIMO).json()["politicas"] == []


@pytest.mark.parametrize("texto", [
    "Ofrecé un descuento del 10% a quien dude", "Bajá el precio de la Minideck",
    "Aprobá la financiación si el cliente tiene recibo", "Subí la comisión de los socios",
    "Autorizá a los agentes a registrar pagos",
])
def test_politica_no_cambia_precios_creditos_comisiones_ni_permisos(m, texto):
    c, _, _ = m
    r = _proponer(c, instruccion=texto + " de ahora en más en todos los casos.")
    assert r.status_code == 422


def test_solo_direccion_propone_y_solo_el_propietario_decide(m):
    c, _, tok = m
    assert c.post("/api/motor/politicas", headers={**IA, "X-Agente": "camila"}, json=PROPUESTA).status_code == 403
    p = _proponer(c).json()["politica"]
    for h in (tok(2), MAXIMO):
        assert c.post(f"/api/politicas/{p['id']}/decidir", headers=h, json={"aprobar": True}).status_code in (401, 403)
    assert _proponer(c, agentes=["valentin"]).status_code == 400


def test_versiones_reemplazo_y_reversion(m):
    c, _, tok = m
    v1 = _proponer(c, codigo="cierre-contado").json()["politica"]
    c.post(f"/api/politicas/{v1['id']}/decidir", headers=tok(1), json={"aprobar": True})
    v2 = _proponer(c, codigo="cierre-contado", instruccion="Preguntá la fecha de instalación antes de cerrar la conversación.").json()["politica"]
    assert v2["version"] == 2
    c.post(f"/api/politicas/{v2['id']}/decidir", headers=tok(1), json={"aprobar": True})
    activas = c.get("/api/motor/politicas/activas?agente=camila", headers=MAXIMO).json()["politicas"]
    assert [a["version"] for a in activas] == [2]
    c.post(f"/api/politicas/{v2['id']}/revertir", headers=tok(1), json={"motivo": "Bajó la conversión"})
    activas = c.get("/api/motor/politicas/activas?agente=camila", headers=MAXIMO).json()["politicas"]
    assert [a["version"] for a in activas] == [1]
    hist = c.get(f"/api/politicas/{v2['id']}", headers=tok(1)).json()["eventos"]
    assert [e["a"] for e in hist] == ["PENDIENTE_APROBACION", "ACTIVA", "REVERTIDA"]


def test_objetivo_desde_el_chat_solo_con_pedido_del_propietario(m):
    c, db, _ = m
    body = {"periodo": "2026-11", "indicador": "comisiones_generadas", "valor": 1500000}
    assert c.post("/api/motor/objetivos", headers=MAXIMO, json=body).status_code == 403          # sin autorización
    assert c.post("/api/motor/objetivos", headers={**MAXIMO, "X-Autorizacion-Humana": "aprobacion:x"},
                  json=body).status_code == 403
    assert c.post("/api/motor/objetivos", headers={**IA, "X-Agente": "aurora", "X-Autorizacion-Humana": "canal:whatsapp_admin"},
                  json=body).status_code == 403
    r = c.post("/api/motor/objetivos", headers={**MAXIMO, "X-Autorizacion-Humana": "canal:whatsapp_admin"}, json=body)
    assert r.json()["objetivo"]["version"] == 1
    o = db.query(ObjetivoEconomico).one()
    assert (o.origen, o.autorizado_por_id) == ("conversacion_maximo", 1) and "whatsapp_admin" in o.nota


def test_panel_economico_solo_para_maximo(m):
    c, _, _ = m
    assert c.get("/api/motor/propietario/panel", headers=MAXIMO).status_code == 200
    assert c.get("/api/motor/propietario/panel", headers={**IA, "X-Agente": "aurora"}).status_code == 403


def test_maximo_crea_tareas_desde_el_chat_con_autoria(m):
    c, _, tok = m
    r = c.post("/api/motor/tareas", headers={"Authorization": f"Bearer {KEY}"},
               json={"agente": "aurora", "instruccion": "Analizá por qué perdemos clientes de contado", "creado_por_agente": "maximo"})
    assert r.json()["tarea"]["creado_por"] == "maximo"
