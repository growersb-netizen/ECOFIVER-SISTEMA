"""Validación de pagos y movimientos de stock atómicos (Fase 0.5)."""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import MaterialInventario, Pago, StockPiscina, Usuario, VentaFinanciada
from routers import auth, materiales, ventas_financiadas
from utils.stock import descontar, sumar

SECRET = "secreto-de-prueba-pagos-" + "x" * 16


@pytest.fixture
def app_db(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add(Usuario(id=1, nombre="Admin", email="a@t", password_hash="x", roles_json='["ADMIN"]', activo=True))
    db.add(VentaFinanciada(id=1, cliente_nombre="Cliente", producto="PISCINA", precio_total=1_000_000,
                           valor_cuota=100_000, cantidad_cuotas=10, cuotas_pagas=0, anticipo=200_000,
                           estado_plan="ACTIVO"))
    db.add(MaterialInventario(id=1, nombre="Resina", unidad="kg", stock_actual=10))
    db.commit()
    app = FastAPI()
    app.include_router(ventas_financiadas.router)
    app.include_router(materiales.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    h = {"Authorization": f"Bearer {auth.create_access_token({'sub': '1'})}"}
    yield TestClient(app), db, h


@pytest.mark.parametrize("cuerpo", [
    {"monto": -50000, "modalidad": "efectivo", "concepto": "entrada"},
    {"monto": 0, "modalidad": "efectivo"},
    {"monto": "mucho", "modalidad": "efectivo"},
    {"monto": "NaN", "modalidad": "efectivo"},
    {"monto": "inf", "modalidad": "efectivo"},
    {"monto": True, "modalidad": "efectivo"},
    {"monto": 100000, "modalidad": "efectivo", "concepto": "regalo"},
])
def test_pago_invalido_se_rechaza_sin_tocar_la_base(app_db, cuerpo):
    c, db, h = app_db
    r = c.post("/api/ventas-financiadas/1/pago", headers=h, json=cuerpo)
    assert r.status_code == 400, r.text
    db.expire_all()
    v = db.get(VentaFinanciada, 1)
    assert (v.anticipo, v.cuotas_pagas) == (200_000, 0)
    assert db.query(Pago).count() == 0


def test_pago_valido_sigue_funcionando(app_db):
    c, db, h = app_db
    r = c.post("/api/ventas-financiadas/1/pago", headers=h,
               json={"monto": "100000", "modalidad": "transferencia"})
    assert r.status_code == 200 and r.json()["cuotas_pagas"] == 1
    assert db.query(Pago).one().monto == 100000


def test_descontar_y_sumar(app_db):
    _, db, _ = app_db
    db.add(StockPiscina(id=1, modelo="6m", color="azul", cantidad=1)); db.commit()
    assert descontar(db, StockPiscina, 1, "cantidad", 1)
    assert not descontar(db, StockPiscina, 1, "cantidad", 1)        # ya no alcanza
    for malo in (0, -1, "x", float("nan")):
        assert not descontar(db, StockPiscina, 1, "cantidad", malo)
        assert not sumar(db, StockPiscina, 1, "cantidad", malo)
    assert sumar(db, StockPiscina, 1, "cantidad", 2)
    db.commit(); db.expire_all()
    assert db.get(StockPiscina, 1).cantidad == 2


@pytest.mark.parametrize("tipo", ["ENTRADA", "SALIDA"])
def test_movimiento_con_cantidad_negativa_se_rechaza(app_db, monkeypatch, tipo):
    c, db, h = app_db
    monkeypatch.setattr(materiales, "_check_fabrica", lambda *a, **k: None)
    r = c.post("/api/materiales/inventario/1/movimiento", headers=h, json={"tipo": tipo, "cantidad": -5})
    assert r.status_code == 400
    db.expire_all()
    assert db.get(MaterialInventario, 1).stock_actual == 10


def test_salida_mayor_al_stock_conserva_comportamiento_existente(app_db, monkeypatch):
    c, db, h = app_db
    monkeypatch.setattr(materiales, "_check_fabrica", lambda *a, **k: None)
    c.post("/api/materiales/inventario/1/movimiento", headers=h, json={"tipo": "SALIDA", "cantidad": 3})
    c.post("/api/materiales/inventario/1/movimiento", headers=h, json={"tipo": "SALIDA", "cantidad": 50})
    db.expire_all()
    assert db.get(MaterialInventario, 1).stock_actual == 0


PG = os.getenv("PG_TEST_URL")   # p. ej. postgresql+psycopg2://postgres:pg@localhost/stock_test


@pytest.mark.skipif(not PG, reason="concurrencia real: requiere PG_TEST_URL (PostgreSQL local, nunca productivo)")
def test_concurrencia_real_no_vende_dos_veces_la_ultima_unidad():
    eng = create_engine(PG)
    StockPiscina.__table__.drop(eng, checkfirst=True)
    StockPiscina.__table__.create(eng)
    S = sessionmaker(bind=eng)
    with S() as s:
        s.add(StockPiscina(id=1, modelo="6m", color="azul", cantidad=1)); s.commit()
    barrera, resultados = threading.Barrier(8), []

    def vender():
        with S() as s:
            barrera.wait()
            ok = descontar(s, StockPiscina, 1, "cantidad", 1)
            s.commit()
            resultados.append(ok)
    hilos = [threading.Thread(target=vender) for _ in range(8)]
    [t.start() for t in hilos]; [t.join() for t in hilos]
    with S() as s:
        assert s.get(StockPiscina, 1).cantidad == 0
    assert resultados.count(True) == 1
    StockPiscina.__table__.drop(eng)
