"""Gestión de leads vía HTTP, aislada de producción y mensajería."""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base, get_db
from database.models import Aliado, Interaccion, Lead, Usuario
from routers import auth, leads, socios


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    owner = Usuario(nombre="Responsable", email="owner@test.invalid", password_hash="unused",
                    roles_json='["ASESOR_APERTURA"]')
    stranger = Usuario(nombre="Otro", email="other@test.invalid", password_hash="unused",
                       roles_json='["ASESOR_APERTURA"]')
    socio = Aliado(codigo="AL-TEST", nombre="Socio", estado="activo")
    other_socio = Aliado(codigo="AL-OTHER", nombre="Otro socio", estado="activo")
    db.add_all([owner, stranger, socio, other_socio])
    db.flush()
    lead = Lead(nombre="Prueba Meta", telefono="5491111111111", origen="META_ADS",
                asesor_apertura_id=owner.id)
    lead_socio = Lead(nombre="Prueba aliado Meta", telefono="5491122222222", origen="META_ADS",
                      aliado_codigo=socio.codigo, notas="Formulario Plan 18 pasos")
    db.add_all([lead, lead_socio])
    db.commit()
    app = FastAPI()
    app.include_router(leads.router)
    app.include_router(socios.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.require_auth] = lambda: owner
    app.dependency_overrides[socios.require_socio] = lambda: socio
    with TestClient(app) as client:
        yield client, db, app, owner, stranger, socio, other_socio, lead, lead_socio
    db.close()
    engine.dispose()


def test_asesor_guarda_contacto_y_lee_historial(setup):
    client, db, app, owner, stranger, socio, other_socio, lead, lead_socio = setup
    response = client.post(f"/api/leads/{lead.id}/registrar-contacto", json={
        "resultado": "INTERESADO", "notas": "Pidió una propuesta del plan 18 pasos"})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Lead, lead.id).estado == "CONTACTADO"
    history = client.get(f"/api/leads/{lead.id}/interacciones")
    assert history.status_code == 200
    assert history.json()[0]["asesor_id"] == owner.id
    assert "18 pasos" in history.json()[0]["notas"]


def test_otro_asesor_no_gestiona_ni_lee_historial(setup):
    client, db, app, owner, stranger, socio, other_socio, lead, lead_socio = setup
    app.dependency_overrides[auth.require_auth] = lambda: stranger
    for method, url, data in [
        ("post", f"/api/leads/{lead.id}/registrar-contacto", {"resultado": "CERRO_VENTA"}),
        ("post", f"/api/leads/{lead.id}/interacciones", {"notas": "Ajeno"}),
        ("get", f"/api/leads/{lead.id}/interacciones", None),
    ]:
        kwargs = {"json": data} if data is not None else {}
        assert getattr(client, method)(url, **kwargs).status_code == 403
    assert db.query(Interaccion).count() == 0
    assert db.get(Lead, lead.id).estado == "NUEVO"


def test_socio_preserva_historial_y_fecha_de_seguimiento(setup):
    client, db, app, owner, stranger, socio, other_socio, lead, lead_socio = setup
    response = client.put(f"/api/socio/leads/{lead_socio.id}", json={
        "estado": "EN_SEGUIMIENTO", "notas": "Llamar después de las 18",
        "proximo_seguimiento": "2026-11-02T18:00:00-03:00"})
    assert response.status_code == 200
    db.expire_all()
    saved = db.get(Lead, lead_socio.id)
    assert saved.estado == "EN_SEGUIMIENTO" and saved.proximo_seguimiento is not None
    history = db.query(Interaccion).filter_by(lead_id=lead_socio.id).one()
    record = json.loads(history.notas)
    assert record["aliado"] == socio.codigo
    assert record["cambios"]["notas"]["antes"] == "Formulario Plan 18 pasos"
    assert record["cambios"]["notas"]["despues"] == "Llamar después de las 18"
    app.dependency_overrides[socios.require_socio] = lambda: other_socio
    assert client.put(f"/api/socio/leads/{lead_socio.id}", json={"notas": "Ajeno"}).status_code == 404


def test_fecha_invalida_no_confirma_gestion_que_no_guardo(setup):
    client, db, app, owner, stranger, socio, other_socio, lead, lead_socio = setup
    response = client.put(f"/api/socio/leads/{lead_socio.id}", json={
        "estado": "CONTACTADO", "proximo_seguimiento": "mañana"})
    assert response.status_code == 422
    assert db.get(Lead, lead_socio.id).estado == "NUEVO"
    assert db.query(Interaccion).count() == 0


@pytest.mark.parametrize("resultado,estado", [("CERRO_VENTA", "CERRADO_GANADO"),
                                             ("NO_INTERESA", "CERRADO_PERDIDO")])
def test_cierre_usa_estados_del_crm(setup, resultado, estado):
    client, db, app, owner, stranger, socio, other_socio, lead, lead_socio = setup
    response = client.post(f"/api/leads/{lead.id}/registrar-contacto", json={"resultado": resultado})
    assert response.status_code == 200 and response.json()["nuevo_estado"] == estado
