"""Recuperación de lead con identidad de página y renovación sin filtrar tokens."""
import os
import sys

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base, get_db
from database.encryption import encrypt_value
from database.models import ConfiguracionSistema, MetaPagina
from routers import agentes

HEADERS = {"Authorization": "Bearer api-meta-test"}
PATH = "/api/leads/meta-datos/1001?page_id=634872006383162"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("API_KEY", "api-meta-test")
    monkeypatch.setenv("ENCRYPTION_KEY", "clave-local-test")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(MetaPagina(page_id="634872006383162", nombre="Eco Prueba", activa=True,
                          page_token="token-expirado-secreto"))
        db.add(ConfiguracionSistema(clave="meta_page_access_token", es_secreto=True,
                                    valor=encrypt_value("token-global-secreto")))
        db.commit()
        app = FastAPI()
        app.include_router(agentes.router)
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def _mock_graph(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_datos_requieren_api_key_y_pagina_activa(api, monkeypatch):
    client, db = api
    def no_network(request):
        raise AssertionError("No debe consultar Meta")
    _mock_graph(monkeypatch, no_network)
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers={"Authorization": "Bearer otra"}).status_code == 401
    assert client.get("/api/leads/meta-datos/abc?page_id=634872006383162", headers=HEADERS).status_code == 422
    assert client.get("/api/leads/meta-datos/1001?page_id=invalid", headers=HEADERS).status_code == 422
    assert client.get("/api/leads/meta-datos/1001?page_id=999", headers=HEADERS).status_code == 404
    db.query(MetaPagina).update({MetaPagina.activa: False})
    db.commit()
    assert client.get(PATH, headers=HEADERS).status_code == 404


def test_renueva_token_expirado_con_global_y_no_lo_devuelve(api, monkeypatch, caplog):
    client, db = api
    seen = []
    def graph(request):
        seen.append(request)
        assert "access_token" not in request.url.params
        token = request.headers["Authorization"]
        if token == "Bearer token-expirado-secreto":
            return httpx.Response(400, json={"error": {"code": 190, "error_subcode": 463,
                                                        "message": "token-expirado-secreto"}})
        if request.url.path.endswith("634872006383162"):
            assert token == "Bearer token-global-secreto"
            assert request.url.params["fields"] == "access_token"
            return httpx.Response(200, json={"access_token": "token-renovado-secreto"})
        assert token == "Bearer token-renovado-secreto"
        return httpx.Response(200, json={"id": "1001", "form_id": "form-plan18",
                                         "field_data": [{"name": "full_name", "values": ["Prueba"]}],
                                         "access_token": "token-no-debe-salir"})
    _mock_graph(monkeypatch, graph)
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["field_data"][0]["values"] == ["Prueba"]
    assert "access_token" not in response.json()
    assert len(seen) == 3
    db.expire_all()
    assert db.query(MetaPagina).first().page_token == "token-renovado-secreto"
    assert not any(token in response.text + caplog.text for token in (
        "token-expirado-secreto", "token-global-secreto", "token-renovado-secreto", "token-no-debe-salir"))


def test_usa_token_de_pagina_vigente_sin_renovar(api, monkeypatch):
    client, db = api
    seen = []
    def graph(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "1001", "field_data": []})
    _mock_graph(monkeypatch, graph)
    assert client.get(PATH, headers=HEADERS).status_code == 200
    assert len(seen) == 1


def test_permiso_faltante_no_renueva_ni_filtra_error_meta(api, monkeypatch, caplog):
    client, db = api
    seen = []
    def graph(request):
        seen.append(request)
        return httpx.Response(403, json={"error": {"code": 200, "message": "token-expirado-secreto"}})
    _mock_graph(monkeypatch, graph)
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 503
    assert len(seen) == 1
    assert "token-expirado-secreto" not in response.text + caplog.text


def test_refresh_fallido_no_filtra_credenciales(api, monkeypatch, caplog):
    client, db = api
    def graph(request):
        return httpx.Response(400, json={"error": {"code": 190, "message": "token-global-secreto"}})
    _mock_graph(monkeypatch, graph)
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 503
    assert "token-global-secreto" not in response.text + caplog.text
    assert db.query(MetaPagina).first().page_token == "token-expirado-secreto"
