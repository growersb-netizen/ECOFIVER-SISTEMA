"""Recorrido HTTP completo local: Meta firmado → servicios → DB → gestión.

No usa red: todo destino HTTP se limita a ASGI o al simulador de Meta Graph.
El cliente HTTP del CRM, los endpoints y la persistencia son los reales.
"""
import asyncio
import hashlib
import hmac
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.database import Base, get_db
from database.models import Aliado, Interaccion, Lead, Usuario, MetaPagina
from routers import agentes, leads, redes_sociales, socios


def test_formulario_a_asignacion_y_gestion_por_responsable(tmp_path, monkeypatch):
    ma_root = Path(__file__).resolve().parents[2] / "eco-multiagente"
    monkeypatch.syspath_prepend(str(ma_root))
    crm_client = importlib.import_module("tools.crm_client")
    spec = importlib.util.spec_from_file_location("meta_e2e_under_test", ma_root / "channels/meta_leads.py")
    meta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(meta)
    secret = "secret-de-prueba-local"
    api_key = "clave-api-de-prueba-local"
    monkeypatch.setenv("META_APP_SECRET", secret)
    monkeypatch.setenv("API_KEY", api_key)
    monkeypatch.setenv("MULTIAGENTE_WEBHOOK_URL", "http://multiagente.test/webhook/meta")
    monkeypatch.setattr(meta, "META_APP_SECRET", secret)
    monkeypatch.setattr(meta, "META_PAGE_TOKEN", "token-multiagente-sin-acceso")
    monkeypatch.setattr(crm_client, "CRM_BASE_URL", "http://crm.test")
    monkeypatch.setattr(crm_client, "HEADERS", {"Authorization": f"Bearer {api_key}"})
    contact = AsyncMock()
    monkeypatch.setattr(meta, "_contactar_lead_wa", contact)

    engine = create_engine(f"sqlite:///{tmp_path / 'integration.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        advisor = Usuario(nombre="Asesor Prueba", email="asesor@test.invalid", activo=True,
                          password_hash="ficticio", roles_json='["ASESOR_APERTURA"]')
        partner = Aliado(codigo="AL-TEST", nombre="Aliado Prueba", estado="activo",
                        contrato_firmado=True, password_hash="ficticio")
        db.add_all([advisor, partner, MetaPagina(page_id="634872006383162", nombre="Página prueba", activa=True, page_token="token-ficticio-meta")])
        db.commit()
        advisor_id, partner_id = advisor.id, partner.id

    def dependency_db():
        with sessions() as db:
            yield db

    def signed_in_advisor():
        with sessions() as db:
            return db.get(Usuario, advisor_id)

    def signed_in_partner():
        with sessions() as db:
            return db.get(Aliado, partner_id)

    crm_app = FastAPI()
    for router in (agentes.router, redes_sociales.router, leads.router, socios.router):
        crm_app.include_router(router)
    crm_app.dependency_overrides[get_db] = dependency_db
    crm_app.dependency_overrides[leads.require_auth] = signed_in_advisor
    crm_app.dependency_overrides[socios.require_socio] = signed_in_partner
    monkeypatch.setattr(redes_sociales, "SessionLocal", sessions)
    ma_app = FastAPI()
    ma_app.include_router(meta.router)

    seen = []

    async def route(request):
        seen.append((request.url.host, request.method, request.url.path))
        if request.url.host == "crm.test":
            return await httpx.ASGITransport(app=crm_app).handle_async_request(request)
        if request.url.host == "multiagente.test":
            return await httpx.ASGITransport(app=ma_app).handle_async_request(request)
        if request.url.host == "graph.facebook.com":
            assert request.headers["Authorization"] == "Bearer token-ficticio-meta"
            assert "access_token" not in request.url.params
            event = request.url.path.rsplit("/", 1)[-1]
            assert event in ("1001", "1002")
            return httpx.Response(200, json={
                "field_data": [
                    {"name": "full_name", "values": [f"Prueba {event}"]},
                    {"name": "phone_number", "values": ["5491100000001" if event == "1001" else "5491100000002"]},
                    {"name": "email", "values": [f"{event}@test.invalid"]},
                    {"name": "¿ De que provincia y localidad sos ?", "values": ["Moreno"]},
                    {"name": "plan", "values": ["18 pasos"]},
                ], "form_id": "form-plan-18", "ad_id": "ad-test", "ad_name": "Plan 18 pasos piscina",
            })
        raise AssertionError(f"Destino HTTP no simulado: {request.url.host}")

    transport = httpx.MockTransport(route)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    async def scenario():
        async with original_client(transport=transport, base_url="http://crm.test") as client:
            async def callback(event):
                raw = json.dumps({"object": "page", "entry": [{"id": "634872006383162", "changes": [{
                    "field": "leadgen", "value": {"leadgen_id": event},
                }]}]}, ensure_ascii=False).encode()
                signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
                response = await client.post("/api/redes/facebook/webhook", content=raw,
                                             headers={"X-Hub-Signature-256": signature})
                assert response.status_code == 200, response.text

            await callback("1001")
            await callback("1002")
            with sessions() as db:
                all_leads = db.query(Lead).order_by(Lead.id).all()
                assert len(all_leads) == 2
                partner_lead = next(lead for lead in all_leads if lead.aliado_codigo == "AL-TEST")
                advisor_lead = next(lead for lead in all_leads if lead.asesor_apertura_id == advisor_id)
                partner_lead_id, advisor_lead_id = partner_lead.id, advisor_lead.id
                assert all(lead.origen == "META_ADS" for lead in all_leads)
                assert all(lead.localidad == "Moreno" for lead in all_leads)
                assert all("18 pasos" in lead.notas and "form-plan-18" in lead.notas for lead in all_leads)
                assert db.query(Interaccion).count() == 2
            assert contact.await_count == 2

            # Los dos responsables ven el lead a través de su endpoint real.
            partner_queue = await client.get("/api/socio/leads")
            assert partner_queue.status_code == 200
            assert [lead["id"] for lead in partner_queue.json()["leads"]] == [partner_lead_id]
            advisor_queue = await client.get("/api/leads/cola-trabajo")
            assert advisor_queue.status_code == 200
            assert [lead["id"] for lead in advisor_queue.json()["items"]] == [advisor_lead_id]

            # Cada panel registra gestión sin habilitar acceso al lead ajeno.
            gestion = await client.put(f"/api/socio/leads/{partner_lead_id}", json={
                "estado": "CONTACTADO", "notas": "Gestionado por aliado", "etiqueta_color": "verde",
                "proximo_seguimiento": "2026-11-01T12:00:00-03:00",
            })
            assert gestion.status_code == 200, gestion.text
            gestion = await client.post(f"/api/leads/{advisor_lead_id}/registrar-contacto", json={
                "resultado": "INTERESADO", "notas": "Gestionado por asesor",
            })
            assert gestion.status_code == 200, gestion.text
            rejected = await client.put(f"/api/socio/leads/{advisor_lead_id}", json={"estado": "INACTIVO"})
            assert rejected.status_code == 404
            rejected = await client.post(f"/api/leads/{partner_lead_id}/registrar-contacto", json={
                "resultado": "NO_INTERESA",
            })
            assert rejected.status_code == 403

            # Reenviar ambos callbacks conserva gestión y no repite contactos.
            await callback("1001")
            await callback("1002")
            assert contact.await_count == 2
            with sessions() as db:
                assert db.query(Lead).count() == 2
                assert db.query(Interaccion).count() == 4
                partner_saved = db.get(Lead, partner_lead_id)
                assert partner_saved.estado == "CONTACTADO"
                assert partner_saved.notas == "Gestionado por aliado"
                assert partner_saved.proximo_seguimiento is not None
                assert db.get(Lead, advisor_lead_id).estado == "CONTACTADO"
                assert db.query(Interaccion).filter(Interaccion.asesor_id == advisor_id,
                                                    Interaccion.notas == "Gestionado por asesor").count() == 1
                assert db.query(Interaccion).filter(Interaccion.notas.contains("Gestionado por aliado")).count() == 1

    try:
        asyncio.run(scenario())
        assert sum(host == "multiagente.test" for host, _, _ in seen) == 4
        assert sum(host == "graph.facebook.com" for host, _, _ in seen) == 4
        assert sum(path == "/api/leads/meta" for _, _, path in seen) == 4
        assert sum(path.startswith("/api/leads/meta-datos/") for _, _, path in seen) == 4
    finally:
        engine.dispose()
