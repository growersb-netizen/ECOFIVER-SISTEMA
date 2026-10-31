"""Multiagente (política + ejecutor reales) → CRM (API real) en el circuito comercial. IA no simulada: no hace falta."""
import asyncio
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import DistanciaLocalidad, ExpedienteFinanciacion, Lead, VentaContado
from routers import circuito_comercial
from utils import circuito_comercial as cc

KEY = "clave-e2e-circuito"


@pytest.fixture
def e2e(monkeypatch):
    ma = Path(__file__).resolve().parents[2] / "eco-multiagente"
    monkeypatch.syspath_prepend(str(ma))
    monkeypatch.setenv("API_KEY", KEY)
    crm_client = importlib.import_module("tools.crm_client")
    acciones = importlib.import_module("tools.crm_actions")
    politica = importlib.import_module("tools.action_policy")
    monkeypatch.setattr(crm_client, "CRM_BASE_URL", "http://crm.test")
    monkeypatch.setattr(crm_client, "HEADERS", {**crm_client.HEADERS, "Authorization": f"Bearer {KEY}"})
    monkeypatch.setattr(cc, "precio_catalogo", lambda p, mo: 2490000 if (p, mo) == ("PISCINA", "Minideck") else None)
    from utils import cotizacion
    monkeypatch.setattr(cotizacion, "_catalogo", lambda: {"piscinas": {"precios": {"Minideck": 2490000},
                                                                       "medidas": {"Minideck": {"largo_m": 3.0}}}})
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add(Lead(id=10, nombre="Ana", telefono="5491100000010"))
    db.commit()
    cotizacion.cargar_distancia(db, "Zárate", "", 10, "prueba", None)
    app = FastAPI()
    app.include_router(circuito_comercial.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.ASGITransport(app=app), **kw))

    def correr(agente, tipo, datos, canal="cliente", lead_id=10):
        ctx = politica.ActionContext(agente=agente, canal=canal, lead_id=lead_id, origen="whatsapp")
        return asyncio.run(acciones.ejecutar_acciones([{"tipo": tipo, "datos": datos}], ctx))
    yield correr, db


CIERRE = {"lead_id": 10, "producto": "PISCINA", "modelo": "Minideck", "precio_final_acordado": 2520000,
          "color": "Celeste", "cliente_nombre": "Ana Pérez", "cliente_localidad": "Zárate",
          "cliente_domicilio": "Belgrano 123", "fecha_entrega_solicitada": "2099-01-10",
          "aceptacion_cliente": "Confirmo la compra"}


def test_camila_cierra_desde_whatsapp_y_pide_entrega(e2e):
    correr, db = e2e
    out = correr("camila", "cerrar_venta_contado", CIERRE)
    assert out.startswith("✅") and "entrega solicitada" in out
    v = db.query(VentaContado).one()
    assert (v.circuito_estado, v.cerrada_por) == ("ENTREGA_PENDIENTE", "agente:camila")


def test_cierre_de_otro_lead_bloqueado_por_la_politica(e2e):
    correr, db = e2e
    out = correr("camila", "cerrar_venta_contado", {**CIERRE, "lead_id": 99})
    assert out.startswith("⛔") and db.query(VentaContado).count() == 0


def test_descuento_rechazado_por_el_crm(e2e):
    correr, db = e2e
    out = correr("camila", "cerrar_venta_contado", {**CIERRE, "precio_final_acordado": 1990000})
    assert "no coincide con la cotización" in out and db.query(VentaContado).count() == 0


@pytest.mark.parametrize("tipo", ["pagar_cuota", "venta_financiada", "emitir_contrato", "venta_contado"])
def test_dinero_y_contratos_nunca_desde_conversaciones_con_clientes(e2e, tipo):
    correr, db = e2e
    for agente in ("maximo", "ezequiel", "camila"):
        assert correr(agente, tipo, {"venta_id": 1, "monto": 100, "lead_id": 10}).startswith("⛔")
    assert correr("camila", tipo, {"venta_id": 1, "monto": 100}, canal="confiable", lead_id=None).startswith("⛔")


def test_nicolas_abre_y_deriva_a_admision(e2e):
    correr, db = e2e
    out = correr("nicolas", "abrir_financiacion", {"lead_id": 10, "producto": "PISCINA", "cliente_nombre": "Juan",
                                                    "modelo": "Minideck", "etapa": "EN_ADMISION"})
    assert out.startswith("✅") and "EN_ADMISION" in out
    assert db.query(ExpedienteFinanciacion).one().estado == "EN_ADMISION"


def test_lead_de_la_conversacion_se_completa_solo(e2e):
    correr, db = e2e
    datos = {k: v for k, v in CIERRE.items() if k != "lead_id"}
    assert correr("camila", "cerrar_venta_contado", datos).startswith("✅")
    assert db.query(VentaContado).one().lead_id == 10
