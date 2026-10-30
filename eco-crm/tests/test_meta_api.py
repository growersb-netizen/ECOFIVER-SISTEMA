"""Contrato HTTP de ingreso Meta sin startup ni conexiones externas."""
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
from database.models import Lead, Usuario
from routers import agentes


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-meta-api-only")
    monkeypatch.delenv("API_KEY_ANTERIOR", raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(Usuario(nombre="Asesor test", email="test@example.invalid", password_hash="unused",
                       roles_json='["ASESOR_APERTURA"]', activo=True))
        db.commit()
        app = FastAPI()
        app.include_router(agentes.router)
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def test_auth_es_obligatoria_para_registrar(api):
    client, db = api
    for headers in ({}, {"Authorization": "Bearer incorrecto"}, {"X-API-Key": "incorrecto"}):
        response = client.post("/api/leads/meta", json={"meta_lead_id": "test-1"}, headers=headers)
        assert response.status_code == 401
    assert db.query(Lead).count() == 0


def test_ingreso_y_reintento_http_conservan_responsable(api):
    client, db = api
    headers = {"Authorization": "Bearer test-meta-api-only"}
    payload = {"meta_lead_id": "test-plan-18", "form_id": "form-test-18", "nombre": "Prueba local",
               "telefono": "+54 9 11 1111 1111", "email": "test@example.invalid"}
    first = client.post("/api/leads/meta", json=payload, headers=headers)
    assert first.status_code == 200
    registered = first.json()
    assert registered["created"] is True
    assert registered["asesor_apertura_id"]
    assert registered["origen"] == "META_ADS"
    second = client.post("/api/leads/meta", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == registered["id"]
    assert second.json()["created"] is False
    assert second.json()["duplicate_event"] is True
    assert db.query(Lead).count() == 1


def test_rechaza_formulario_sin_identidad(api):
    client, db = api
    response = client.post("/api/leads/meta", json={"nombre": "Sin identificador"},
                           headers={"Authorization": "Bearer test-meta-api-only"})
    assert response.status_code == 422
    assert db.query(Lead).count() == 0
