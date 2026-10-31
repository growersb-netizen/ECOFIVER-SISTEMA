"""Bajas de comunicaciones comerciales: registro persistente, filtros y reactivación."""
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
from database.models import Lead, Usuario
from routers import agentes
from routers.auth import create_access_token
from utils import exclusiones

KEY = "clave-agentes-test"
TEL = "5491135164644"
H = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    from routers import auth
    monkeypatch.setattr(auth, "SECRET_KEY", "secreto-de-prueba-bajas-" + "x" * 16)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    hace = datetime.utcnow() - timedelta(days=40)
    db.add_all([
        Lead(nombre="Ana", telefono=TEL, session_id=TEL, estado="NUEVO", created_at=hace, updated_at=hace),
        Lead(nombre="Beto", telefono="5491144445555", session_id="5491144445555", estado="NUEVO",
             created_at=hace, updated_at=hace),
        Usuario(nombre="Rodrigo", email="admin@test", password_hash="x", roles_json='["ADMIN"]', activo=True),
        Usuario(nombre="Agentes IA (sistema)", email="agentes-ia@ecofiver.local", password_hash="x",
                roles_json='["ADMIN"]', activo=True, es_agente_ia=True),
        Usuario(nombre="Vendedor", email="v@test", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(agentes.router)

    def _db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app), db
    db.close()


def _token(db, email):
    u = db.query(Usuario).filter_by(email=email).first()
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


def test_clave_de_telefono_ignora_formato():
    assert exclusiones.clave_telefono("+54 9 11 3516-4644") == exclusiones.clave_telefono("1135164644") \
        == exclusiones.clave_telefono(TEL) == "1135164644"
    assert exclusiones.clave_telefono("3f2b8c1e-9a4d") == ""          # UUID del widget: no es teléfono
    assert exclusiones.clave_telefono("") == ""


def test_registrar_baja_desde_la_sesion_y_es_idempotente(entorno):
    c, _ = entorno
    r = c.post("/api/contactos/baja", headers=H, json={"session_id": TEL, "canal": "whatsapp",
                                                        "texto": "No me escriban más"})
    assert r.json()["registrado"] and not r.json()["ya_existia"]
    r = c.post("/api/contactos/baja", headers=H, json={"session_id": TEL})
    assert r.json()["ya_existia"]
    assert c.get("/api/contactos/baja", headers=H, params={"telefono": "11 3516-4644"}).json()["excluido"]
    assert not c.get("/api/contactos/baja", headers=H, params={"telefono": "5491144445555"}).json()["excluido"]


def test_sin_telefono_no_registra(entorno):
    c, _ = entorno
    r = c.post("/api/contactos/baja", headers=H, json={"session_id": "3f2b8c1e-9a4d-4c6b-8e2f-1a2b3c4d5e6f"})
    assert r.json() == {"ok": True, "registrado": False, "motivo": "sin_telefono"}


def test_endpoints_de_baja_exigen_clave(entorno):
    c, _ = entorno
    assert c.post("/api/contactos/baja", json={"telefono": TEL}).status_code == 401
    assert c.get("/api/contactos/baja", params={"telefono": TEL}).status_code == 401


@pytest.mark.parametrize("ruta,params", [
    ("/api/leads/sin-respuesta", {"horas": 2}),
    ("/api/leads/frios-reactivar", {"dias_inactivo": 30}),
])
def test_listados_de_contacto_automatico_excluyen_bajas(entorno, ruta, params):
    c, _ = entorno
    antes = {l["telefono"] for l in c.get(ruta, headers=H, params=params).json()}
    assert TEL in antes
    c.post("/api/contactos/baja", headers=H, json={"telefono": TEL})
    despues = {l["telefono"] for l in c.get(ruta, headers=H, params=params).json()}
    assert TEL not in despues and "5491144445555" in despues


def test_nuevos_y_nutrir_excluyen_bajas(entorno):
    c, db = entorno
    c.post("/api/contactos/baja", headers=H, json={"telefono": TEL})
    ahora = datetime.utcnow()
    db.add_all([Lead(nombre="Ana otra vez", telefono="+54 9 11 3516-4644", estado="NUEVO",
                     created_at=ahora - timedelta(minutes=5)),
                Lead(nombre="Ana 24h", telefono=TEL, estado="NUEVO", created_at=ahora - timedelta(hours=25))])
    db.commit()
    nuevos = c.get("/api/leads/nuevos-sin-contactar", headers=H, params={"minutos": 30}).json()
    nutrir = c.get("/api/leads/para-nutrir", headers=H).json()
    assert not [l for l in nuevos + nutrir if l["nombre"].startswith("Ana")]


def test_volver_a_escribir_no_reactiva(entorno):
    c, _ = entorno
    c.post("/api/contactos/baja", headers=H, json={"session_id": TEL})
    # El contacto escribe de nuevo: el multiagente busca/crea el lead y guarda el mensaje
    c.post("/api/leads/agent", headers=H, json={"session_id": TEL, "canal_origen": "whatsapp"})
    c.post(f"/api/leads/by-session/{TEL}/messages", headers=H,
           json={"user_msg": "Hola, ¿cuánto sale la de 6?", "agent_reply": "...", "agent_name": "valentina"})
    lead = c.get(f"/api/leads/by-session/{TEL}", headers=H).json()
    assert lead["baja_comercial"] is True
    assert TEL not in {l["telefono"] for l in c.get("/api/leads/frios-reactivar", headers=H).json()}


def test_reactivar_solo_admin_humano_con_motivo(entorno):
    c, db = entorno
    c.post("/api/contactos/baja", headers=H, json={"telefono": TEL})
    url = "/api/contactos/baja/reactivar"
    cuerpo = {"telefono": TEL, "motivo": "El cliente pidió volver a recibir novedades"}
    assert c.post(url, headers=H, json=cuerpo).status_code == 401                       # API key de agentes
    assert c.post(url, headers=_token(db, "agentes-ia@ecofiver.local"), json=cuerpo).status_code == 403
    assert c.post(url, headers=_token(db, "v@test"), json=cuerpo).status_code == 403    # no admin
    assert c.post(url, headers=_token(db, "admin@test"), json={"telefono": TEL}).status_code == 400
    assert c.get("/api/contactos/baja", headers=H, params={"telefono": TEL}).json()["excluido"]
    r = c.post(url, headers=_token(db, "admin@test"), json=cuerpo)
    assert r.json()["reactivado"]
    assert not c.get("/api/contactos/baja", headers=H, params={"telefono": TEL}).json()["excluido"]
    # Un nuevo pedido vuelve a activarla
    assert not c.post("/api/contactos/baja", headers=H, json={"telefono": TEL}).json()["ya_existia"]
    assert c.get("/api/contactos/baja", headers=H, params={"telefono": TEL}).json()["excluido"]


def test_testimonio_no_se_envia_a_contactos_con_baja(entorno, monkeypatch):
    _, db = entorno
    from routers import logistica
    import utils.whatsapp as wa
    enviados = []
    monkeypatch.setattr(wa, "send_whatsapp_text", lambda db, to, msg: enviados.append(to) or True)
    exclusiones.registrar_baja(db, TEL)
    logistica._enviar_wa_testimonio(db, TEL, "Ana", "tok")
    logistica._enviar_wa_testimonio(db, "5491144445555", "Beto", "tok")
    assert enviados == ["5491144445555"]
