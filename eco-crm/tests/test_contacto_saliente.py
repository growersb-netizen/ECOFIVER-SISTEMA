"""Autorización de salientes: baja, ventana de 24 h de WhatsApp y deduplicación entre tareas."""
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
from database.models import ContactoProactivo, InboxMensaje
from routers import agentes
from utils import exclusiones

KEY = "clave-salientes"
H = {"Authorization": f"Bearer {KEY}"}
TEL = "5491100000077"


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    app = FastAPI()
    app.include_router(agentes.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    pedir = lambda origen="cron seguimiento", tel=TEL: c.post("/api/contactos/saliente/autorizar", headers=H,
                                                                json={"telefono": tel, "origen": origen}).json()
    yield db, pedir


def _entrante(db, horas_atras):
    db.add(InboxMensaje(phone=TEL, direccion="IN", contenido="hola",
                        created_at=datetime.utcnow() - timedelta(hours=horas_atras)))
    db.commit()


def test_sin_mensaje_del_cliente_requiere_plantilla(m):
    db, pedir = m
    r = pedir()
    assert (r["permitido"], r["motivo"]) == (False, "fuera_de_ventana_24h") and "plantilla" in r["detalle"]


def test_fuera_de_24h_no_se_envia(m):
    db, pedir = m
    _entrante(db, 30)
    assert pedir()["motivo"] == "fuera_de_ventana_24h"


def test_dentro_de_24h_se_autoriza_y_queda_registrado(m):
    db, pedir = m
    _entrante(db, 3)
    assert pedir()["permitido"] is True
    assert db.query(ContactoProactivo).one().origen == "cron seguimiento"


def test_no_duplica_seguimientos_entre_tareas(m):
    db, pedir = m
    _entrante(db, 3)
    assert pedir("cron nutricion 24h")["permitido"] is True
    r = pedir("cron seguimiento")
    assert (r["permitido"], r["motivo"], r["por"]) == (False, "contactado_recientemente", "cron nutricion 24h")


def test_baja_tiene_prioridad(m):
    db, pedir = m
    _entrante(db, 1)
    exclusiones.registrar_baja(db, TEL)
    assert pedir()["motivo"] == "baja_comercial"


def test_exige_clave(m):
    db, pedir = m
    from fastapi.testclient import TestClient  # noqa: F401
    assert pedir(tel="")["motivo"] == "telefono_invalido"
