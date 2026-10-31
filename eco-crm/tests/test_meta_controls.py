"""Controles de reparto: permisos reales, persistencia y conexión de formularios."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base, get_db
from database.models import (
    Aliado, AuditLog, Lead, MetaPagina, Usuario,
    MetaLeadCampana, MetaLeadDestino, MetaLeadOrganizacion,
)
from routers import auth, reparto_meta

SECRET = "reparto-test-no-production-secret"


def token(identity, kind=None):
    data = {"sub": str(identity), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    if kind:
        data["typ"] = kind
    return jwt.encode(data, SECRET, algorithm="HS256")


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([
            Usuario(id=7, nombre="Admin", email="admin@test.invalid", password_hash="x", roles_json='["ADMIN"]', activo=True),
            Usuario(id=8, nombre="Claudia CRM", email="claudia@test.invalid", password_hash="x", roles_json='["ADMIN"]', activo=True, aliado_codigo="AL-010"),
            Usuario(id=10, nombre="Admin collision", email="collision@test.invalid", password_hash="x", roles_json='["ADMIN"]', activo=True),
            Usuario(id=9, nombre="Asesor", email="asesor@test.invalid", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True),
            Aliado(id=2, codigo="AL-002", nombre="Rodrigo", estado="activo", password_hash="x", es_admin_crm=True, es_organizador=True),
            # La restricción aplica aunque Claudia esté marcada como admin global.
            Aliado(id=10, codigo="AL-010", nombre="Claudia", estado="activo", password_hash="x", es_admin_crm=True, es_organizador=False),
            Aliado(id=22, codigo="AL-022", nombre="Miembro", estado="activo", password_hash="x", organizacion_codigo="AL-010"),
            Aliado(id=99, codigo="AL-099", nombre="Ajeno", estado="activo", password_hash="x", organizacion_codigo="AL-002"),
            Aliado(id=98, codigo="AL-098", nombre="Inactivo", estado="inactivo", password_hash="x", organizacion_codigo="AL-010"),
            MetaPagina(page_id="300", nombre="Página de prueba", activa=True, page_token="old-page-token"),
            MetaLeadCampana(form_id="100", page_id="300", nombre="Plan 18 Pasos", producto="MODULO", activa=True),
            MetaLeadCampana(form_id="200", page_id="300", nombre="Piscinas", producto="PISCINA", activa=True),
        ])
        db.commit()
        app = FastAPI()
        app.include_router(reparto_meta.router)
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def root():
    return {"Authorization": f"Bearer {token(7)}"}


def claudia():
    return {"Cookie": f"socio_token={token(10, 'socio')}"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad"}])
def test_requiere_sesion_valida(setup, headers):
    client, _ = setup
    assert client.get("/api/reparto-meta", headers=headers).status_code == 401


@pytest.mark.parametrize("headers", [claudia(), {"Authorization": f"Bearer {token(8)}"},
                                      {"Cookie": f"access_token={token(10, 'socio')}"}])
def test_claudia_siempre_limitada_a_su_organizacion_incluso_admin_y_colision(setup, headers):
    client, db = setup
    response = client.get("/api/reparto-meta", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["alcance"] == "organizacion" and data["organizacion_codigo"] == "AL-010"
    assert not data["puede_crear_campanas"] and not data["puede_repartir_pendientes"]
    assert {row["codigo"] for row in data["destinatarios"]} == {"AL-010", "AL-022", "AL-098"}
    assert "AL-099" not in response.text
    denied = client.patch("/api/reparto-meta/destinos/aliado:AL-099", json={"habilitado": True}, headers=headers)
    assert denied.status_code == 403
    assert db.get(MetaLeadDestino, "aliado:AL-099") is None
    assert client.patch("/api/reparto-meta/organizaciones/AL-002/campanas/100", json={"habilitada": True}, headers=headers).status_code == 403
    assert client.post("/api/reparto-meta/pendientes", json={"form_id": "100"}, headers=headers).status_code == 403


def test_socio_cookie_tiene_precedencia_sobre_cookie_crm_coexistente(setup):
    client, _ = setup
    response = client.get("/api/reparto-meta", headers={"Cookie": f"socio_token={token(10, 'socio')}; access_token={token(7)}"})
    assert response.json()["alcance"] == "organizacion"


def test_root_crm_y_socio_admin_acceso_global(setup):
    client, _ = setup
    for headers in (root(), {"Cookie": f"socio_token={token(2, 'socio')}"}):
        data = client.get("/api/reparto-meta", headers=headers).json()
        assert data["alcance"] == "global" and data["puede_crear_campanas"]
        assert data["paginas"] == [{"page_id": "300", "nombre": "Página de prueba"}]
        assert "asesor:9" in {row["clave"] for row in data["destinatarios"]}


def test_toggle_guarda_actor_y_booleanos_estrictos(setup):
    client, db = setup
    path = "/api/reparto-meta/destinos/aliado:AL-022"
    for bad in ({"habilitado": "false"}, {"habilitado": None}, {"otro": True}, {}):
        assert client.patch(path, json=bad, headers=claudia()).status_code == 422
    response = client.patch(path, json={"habilitado": True, "modulos": True}, headers=claudia())
    assert response.status_code == 200
    pref = db.get(MetaLeadDestino, "aliado:AL-022")
    assert pref.habilitado and pref.modulos and not pref.piscinas
    assert pref.actualizado_por == "AL-010"
    audit = db.query(AuditLog).filter_by(table_name="meta_lead_destinos").first()
    assert "AL-010" in audit.usuario_nombre and "AL-022" in audit.changed_fields
    assert client.patch("/api/reparto-meta/destinos/aliado:AL-098", json={"habilitado": True}, headers=claudia()).status_code == 422


def test_toggle_recupera_pendientes_sin_reasignar_gestion(setup):
    from utils.meta_ingreso import registrar_formulario_meta
    client, db = setup
    lead = registrar_formulario_meta(db, {"meta_lead_id": "lead-a", "form_id": "100", "page_id": "300", "telefono": "111"})
    assert not lead.aliado_codigo
    gate = client.patch("/api/reparto-meta/organizaciones/AL-010/campanas/100", json={"habilitada": True}, headers=claudia())
    assert gate.status_code == 200
    response = client.patch("/api/reparto-meta/destinos/aliado:AL-022", json={"habilitado": True, "modulos": True}, headers=claudia())
    assert response.status_code == 200 and response.json()["asignados"] == 1
    db.expire_all()
    assert db.get(Lead, lead.id).aliado_codigo == "AL-022"
    assert client.patch("/api/reparto-meta/destinos/aliado:AL-022", json={"habilitado": False}, headers=claudia()).status_code == 200
    assert db.get(Lead, lead.id).aliado_codigo == "AL-022"
    assert client.post("/api/reparto-meta/pendientes", json={}, headers=root()).status_code == 200


def test_campana_solo_global_y_producto_valido(setup):
    client, db = setup
    payload = {"form_id": "400", "page_id": "300", "nombre": "Nueva piscina", "producto": "PISCINA", "activa": False}
    assert client.post("/api/reparto-meta/campanas", json=payload, headers=claudia()).status_code == 403
    assert client.post("/api/reparto-meta/campanas", json={**payload, "producto": "TODO"}, headers=root()).status_code == 422
    assert client.post("/api/reparto-meta/campanas", json=payload, headers=root()).status_code == 200
    assert db.get(MetaLeadCampana, "400").producto == "PISCINA"
    assert client.post("/api/reparto-meta/campanas", json=payload, headers=root()).status_code == 409


def mock_meta(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(reparto_meta.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler)))


def test_listado_formularios_renueva_y_no_devuelve_secretos_y_pagina(setup, monkeypatch):
    from routers import configuracion
    client, db = setup
    monkeypatch.setattr(configuracion, "get_config_value", lambda *args: "global-private-token")
    calls = []

    def handle(request):
        calls.append(request)
        if request.headers["Authorization"] == "Bearer old-page-token":
            return httpx.Response(400, json={"error": {"code": 190}})
        if request.url.path.endswith("/300"):
            return httpx.Response(200, json={"access_token": "renewed-private-token"})
        assert request.headers["Authorization"] == "Bearer renewed-private-token"
        if request.url.params.get("after"):
            return httpx.Response(200, json={"data": [{"id": "101", "name": "Segundo", "status": "ACTIVE"}]})
        return httpx.Response(200, json={"data": [{"id": "100", "name": "Plan18", "status": "ACTIVE", "access_token": "do-not-expose"}],
                                       "paging": {"next": "https://irrelevant.invalid/?access_token=secret", "cursors": {"after": "cursor"}}})

    mock_meta(monkeypatch, handle)
    assert client.get("/api/reparto-meta/formularios?page_id=300", headers=claudia()).status_code == 403
    response = client.get("/api/reparto-meta/formularios?page_id=300", headers=root())
    assert response.status_code == 200
    assert len(response.json()["forms"]) == 2 and not response.json()["has_more"]
    assert "token" not in response.text and "secret" not in response.text
    db.expire_all()
    assert db.query(MetaPagina).filter_by(page_id="300").first().page_token == "renewed-private-token"


def test_activar_campana_suscribe_leadgen_y_fallo_no_activa(setup, monkeypatch):
    client, db = setup
    payload = {"form_id": "400", "page_id": "300", "nombre": "Nueva piscina", "producto": "PISCINA", "activa": True}
    calls, state = [], {"allow": False}

    def handle(request):
        calls.append(request)
        assert request.method == "POST" and request.url.path.endswith("/subscribed_apps")
        assert b"leadgen" in request.content and b"messages" in request.content
        return httpx.Response(200, json={"success": True}) if state["allow"] else httpx.Response(403, json={"error": {"code": 200}})

    mock_meta(monkeypatch, handle)
    response = client.post("/api/reparto-meta/campanas", json=payload, headers=root())
    assert response.status_code == 503 and db.get(MetaLeadCampana, "400") is None
    state["allow"] = True
    response = client.post("/api/reparto-meta/campanas", json=payload, headers=root())
    assert response.status_code == 200 and db.get(MetaLeadCampana, "400").activa


def test_cookie_crm_historica_de_claudia_sin_vinculo_no_es_admin_global(setup):
    client, db = setup
    user = Usuario(id=55, nombre="Claudia histórica", email="socio.admin.al010@ecofiver.crm",
                   password_hash="unused", roles_json='["ADMIN"]', activo=True,
                   aliado_codigo=None)
    db.add(user)
    db.commit()
    headers = {"Cookie": f"access_token={token(user.id)}"}
    data = client.get("/api/reparto-meta", headers=headers).json()
    assert data["alcance"] == "organizacion"
    assert data["organizacion_codigo"] == "AL-010"
    assert not data["puede_crear_campanas"]
    assert client.patch("/api/reparto-meta/destinos/aliado:AL-099", json={"habilitado": True},
                        headers=headers).status_code == 403
    assert client.patch("/api/reparto-meta/organizaciones/AL-002/campanas/100",
                        json={"habilitada": True}, headers=headers).status_code == 403
    assert db.get(MetaLeadDestino, "aliado:AL-099") is None


@pytest.mark.parametrize("existing", [True, False])
def test_sso_admin_vincula_usuario_socio_antes_de_emitir_sesion(setup, monkeypatch, existing):
    from routers import socios
    client, db = setup
    roles = '["ADMIN", "FABRICA"]'
    if existing:
        db.add(Usuario(id=55, nombre="Claudia histórica", email="socio.admin.al010@ecofiver.crm",
                       password_hash="unused", roles_json=roles, activo=True, aliado_codigo=None))
        db.commit()
    client.app.add_api_route("/socio/acceso-admin", socios.socio_acceso_admin, methods=["GET"])
    client.app.dependency_overrides[socios.require_socio] = lambda: db.get(Aliado, 10)
    monkeypatch.setattr(socios, "hash_password", lambda _value: "test-hash-unused")
    response = client.get("/socio/acceso-admin", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/aliados"
    user = db.query(Usuario).filter_by(email="socio.admin.al010@ecofiver.crm").one()
    assert user.aliado_codigo == "AL-010"
    assert user.roles_json == (roles if existing else json.dumps(["ADMIN"]))
    headers = {"Cookie": f"access_token={response.cookies['access_token']}"}
    assert client.get("/api/reparto-meta", headers=headers).json()["alcance"] == "organizacion"
