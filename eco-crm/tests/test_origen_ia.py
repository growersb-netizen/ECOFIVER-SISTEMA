"""Clave propia de la IA (AGENTES_IA_API_KEY): autentica como servicio y siempre identifica a la IA."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from utils.api_keys import agentes_ia_key_valida, api_key_valida, multiagente_key_valida
from utils.origen import es_agente_ia, negar_a_agentes_ia


@pytest.fixture
def c(monkeypatch):
    monkeypatch.setenv("API_KEY", "general")
    monkeypatch.setenv("CRM_API_KEY", "inbox")
    monkeypatch.setenv("AGENTES_IA_API_KEY", "clave-ia")
    app = FastAPI()

    @app.get("/financiero", dependencies=[Depends(negar_a_agentes_ia)])
    def financiero():
        return {"ok": True}

    @app.get("/quien")
    def quien(request: __import__("fastapi").Request):
        return {"ia": es_agente_ia(request)}
    return TestClient(app)


def test_la_clave_ia_vale_como_clave_de_servicio_y_de_inbox(c):
    assert api_key_valida("clave-ia") and multiagente_key_valida("clave-ia") and agentes_ia_key_valida("clave-ia")
    assert not agentes_ia_key_valida("general")


def test_con_la_clave_ia_se_identifica_como_ia_aunque_omita_el_encabezado(c):
    assert c.get("/quien", headers={"Authorization": "Bearer clave-ia"}).json()["ia"] is True
    assert c.get("/quien", headers={"X-API-Key": "clave-ia"}).json()["ia"] is True
    assert c.get("/quien", headers={"Authorization": "Bearer general"}).json()["ia"] is False
    assert c.get("/financiero", headers={"Authorization": "Bearer clave-ia"}).status_code == 403
    r = c.get("/financiero", headers={"Authorization": "Bearer clave-ia", "X-Autorizacion-Humana": "canal:whatsapp_admin"})
    assert r.status_code == 200                                     # Máximo en el canal del propietario, como antes


def test_sin_configurar_no_cambia_nada(monkeypatch):
    monkeypatch.delenv("AGENTES_IA_API_KEY", raising=False)
    assert not agentes_ia_key_valida("") and not agentes_ia_key_valida(None)
