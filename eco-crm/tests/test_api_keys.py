"""Tests de utils/api_keys.py — validación centralizada y rotación sin cortes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from utils.api_keys import api_key_valida, multiagente_key_valida


@pytest.fixture(autouse=True)
def _limpiar(monkeypatch):
    for k in ("API_KEY", "API_KEY_ANTERIOR", "CRM_API_KEY", "CRM_API_KEY_ANTERIOR",
              "AGENTES_IA_API_KEY", "AGENTES_IA_API_KEY_ANTERIOR"):
        monkeypatch.delenv(k, raising=False)


def test_sin_clave_configurada_falla_cerrado():
    assert not api_key_valida("")
    assert not api_key_valida(None)
    assert not api_key_valida("cualquiera")


def test_clave_vigente(monkeypatch):
    monkeypatch.setenv("API_KEY", "nueva")
    assert api_key_valida("nueva")
    assert api_key_valida(" nueva ")
    assert not api_key_valida("otra")
    assert not api_key_valida("")


def test_rotacion_acepta_ambas_y_luego_solo_la_nueva(monkeypatch):
    monkeypatch.setenv("API_KEY", "nueva")
    monkeypatch.setenv("API_KEY_ANTERIOR", "vieja")
    assert api_key_valida("nueva") and api_key_valida("vieja")
    monkeypatch.delenv("API_KEY_ANTERIOR")
    assert api_key_valida("nueva") and not api_key_valida("vieja")


def test_no_acepta_tipos_raros(monkeypatch):
    monkeypatch.setenv("API_KEY", "k")
    assert not api_key_valida(["k"])
    assert not api_key_valida(123)


def test_clave_del_multiagente_es_independiente(monkeypatch):
    monkeypatch.setenv("API_KEY", "general")
    monkeypatch.setenv("CRM_API_KEY", "inbox")
    assert multiagente_key_valida("inbox")
    assert not multiagente_key_valida("general")
    monkeypatch.setenv("CRM_API_KEY_ANTERIOR", "inbox-vieja")
    assert multiagente_key_valida("inbox-vieja")


def test_endpoints_que_antes_fallaban_abiertos(monkeypatch):
    """marketing/meta_ads comparaban con != : con API_KEY vacía y sin header pasaban."""
    assert not api_key_valida("")  # equivalente al caso "" != "" → False → acceso


def test_zapia_require_api_key(monkeypatch):
    from fastapi import HTTPException
    from routers.zapia import require_api_key
    with pytest.raises(HTTPException):
        require_api_key(None)
    monkeypatch.setenv("API_KEY", "k1")
    assert require_api_key("k1") is True
    with pytest.raises(HTTPException):
        require_api_key("k2")
