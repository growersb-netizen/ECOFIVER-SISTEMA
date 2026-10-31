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
from datetime import datetime, timedelta

from jose import jwt

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.database import Base, get_db
from database.models import (Aliado, Interaccion, Lead, Usuario, MetaPagina,
                             MetaLeadCampana, MetaLeadDestino, MetaLeadOrganizacion)
from routers import agentes, auth, leads, redes_sociales, socios, reparto_meta


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
                        contrato_firmado=True, password_hash="ficticio", organizacion_codigo="AL-010")
        claudia = Aliado(codigo="AL-010", nombre="Claudia", estado="activo", es_organizador=True,
                        es_admin_crm=True, contrato_firmado=True, password_hash="ficticio")
        foreign = Aliado(codigo="AL-020", nombre="Otra organización", estado="activo", es_organizador=True,
                        contrato_firmado=True, password_hash="ficticio")
        foreign_member = Aliado(codigo="AL-OTHER", nombre="Otro vendedor", estado="activo",
                               organizacion_codigo="AL-020", contrato_firmado=True, password_hash="ficticio")
        admin = Usuario(nombre="Admin", email="admin@test.invalid", activo=True,
                        password_hash="ficticio", roles_json='["ADMIN"]')
        db.add_all([advisor, partner, claudia, foreign, foreign_member, admin, MetaPagina(page_id="634872006383162", nombre="Página prueba", activa=True, page_token="token-ficticio-meta")])
        db.flush()
        db.add(MetaLeadCampana(form_id="1122869520123560", page_id="634872006383162",
                              nombre="Plan 18 viviendas", producto="MODULO", activa=True))
        db.add(MetaLeadCampana(form_id="1122869520123561", page_id="634872006383162",
                              nombre="Piscinas contado", producto="PISCINA", activa=True))
        db.add_all([
            MetaLeadDestino(clave=f"asesor:{advisor.id}", habilitado=True, modulos=True, piscinas=False),
            MetaLeadDestino(clave="aliado:AL-TEST", habilitado=True, modulos=True, piscinas=False),
            MetaLeadDestino(clave="aliado:AL-OTHER", habilitado=False, modulos=False, piscinas=False),
            MetaLeadOrganizacion(form_id="1122869520123560", organizacion_codigo="AL-010", habilitada=True),
            MetaLeadOrganizacion(form_id="1122869520123561", organizacion_codigo="AL-010", habilitada=False),
        ])
        db.commit()
        advisor_id, partner_id = advisor.id, partner.id
        claudia_id, admin_id = claudia.id, admin.id

    monkeypatch.setattr(auth, "SECRET_KEY", "jwt-test-secreto-reparto-local")

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
    for router in (agentes.router, redes_sociales.router, leads.router, socios.router, reparto_meta.router):
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
            assert event in ("1001", "1002", "1003", "1004")
            return httpx.Response(200, json={
                "field_data": [
                    {"name": "full_name", "values": [f"Prueba {event}"]},
                    {"name": "phone_number", "values": [f"549110000{event}"]},
                    {"name": "email", "values": [f"{event}@test.invalid"]},
                    {"name": "¿ De que provincia y localidad sos ?", "values": ["Moreno"]},
                    {"name": "plan", "values": ["18 pasos"]},
                ], "form_id": "1122869520123561" if event == "1004" else "1122869520123560", "ad_id": "ad-test", "ad_name": "Plan 18 pasos piscina",
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
                assert all(lead.producto_interes == "MODULO" for lead in all_leads)
                assert all("18 pasos" in lead.notas and "1122869520123560" in lead.notas for lead in all_leads)
                initial_history_count = db.query(Interaccion).count()
                assert initial_history_count >= 2
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
                assert db.query(Interaccion).count() == initial_history_count + 2
                partner_saved = db.get(Lead, partner_lead_id)
                assert partner_saved.estado == "CONTACTADO"
                assert partner_saved.notas == "Gestionado por aliado"
                assert partner_saved.proximo_seguimiento is not None
                assert db.get(Lead, advisor_lead_id).estado == "CONTACTADO"
                assert db.query(Interaccion).filter(Interaccion.asesor_id == advisor_id,
                                                    Interaccion.notas == "Gestionado por asesor").count() == 1
                assert db.query(Interaccion).filter(Interaccion.notas.contains("Gestionado por aliado")).count() == 1

            def login_claudia():
                client.cookies.clear()
                token = jwt.encode({"sub": str(claudia_id), "typ": "socio",
                                    "exp": datetime.utcnow() + timedelta(hours=1)}, auth.SECRET_KEY, algorithm="HS256")
                client.cookies.set("socio_token", token)

            def login_admin():
                client.cookies.clear()
                token = auth.create_access_token({"sub": str(admin_id)})
                client.cookies.set("access_token", token)

            login_claudia()
            # Claudia, aun es_admin_crm, sólo administra su propia organización.
            own = await client.patch("/api/reparto-meta/destinos/aliado:AL-TEST", json={"habilitado": False})
            assert own.status_code == 200, own.text
            foreign = await client.patch("/api/reparto-meta/destinos/aliado:AL-OTHER", json={"habilitado": True})
            assert foreign.status_code == 403
            foreign_gate = await client.patch("/api/reparto-meta/organizaciones/AL-020/campanas/1122869520123560",
                                                json={"habilitada": True})
            assert foreign_gate.status_code == 403
            login_admin()
            paused = await client.patch(f"/api/reparto-meta/destinos/asesor:{advisor_id}", json={"habilitado": False})
            assert paused.status_code == 200, paused.text
            admin_foreign = await client.patch("/api/reparto-meta/organizaciones/AL-020/campanas/1122869520123560",
                                                json={"habilitada": True})
            assert admin_foreign.status_code == 200, admin_foreign.text
            await callback("1003")
            with sessions() as db:
                pending = db.query(Lead).filter_by(session_id="meta:1003").one()
                pending_id = pending.id
                assert pending.asesor_apertura_id is None and pending.aliado_codigo is None

            login_claudia()
            enabled = await client.patch("/api/reparto-meta/destinos/aliado:AL-TEST", json={"habilitado": True, "modulos": True})
            assert enabled.status_code == 200, enabled.text
            denied_drain = await client.post("/api/reparto-meta/pendientes", json={"form_id": "1122869520123560"})
            assert denied_drain.status_code == 403
            login_admin()
            distributed = await client.post("/api/reparto-meta/pendientes", json={"form_id": "1122869520123560"})
            assert distributed.status_code == 200, distributed.text
            assert enabled.json().get("asignados", 0) + distributed.json()["asignados"] == 1
            with sessions() as db:
                assert db.get(Lead, pending_id).aliado_codigo == "AL-TEST"

            # El producto piscina exige su toggle Y la habilitación de campaña de la org.
            login_claudia()
            enabled = await client.patch("/api/reparto-meta/destinos/aliado:AL-TEST", json={"piscinas": True})
            assert enabled.status_code == 200
            await callback("1004")
            with sessions() as db:
                pool_pending = db.query(Lead).filter_by(session_id="meta:1004").one()
                pool_id = pool_pending.id
                assert pool_pending.producto_interes == "PISCINA"
                assert pool_pending.asesor_apertura_id is None and pool_pending.aliado_codigo is None
            gate = await client.patch("/api/reparto-meta/organizaciones/AL-010/campanas/1122869520123561",
                                      json={"habilitada": True})
            assert gate.status_code == 200, gate.text
            login_admin()
            distributed = await client.post("/api/reparto-meta/pendientes", json={"form_id": "1122869520123561"})
            assert distributed.status_code == 200, distributed.text
            assert gate.json().get("asignados", 0) + distributed.json()["asignados"] == 1
            with sessions() as db:
                assert db.get(Lead, pool_id).aliado_codigo == "AL-TEST"
                assert db.get(Lead, partner_lead_id).estado == "CONTACTADO"
                assert db.get(Lead, advisor_lead_id).asesor_apertura_id == advisor_id
            assert contact.await_count == 4

    try:
        asyncio.run(scenario())
        assert sum(host == "multiagente.test" for host, _, _ in seen) == 6
        assert sum(host == "graph.facebook.com" for host, _, _ in seen) == 6
        assert sum(path == "/api/leads/meta" for _, _, path in seen) == 6
        assert sum(path.startswith("/api/leads/meta-datos/") for _, _, path in seen) == 6
    finally:
        engine.dispose()
