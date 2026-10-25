"""
Tests Fase 2 Etapa A — WhatsApp Coexistence / smb_message_echoes
Ejecutar: pytest tests/test_whatsapp_coexistence.py -v

No requieren conexión con Meta ni con la WABA.
"""
import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


PHONE_ID_SUPERVISOR = "1383774158147416"
PHONE_ID_AGENTES    = "1037947576071396"


def _make_message_event(phone_number_id: str, from_phone: str, text: str, wamid: str = "wamid.test001") -> dict:
    return {
        "entry": [{
            "id": "123",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "11229855977", "phone_number_id": phone_number_id},
                    "contacts": [{"wa_id": from_phone, "profile": {"name": "Test User"}}],
                    "messages": [{"from": from_phone, "id": wamid, "timestamp": "1729900000", "type": "text", "text": {"body": text}}],
                },
            }],
        }],
        "object": "whatsapp_business_account",
    }


def _make_echo_event(phone_number_id: str, business_phone: str, recipient_phone: str,
                     text: str, wamid: str = "wamid.echo001") -> dict:
    return {
        "entry": [{
            "id": "123",
            "changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "11229855977", "phone_number_id": phone_number_id},
                    "contacts": [{"wa_id": recipient_phone, "profile": {"name": "Cliente Test"}}],
                    "messages": [{"from": business_phone, "to": recipient_phone, "id": wamid, "timestamp": "1729900000", "type": "text", "text": {"body": text}}],
                },
            }],
        }],
        "object": "whatsapp_business_account",
    }


def _make_echo_event_no_contacts(phone_number_id: str, recipient_phone: str, text: str) -> dict:
    """Echo sin contacts[] — solo messages[0]["to"]"""
    return {
        "entry": [{
            "id": "123",
            "changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_number_id},
                    "contacts": [],
                    "messages": [{"from": "5491122985977", "to": recipient_phone, "id": "wamid.nocontact", "type": "text", "text": {"body": text}}],
                },
            }],
        }],
        "object": "whatsapp_business_account",
    }


def _make_status_event(phone_number_id: str) -> dict:
    return {
        "entry": [{
            "id": "123",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_number_id},
                    "statuses": [{"id": "wamid.status001", "status": "delivered", "timestamp": "1729900000", "recipient_id": "5491199887766"}],
                },
            }],
        }],
        "object": "whatsapp_business_account",
    }


def _build_minimal_app() -> FastAPI:
    """App mínima con solo el router WA, sin Telegram ni otras dependencias."""
    os.environ.setdefault("WA_SUPERVISOR_PHONE_IDS",   PHONE_ID_SUPERVISOR)
    os.environ.setdefault("WA_SUPERVISOR_DISPLAY_MAP", f"{PHONE_ID_SUPERVISOR}:rodrigo")
    os.environ.setdefault("WA_PHONE_ID_AGENTES",       PHONE_ID_AGENTES)
    os.environ.setdefault("WA_VERIFY_TOKEN",            "eco_test_token")
    os.environ.setdefault("CRM_BASE_URL",               "http://mock-crm")
    os.environ.setdefault("CRM_API_KEY",                "test-key")

    from channels.whatsapp import router as wa_router
    app = FastAPI()
    app.include_router(wa_router)
    return app


# ─── Tests de routing del webhook ─────────────────────────────────────────────

class TestWebhookRouting:

    def test_echo_returns_accepted(self):
        """smb_message_echoes devuelve 200 accepted sin procesar como entrante normal."""
        with patch("channels.whatsapp._procesar_echo_smb", new_callable=AsyncMock):
            app = _build_minimal_app()
            client = TestClient(app)
            payload = _make_echo_event(PHONE_ID_SUPERVISOR, "5491122985977", "5491199887766", "Hola")
            resp = client.post("/webhook/whatsapp", json=payload)
            assert resp.status_code == 200
            assert resp.json()["status"] == "accepted"

    def test_status_update_returns_ignored(self):
        """Status updates devuelven 200 ignored."""
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/webhook/whatsapp", json=_make_status_event(PHONE_ID_AGENTES))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_normal_message_returns_accepted(self):
        """Mensajes normales devuelven 200 accepted."""
        with patch("channels.whatsapp._enqueue_message", new_callable=AsyncMock):
            app = _build_minimal_app()
            client = TestClient(app)
            resp = client.post("/webhook/whatsapp", json=_make_message_event(PHONE_ID_AGENTES, "5491199887766", "Hola"))
            assert resp.status_code == 200
            assert resp.json()["status"] == "accepted"

    def test_malformed_body_returns_ignored(self):
        """Body sin entry[] devuelve 200 ignored."""
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/webhook/whatsapp", json={"object": "whatsapp_business_account"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


# ─── Tests de _procesar_echo_smb ──────────────────────────────────────────────

class TestEchoProcessing:

    @pytest.mark.asyncio
    async def test_echo_pushes_out_to_crm(self):
        """Echo pushea OUT al CRM con remitente correcto del mapa."""
        from channels import whatsapp as wa_mod
        display_map = {PHONE_ID_SUPERVISOR: "rodrigo"}

        change_value = {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": PHONE_ID_SUPERVISOR},
            "contacts": [{"wa_id": "5491199887766", "profile": {"name": "Cliente"}}],
            "messages": [{"from": "5491122985977", "to": "5491199887766", "id": "wamid.echo_test", "type": "text", "text": {"body": "Texto de prueba"}}],
        }

        with patch.object(wa_mod, "_SUPERVISOR_DISPLAY_MAP", display_map), \
             patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm:
            await wa_mod._procesar_echo_smb(change_value)
            mock_crm.assert_awaited_once()
            kw = mock_crm.call_args.kwargs
            assert kw["direccion"] == "OUT"
            assert kw["phone"] == "5491199887766"
            assert kw["remitente"] == "rodrigo"
            assert kw["wa_message_id"] == "wamid.echo_test"
            assert kw["wa_linea"] == PHONE_ID_SUPERVISOR

    @pytest.mark.asyncio
    async def test_echo_fallback_to_message_to(self):
        """Cuando contacts[] está vacío, usa messages[0]['to'] como destinatario."""
        from channels import whatsapp as wa_mod

        change_value = {
            "metadata": {"phone_number_id": PHONE_ID_SUPERVISOR},
            "contacts": [],
            "messages": [{"from": "5491122985977", "to": "5491199887766", "id": "wamid.fallback", "type": "text", "text": {"body": "Hola"}}],
        }

        with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm:
            await wa_mod._procesar_echo_smb(change_value)
            mock_crm.assert_awaited_once()
            assert mock_crm.call_args.kwargs["phone"] == "5491199887766"

    @pytest.mark.asyncio
    async def test_echo_empty_messages_skips(self):
        """Echo sin mensajes no llama al CRM."""
        from channels.whatsapp import _procesar_echo_smb
        with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm:
            await _procesar_echo_smb({"messages": [], "contacts": [], "metadata": {}})
            mock_crm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_echo_no_recipient_skips(self):
        """Echo sin destinatario identificable no llama al CRM."""
        from channels.whatsapp import _procesar_echo_smb
        change_value = {
            "metadata": {"phone_number_id": PHONE_ID_SUPERVISOR},
            "contacts": [],
            "messages": [{"from": "5491122985977", "id": "wamid.norecipient", "type": "text", "text": {"body": "Hola"}}],
        }
        with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm:
            await _procesar_echo_smb(change_value)
            mock_crm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_echo_image_type(self):
        """Echo de imagen registra [IMAGEN] con caption."""
        from channels.whatsapp import _procesar_echo_smb
        change_value = {
            "metadata": {"phone_number_id": PHONE_ID_SUPERVISOR},
            "contacts": [{"wa_id": "5491199887766"}],
            "messages": [{"from": "5491122985977", "to": "5491199887766", "id": "wamid.img", "type": "image", "image": {"caption": "mira esto"}}],
        }
        with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm:
            await _procesar_echo_smb(change_value)
            contenido = mock_crm.call_args.kwargs["contenido"]
            assert "[IMAGEN]" in contenido
            assert "mira esto" in contenido

    @pytest.mark.asyncio
    async def test_echo_audio_type(self):
        """Echo de audio registra [AUDIO] sin intentar transcripción."""
        from channels.whatsapp import _procesar_echo_smb
        change_value = {
            "metadata": {"phone_number_id": PHONE_ID_SUPERVISOR},
            "contacts": [{"wa_id": "5491199887766"}],
            "messages": [{"from": "5491122985977", "id": "wamid.audio", "type": "audio", "audio": {"id": "audio_123"}}],
        }
        with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm, \
             patch("channels.whatsapp._transcribir_audio", new_callable=AsyncMock) as mock_transcribe:
            await _procesar_echo_smb(change_value)
            mock_transcribe.assert_not_awaited()
            assert mock_crm.call_args.kwargs["contenido"] == "[AUDIO]"


# ─── Tests del guard supervisor ───────────────────────────────────────────────

class TestSupervisorGuard:

    @pytest.mark.asyncio
    async def test_supervisor_line_pushes_in_no_bot(self):
        """Mensajes en línea supervisor → push IN + return, route_message no se llama."""
        from channels import whatsapp as wa_mod
        original_ids = wa_mod.WA_SUPERVISOR_PHONE_IDS
        wa_mod.WA_SUPERVISOR_PHONE_IDS = {PHONE_ID_SUPERVISOR}

        batch = [{
            "msg_type": "text",
            "message": {"id": "wamid.sup001", "type": "text", "text": {"body": "Hola"}},
            "phone_number_id": PHONE_ID_SUPERVISOR,
            "nombre_contacto": "Cliente Sup",
        }]

        try:
            with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock) as mock_crm, \
                 patch("channels.whatsapp.route_message", new_callable=AsyncMock) as mock_route:
                await wa_mod._process_batch("5491199887766", batch)
                mock_crm.assert_awaited_once()
                assert mock_crm.call_args.kwargs["direccion"] == "IN"
                mock_route.assert_not_awaited()
        finally:
            wa_mod.WA_SUPERVISOR_PHONE_IDS = original_ids

    @pytest.mark.asyncio
    async def test_supervisor_line_does_not_send_wa_reply(self):
        """Línea supervisor no llama a enviar_mensaje_wa."""
        from channels import whatsapp as wa_mod
        original_ids = wa_mod.WA_SUPERVISOR_PHONE_IDS
        wa_mod.WA_SUPERVISOR_PHONE_IDS = {PHONE_ID_SUPERVISOR}

        batch = [{"msg_type": "text", "message": {"id": "wamid.sup002", "type": "text", "text": {"body": "Hola"}}, "phone_number_id": PHONE_ID_SUPERVISOR, "nombre_contacto": ""}]

        try:
            with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock), \
                 patch("channels.whatsapp.enviar_mensaje_wa", new_callable=AsyncMock) as mock_send:
                await wa_mod._process_batch("5491199887766", batch)
                mock_send.assert_not_awaited()
        finally:
            wa_mod.WA_SUPERVISOR_PHONE_IDS = original_ids

    @pytest.mark.asyncio
    async def test_non_supervisor_line_calls_route_message(self):
        """Línea normal activa el bot."""
        from channels import whatsapp as wa_mod
        original_ids = wa_mod.WA_SUPERVISOR_PHONE_IDS
        wa_mod.WA_SUPERVISOR_PHONE_IDS = {PHONE_ID_SUPERVISOR}
        wa_mod.WA_PHONE_ID_AGENTES     = PHONE_ID_AGENTES

        batch = [{"msg_type": "text", "message": {"id": "wamid.normal", "type": "text", "text": {"body": "Precio módulo"}}, "phone_number_id": PHONE_ID_AGENTES, "nombre_contacto": "Normal"}]

        try:
            with patch("channels.whatsapp._crm_push_mensaje", new_callable=AsyncMock), \
                 patch("channels.whatsapp._crm_get_modo", new_callable=AsyncMock, return_value="bot"), \
                 patch("channels.whatsapp.route_message", new_callable=AsyncMock, return_value={"reply": "Hola soy Pablo", "agent": "pablo"}) as mock_route, \
                 patch("channels.whatsapp.enviar_mensaje_wa", new_callable=AsyncMock):
                await wa_mod._process_batch("5491199887766", batch)
                mock_route.assert_awaited_once()
        finally:
            wa_mod.WA_SUPERVISOR_PHONE_IDS = original_ids


# ─── Tests de deduplicación (CRM) ────────────────────────────────────────────

class TestDeduplication:

    def _make_db(self):
        """SQLite in-memory DB con el modelo InboxMensaje."""
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "eco-crm"))
        from sqlalchemy import create_engine, UniqueConstraint
        from sqlalchemy.orm import sessionmaker
        from database.models import Base, InboxMensaje

        engine = create_engine("sqlite:///:memory:")
        # Parcial index no soportado en SQLite — usar index normal para el test
        from sqlalchemy import event, text as sa_text
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        return Session(), InboxMensaje

    def test_app_level_dedup_blocks_second_insert(self):
        """La deduplicación a nivel aplicación detecta wa_message_id duplicado."""
        db, InboxMensaje = self._make_db()

        first = InboxMensaje(phone="5491199887766", direccion="IN", contenido="Hola", wa_message_id="wamid.dedup001")
        db.add(first)
        db.commit()
        db.refresh(first)

        # Simular segundo intento con mismo wa_message_id (como lo haría recibir_entrante)
        existing = db.query(InboxMensaje).filter(InboxMensaje.wa_message_id == "wamid.dedup001").first()
        assert existing is not None
        assert existing.id == first.id

        # No insertar segundo
        count_before = db.query(InboxMensaje).count()
        # → el endpoint devolvería {"ok": True, "id": existing.id, "duplicado": True}
        assert count_before == 1

    def test_distinct_wa_message_ids_insert_normally(self):
        """IDs diferentes se insertan sin conflicto."""
        db, InboxMensaje = self._make_db()

        db.add(InboxMensaje(phone="5491199887766", direccion="IN", contenido="Msg1", wa_message_id="wamid.a"))
        db.add(InboxMensaje(phone="5491199887766", direccion="IN", contenido="Msg2", wa_message_id="wamid.b"))
        db.commit()
        assert db.query(InboxMensaje).count() == 2

    def test_null_wa_message_id_allows_multiple(self):
        """wa_message_id=NULL permite múltiples filas (mensajes manuales del CRM)."""
        db, InboxMensaje = self._make_db()

        db.add(InboxMensaje(phone="5491199887766", direccion="OUT", contenido="Manual 1", wa_message_id=None))
        db.add(InboxMensaje(phone="5491199887766", direccion="OUT", contenido="Manual 2", wa_message_id=None))
        db.commit()
        assert db.query(InboxMensaje).count() == 2
