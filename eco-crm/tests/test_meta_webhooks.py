"""Callbacks firmados y ACK tras persistencia, sin llamadas reales."""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routers import redes_sociales as redes

spec = importlib.util.spec_from_file_location(
    "meta_webhook_under_test",
    Path(__file__).resolve().parents[2] / "eco-multiagente/channels/meta_leads.py",
)
meta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meta)

SECRET = "webhook-test-secret"
BODY = {"object": "page", "entry": [{"id": "page", "changes": [
    {"field": "leadgen", "value": {"leadgen_id": "lead-123"}},
]}]}
RAW = json.dumps(BODY, ensure_ascii=False, indent=2).encode()
SIGNATURE = "sha256=" + hmac.new(SECRET.encode(), RAW, hashlib.sha256).hexdigest()


@pytest.fixture
def crm_client(monkeypatch):
    monkeypatch.setattr(redes, "get_config_value", lambda *args: SECRET)
    monkeypatch.setattr(redes, "SessionLocal", MagicMock())
    monkeypatch.setattr(redes, "_procesar_evento_fb", AsyncMock())
    app = FastAPI()
    app.include_router(redes.router)
    app.dependency_overrides[redes.get_db] = lambda: None
    return TestClient(app)


def test_crm_preserva_cuerpo_y_firma(crm_client, monkeypatch):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "ok"})
    original = httpx.AsyncClient
    monkeypatch.setattr(redes.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(transport)))
    response = crm_client.post("/api/redes/facebook/webhook", content=RAW,
                               headers={"X-Hub-Signature-256": SIGNATURE})
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].content == RAW
    assert calls[0].headers["X-Hub-Signature-256"] == SIGNATURE
    assert calls[0].headers["X-Ecofiver-Lead-Only"] == "1"


def test_crm_retorna_error_si_multiagente_no_confirma(crm_client, monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(redes.httpx, "AsyncClient", lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))))
    response = crm_client.post("/api/redes/facebook/webhook", content=RAW,
                               headers={"X-Hub-Signature-256": SIGNATURE})
    assert response.status_code == 503
    redes._procesar_evento_fb.assert_not_awaited()


def test_crm_rechaza_firma_invalida_antes_de_actuar(crm_client):
    response = crm_client.post("/api/redes/facebook/webhook", content=RAW,
                               headers={"X-Hub-Signature-256": "sha256=incorrecta"})
    assert response.status_code == 403
    redes._procesar_evento_fb.assert_not_awaited()


@pytest.fixture
def ma_client(monkeypatch):
    monkeypatch.setattr(meta, "META_APP_SECRET", SECRET)
    app = FastAPI()
    app.include_router(meta.router)
    return TestClient(app)


def test_multiagente_espera_confirmacion_crm(ma_client, monkeypatch):
    process = AsyncMock(side_effect=RuntimeError("CRM no disponible"))
    monkeypatch.setattr(meta, "_procesar_lead_ads", process)
    response = ma_client.post("/webhook/meta", content=RAW,
                              headers={"X-Hub-Signature-256": SIGNATURE})
    assert response.status_code == 503
    process.assert_awaited_once_with("lead-123", "page")


def test_multiagente_no_recontacta_en_reintento(ma_client, monkeypatch):
    process = AsyncMock(return_value=({"telefono": "549111"}, {"id": 1, "created": False}))
    contact = AsyncMock()
    monkeypatch.setattr(meta, "_procesar_lead_ads", process)
    monkeypatch.setattr(meta, "_contactar_lead_seguro", contact)
    response = ma_client.post("/webhook/meta", content=RAW,
                              headers={"X-Hub-Signature-256": SIGNATURE})
    assert response.status_code == 200
    process.assert_awaited_once()
    contact.assert_not_awaited()


def test_fallo_contacto_no_pierde_registro(ma_client, monkeypatch):
    monkeypatch.setattr(meta, "_procesar_lead_ads", AsyncMock(return_value=(
        {"telefono": "549111"}, {"id": 1, "created": True})))
    contact = AsyncMock(side_effect=RuntimeError("WA no disponible"))
    monkeypatch.setattr(meta, "_contactar_lead_wa", contact)
    response = ma_client.post("/webhook/meta", content=RAW,
                              headers={"X-Hub-Signature-256": SIGNATURE})
    assert response.status_code == 200
    contact.assert_awaited_once()


def test_registra_sin_telefono_sin_importar_ia(monkeypatch):
    register = AsyncMock(return_value={"id": 1, "created": True})
    monkeypatch.setitem(sys.modules, "tools", SimpleNamespace(
        crm_client=SimpleNamespace(registrar_lead_meta=register)))
    payload, saved = asyncio.run(meta._registrar_lead_crm({"meta_lead_id": "test"}))
    assert saved["id"] == 1
    assert payload["telefono"] == ""
    register.assert_awaited_once()


def test_preguntas_plan18_y_producto_desconocido_se_conservan(monkeypatch):
    retrieve = AsyncMock(return_value={"form_id": "1122869520123560", "field_data": [
        {"name": "FULL_NAME", "values": ["Prueba Plan18"]},
        {"name": "PHONE", "values": ["5491100000000"]},
        {"name": "¿ De que provincia y localidad sos ?", "values": ["Casa Grande, Córdoba"]},
        {"name": "¿ Contas con terreno ?", "values": ["Sí"]},
        {"name": "¿ Cuántas personas componen el grupo familiar ?", "values": ["4"]},
    ]})
    monkeypatch.setitem(sys.modules, "tools", SimpleNamespace(
        crm_client=SimpleNamespace(obtener_datos_lead_meta=retrieve)))
    parsed = asyncio.run(meta._obtener_datos_lead("123", "634872006383162"))
    assert parsed["nombre"] == "Prueba Plan18"
    assert parsed["telefono"] == "5491100000000"
    assert parsed["ciudad"] == "Casa Grande, Córdoba"
    assert parsed["producto_interes"] == "sin_definir"
    assert len(parsed["field_data"]) == 5
    retrieve.assert_awaited_once_with("123", "634872006383162")


def test_multiagente_rechaza_firma_invalida(ma_client):
    response = ma_client.post("/webhook/meta", content=RAW,
                              headers={"X-Hub-Signature-256": "sha256=incorrecta"})
    assert response.status_code == 403


def test_multiagente_falla_cerrado_sin_secret(ma_client, monkeypatch):
    monkeypatch.setattr(meta, "META_APP_SECRET", "")
    response = ma_client.post("/webhook/meta", content=RAW)
    assert response.status_code == 503


def test_reenvio_no_duplica_mensajes_sociales(ma_client, monkeypatch):
    body = json.loads(RAW)
    body["entry"][0]["messaging"] = [{"message": {"text": "Hola"}}]
    raw = json.dumps(body).encode()
    signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    monkeypatch.setattr(meta, "_procesar_lead_ads", AsyncMock(return_value=(
        {}, {"id": 1, "created": False})))
    dm = AsyncMock()
    monkeypatch.setattr(meta, "_procesar_messenger_dm", dm)
    response = ma_client.post("/webhook/meta", content=raw,
                              headers={"X-Hub-Signature-256": signature,
                                       "X-Ecofiver-Lead-Only": "1"})
    assert response.status_code == 200
    dm.assert_not_awaited()
