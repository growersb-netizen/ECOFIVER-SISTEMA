"""
Matriz de autorización (Fase 0.5): roles × recursos, verificada en el servidor.

Roles: administrador CRM, vendedor (ASESOR_APERTURA), supervisor, cobranzas,
organizador (socio con organización), socio vendedor, sin sesión, servicio
interno / agente IA (API key).
Recursos: reparto Meta, leads, información financiera, Control Center.
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import Aliado, Lead, Usuario
from routers import auth, cobranzas, control_agentes, leads, reparto_meta, socios
from utils import sesiones

SECRET = "secreto-de-prueba-matriz-" + "x" * 20
API_KEY = "clave-servicio-matriz"


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setattr(socios, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", API_KEY)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    # Los ids de Usuario y Aliado se superponen a propósito (1, 2, 3…)
    usuarios = {
        "admin": Usuario(id=1, nombre="Admin", email="a@t", password_hash="x", roles_json='["ADMIN"]', activo=True),
        "vendedor": Usuario(id=2, nombre="Vend", email="v@t", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True),
        "supervisor": Usuario(id=3, nombre="Sup", email="s@t", password_hash="x", roles_json='["SUPERVISOR_CIERRE"]', activo=True),
        "cobranzas": Usuario(id=4, nombre="Cob", email="c@t", password_hash="x", roles_json='["COBRANZAS"]', activo=True),
        "inactivo": Usuario(id=5, nombre="Baja", email="i@t", password_hash="x", roles_json='["ADMIN"]', activo=False),
    }
    db.add_all(usuarios.values())
    db.add_all([
        Aliado(id=1, codigo="AL-100", nombre="Organizador A", telefono="1", estado="activo", es_organizador=True),
        Aliado(id=2, codigo="AL-101", nombre="Vendedor de A", telefono="2", estado="activo", organizacion_codigo="AL-100"),
        Aliado(id=3, codigo="AL-200", nombre="Organizador B", telefono="3", estado="activo", es_organizador=True),
    ])
    db.add_all([Lead(id=10, nombre="Lead del vendedor", telefono="5491100000001", asesor_apertura_id=2),
                Lead(id=11, nombre="Lead de otro", telefono="5491100000002", asesor_apertura_id=3)])
    db.commit()
    app = FastAPI()
    for r in (auth, leads, cobranzas, control_agentes):
        app.include_router(r.router)
    app.include_router(reparto_meta.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)

    def crm(uid, **kw):
        return {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)}, **kw)}"}

    def socio(aid):
        return {"Authorization": f"Bearer {socios._crear_token_socio(aid)}"}
    roles = {
        "admin": crm(1), "vendedor": crm(2), "supervisor": crm(3), "cobranzas": crm(4),
        "inactivo": crm(5),
        "organizador": socio(1), "socio_vendedor": socio(2), "organizador_otra_org": socio(3),
        "sin_sesion": {}, "servicio_api_key": {"Authorization": f"Bearer {API_KEY}"},
    }
    yield c, roles, crm, socio


# ── Autenticación y clases de sesión ─────────────────────────────────────────

def test_token_de_socio_no_es_sesion_crm(m):
    c, roles, _, _ = m
    for rol in ("organizador", "socio_vendedor", "organizador_otra_org"):   # mismos ids que admin/vendedor/supervisor
        assert c.get("/api/usuarios/me", headers=roles[rol]).status_code == 401, rol


def test_token_crm_no_es_sesion_de_socio(m):
    c, roles, crm, _ = m
    from fastapi import Request
    token = auth.create_access_token({"sub": "1"})
    assert sesiones.validar(token, "socio", SECRET) is None
    assert sesiones.validar(token, "crm", SECRET)["aud"] == sesiones.AUD_CRM


def test_audiencia_y_clase_correctas_e_incorrectas(m):
    c, _, _, _ = m
    exp = {"exp": 9999999999}
    casos = {
        "aud ajena": {"sub": "1", "typ": "crm", "aud": "otra-app", **exp},
        "aud de socio con typ crm": {"sub": "1", "typ": "crm", "aud": sesiones.AUD_SOCIO, **exp},
        "typ desconocido sin aud": {"sub": "1", "typ": "admin", **exp},
        "socio legado": {"sub": "1", "typ": "socio", **exp},
        "sin exp": {"sub": "1", "typ": "crm", "aud": sesiones.AUD_CRM},
        "sub no numérico": {"sub": "admin", "typ": "crm", "aud": sesiones.AUD_CRM, **exp},
    }
    for nombre, claims in casos.items():
        tok = jwt.encode(claims, SECRET, algorithm="HS256")
        assert c.get("/api/usuarios/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401, nombre
    firmado_con_otra = jwt.encode({"sub": "1", "typ": "crm", "aud": sesiones.AUD_CRM, **exp}, "otra-clave", algorithm="HS256")
    assert c.get("/api/usuarios/me", headers={"Authorization": f"Bearer {firmado_con_otra}"}).status_code == 401


def test_token_crm_legado_sigue_valido_hasta_vencer(m):
    """Los tokens emitidos antes del contrato (sin aud ni typ) no cierran sesiones al desplegar."""
    c, _, _, _ = m
    legado = jwt.encode({"sub": "1", "exp": 9999999999}, SECRET, algorithm="HS256")
    assert c.get("/api/usuarios/me", headers={"Authorization": f"Bearer {legado}"}).json()["id"] == 1


def test_sesion_vencida_y_usuario_inactivo(m):
    c, roles, crm, _ = m
    assert c.get("/api/usuarios/me", headers=crm(1, expires_delta=timedelta(seconds=-5))).status_code == 401
    assert c.get("/api/usuarios/me", headers=roles["inactivo"]).status_code == 401


# ── Matriz rol × recurso ─────────────────────────────────────────────────────

MATRIZ = {
    # recurso: {rol: estado esperado}
    ("GET", "/api/reparto-meta"): {
        "admin": 200, "vendedor": 403, "supervisor": 403, "cobranzas": 403, "inactivo": 401,
        "organizador": 200, "socio_vendedor": 403, "organizador_otra_org": 200,
        "sin_sesion": 401, "servicio_api_key": 401},
    ("POST", "/api/reparto-meta/pendientes"): {   # acción global
        "admin": 200, "vendedor": 403, "organizador": 403, "socio_vendedor": 403,
        "sin_sesion": 401, "servicio_api_key": 401},
    ("GET", "/api/cobranzas/cartera"): {          # información financiera
        "admin": 200, "cobranzas": 200, "vendedor": 403, "supervisor": 403, "inactivo": 401,
        "organizador": 401, "socio_vendedor": 401, "sin_sesion": 401, "servicio_api_key": 401},
    ("GET", "/api/control-agentes/historial"): {
        "admin": 200, "vendedor": 403, "supervisor": 403, "cobranzas": 403,
        "organizador": 401, "socio_vendedor": 401, "sin_sesion": 401, "servicio_api_key": 401},
    ("POST", "/api/control-agentes/comando"): {   # órdenes a Máximo por canal confiable
        "vendedor": 403, "supervisor": 403, "cobranzas": 403,
        "organizador": 401, "socio_vendedor": 401, "sin_sesion": 401, "servicio_api_key": 401},
    ("GET", "/api/control-agentes/catalogo"): {
        "admin": 200, "vendedor": 403, "sin_sesion": 401},
}


@pytest.mark.parametrize("recurso", list(MATRIZ), ids=lambda r: f"{r[0]} {r[1]}")
def test_matriz(m, recurso):
    c, roles, _, _ = m
    metodo, ruta = recurso
    fallas = []
    for rol, esperado in MATRIZ[recurso].items():
        if metodo == "GET":
            r = c.get(ruta, headers=roles[rol])
        else:
            r = c.post(ruta, headers=roles[rol], json={"instruccion": "prueba"} if "comando" in ruta else {})
        if r.status_code != esperado:
            fallas.append(f"{rol}: {r.status_code} (esperado {esperado})")
    assert not fallas, fallas


def test_reparto_organizador_solo_ve_su_organizacion(m):
    c, roles, _, _ = m
    vistos = str(c.get("/api/reparto-meta", headers=roles["organizador"]).json())
    assert "AL-101" in vistos and "AL-200" not in vistos


def test_reparto_organizador_no_modifica_otra_organizacion(m):
    c, roles, _, _ = m
    r = c.patch("/api/reparto-meta/destinos/aliado:AL-200", headers=roles["organizador"], json={"habilitado": True})
    assert r.status_code == 403
    r = c.patch("/api/reparto-meta/destinos/aliado:AL-101", headers=roles["organizador_otra_org"], json={"habilitado": True})
    assert r.status_code == 403


def test_vendedor_solo_ve_sus_leads(m):
    c, roles, _, _ = m
    r = c.get("/api/leads", headers=roles["vendedor"])
    assert r.status_code == 200
    ids = {l["id"] for l in (r.json()["leads"] if isinstance(r.json(), dict) else r.json())}
    assert ids == {10}
    assert c.get("/api/leads", headers=roles["organizador"]).status_code == 401
    assert c.get("/api/leads", headers=roles["sin_sesion"]).status_code == 401
