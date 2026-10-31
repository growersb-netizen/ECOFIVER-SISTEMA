"""Los roles ADMISION y PROPIETARIO se asignan desde la pantalla de usuarios, solo por un ADMIN."""
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
from database.models import Usuario
from routers import auth

SECRET = "secreto-de-prueba-roles-" + "x" * 16


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN"]', activo=True),
                Usuario(id=2, nombre="Coordinador", email="c@t", password_hash="x", roles_json='["COORDINADOR_OPERATIVO"]', activo=True),
                Usuario(id=3, nombre="Socio", email="s@t", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True,
                        aliado_codigo="AL-010")])
    db.commit()
    app = FastAPI()
    app.include_router(auth.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield TestClient(app), db, tok


def test_roles_nuevos_disponibles_en_la_pantalla():
    claves = [k for k, _ in auth.ROLES_DISPONIBLES]
    assert "ADMISION" in claves and "PROPIETARIO" in claves


def test_admin_asigna_admision_y_propietario(m):
    c, db, tok = m
    assert c.put("/api/usuarios/3", headers=tok(1), json={"roles": ["ASESOR_APERTURA", "ADMISION"]}).status_code == 200
    assert c.put("/api/usuarios/1", headers=tok(1), json={"roles": ["ADMIN", "PROPIETARIO", "ADMISION"]}).status_code == 200
    lista = {u["id"]: u for u in c.get("/api/usuarios", headers=tok(1)).json()}
    assert lista[3]["roles"] == ["ASESOR_APERTURA", "ADMISION"] and lista[3]["aliado_codigo"] == "AL-010"
    assert set(lista[1]["roles"]) == {"ADMIN", "PROPIETARIO", "ADMISION"}


@pytest.mark.parametrize("roles", [["ASESOR_APERTURA", "ADMISION"], ["ASESOR_APERTURA", "PROPIETARIO"]])
def test_coordinador_no_da_roles_sensibles(m, roles):
    c, _, tok = m
    assert c.put("/api/usuarios/3", headers=tok(2), json={"roles": roles}).status_code == 403
    assert c.post("/api/usuarios", headers=tok(2), json={"nombre": "X", "email": "x@x.com", "password": "123456",
                                                          "roles": roles}).status_code == 403


def test_coordinador_no_quita_admision_pero_edita_lo_demas(m):
    c, _, tok = m
    c.put("/api/usuarios/3", headers=tok(1), json={"roles": ["ASESOR_APERTURA", "ADMISION"]})
    assert c.put("/api/usuarios/3", headers=tok(2), json={"roles": ["ASESOR_APERTURA"]}).status_code == 403
    assert c.put("/api/usuarios/3", headers=tok(2), json={"roles": ["ASESOR_APERTURA", "ADMISION", "FABRICA"]}).status_code == 200
