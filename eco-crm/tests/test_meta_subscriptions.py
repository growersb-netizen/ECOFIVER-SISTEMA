"""El alta/reconexión de páginas conserva eventos e incluye Lead Ads."""
import os
import sys
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import Base, get_db
from database.models import MetaPagina, Usuario
from routers import redes_sociales as redes


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ML_AUDIT_TOKEN", "audit-only-test")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(MetaPagina(page_id="page-test", nombre="Página de prueba", page_token="page-token-test"))
        db.commit()
        config = {"meta_app_id": "test-app", "meta_app_secret": "test-secret",
                  "meta_page_access_token": "global-token-test", "crm_base_url": "https://crm.test"}
        monkeypatch.setattr(redes, "get_config_value", lambda key, db: config.get(key))
        monkeypatch.setattr(redes, "encrypt_value", lambda value: "encrypted-test")
        app = FastAPI()
        app.include_router(redes.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[redes.require_auth] = lambda: Usuario(id=1, roles_json='["ADMIN"]')
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def test_oauth_pide_recuperacion_de_leads_sin_perder_permisos(api):
    response = api[0].get("/api/redes/facebook/oauth-url")
    assert response.status_code == 200
    scopes = set(parse_qs(urlsplit(response.json()["url"]).query)["scope"][0].split(","))
    assert {"leads_retrieval", "pages_manage_metadata", "pages_messaging", "pages_read_engagement",
            "pages_show_list", "pages_manage_posts", "pages_read_user_content",
            "pages_manage_engagement", "business_management"} <= scopes


@pytest.mark.parametrize("bulk", [False, True])
def test_suscripcion_y_fallback_preservan_eventos_y_leadgen(api, monkeypatch, bulk):
    calls = []
    def route(request):
        assert request.url.path.endswith("/page-test/subscribed_apps")
        fields = set(request.url.params["subscribed_fields"].split(","))
        assert {"feed", "messages", "message_reactions", "leadgen"} <= fields
        calls.append(request)
        if bulk and len(calls) == 1:
            return httpx.Response(400, json={"error": {"code": 200}})
        return httpx.Response(200, json={"success": True})
    original = httpx.AsyncClient
    monkeypatch.setattr(redes.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(route)))
    path = "/api/redes/admin/subscribe-all?t=audit-only-test" if bulk else "/api/redes/paginas/page-test/subscribe-webhook"
    response = api[0].post(path)
    assert response.status_code == 200 and response.json()["ok"]
    assert len(calls) == (2 if bulk else 1)
    assert api[1].query(MetaPagina).first().webhook_subscribed


def test_token_de_sistema_tambien_pide_leads_retrieval(api, monkeypatch):
    calls = []
    def route(request):
        calls.append(request)
        if request.url.path.endswith("/system_user_access_tokens"):
            assert "leads_retrieval" in request.url.params["scope"].split(",")
            return httpx.Response(200, json={"access_token": "system-test"})
        if request.url.path.endswith("/me/accounts"):
            return httpx.Response(200, json={"data": [{"id": "page-test", "access_token": "page-test"}]})
        assert request.url.path.endswith("/page-test/subscribed_apps")
        assert set(request.url.params["subscribed_fields"].split(",")) == {"feed", "messages", "message_reactions", "leadgen"}
        return httpx.Response(200, json={"success": True})
    original = httpx.AsyncClient
    monkeypatch.setattr(redes.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(route)))
    response = api[0].post("/api/redes/admin/subscribe-via-system-token?t=audit-only-test",
                           json={"user_token": "human-test"})
    assert response.status_code == 200 and response.json()["ok"]
    assert len(calls) == 3
