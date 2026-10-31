"""
Reglas comerciales de piscinas de contado (flujo vigente de EcoFiver):
flete por km de ida desde Zárate, precio final único, promociones de flete con
reserva semanal, autoportantes ≤ 4,10 m, excavación incluida, pago contra
entrega, cierre en el CRM y comisión sobre el producto al entregar.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import ComisionPropietario, ConfiguracionSistema, DistanciaLocalidad, Lead, Usuario, VentaContado
from routers import auth, circuito_comercial
from utils import cotizacion

SECRET = "secreto-de-prueba-cotizacion-" + "x" * 16
KEY = "clave-cotizacion"
CAMILA = {"Authorization": f"Bearer {KEY}", "X-Origen-Cliente": "multiagente", "X-Agente": "camila"}
CATALOGO = {"piscinas": {
    "precios": {"Minideck": 2490000, "Minimalista Mediana": 5990000, "Arco Romano Grande Recto": 7990000,
                "Playa y Abanico": 9490000, "Autoportante": 2990000, "Autoportante Gigante": 3990000},
    "medidas": {"Minideck": {"largo_m": 3.0, "profundidad_max_m": 0.7},
                "Minimalista Mediana": {"largo_m": 5.5, "profundidad_max_m": 1.5},
                "Arco Romano Grande Recto": {"largo_m": 8.1, "profundidad_max_m": 1.8},
                "Playa y Abanico": {"largo_m": 9.2, "profundidad_max_m": 1.8},
                "Autoportante": {"largo_m": 4.1, "profundidad_max_m": 0.7},
                "Autoportante Gigante": {"largo_m": 5.0, "profundidad_max_m": 0.7}}}}


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", KEY)
    monkeypatch.setattr(cotizacion, "_catalogo", lambda: CATALOGO)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    db.add_all([Usuario(id=1, nombre="Rodrigo", email="r@t", password_hash="x", roles_json='["ADMIN","PROPIETARIO"]', activo=True),
                Usuario(id=2, nombre="Log", email="l@t", password_hash="x", roles_json='["LOGISTICA"]', activo=True),
                Usuario(id=3, nombre="Vend", email="v@t", password_hash="x", roles_json='["ASESOR_APERTURA"]', activo=True),
                Lead(id=10, nombre="Ana", telefono="5491100000010")])
    db.commit()
    cotizacion.cargar_distancia(db, "Pilar", "Buenos Aires", 60, "Google Maps ruta más corta", 1)
    app = FastAPI()
    app.include_router(circuito_comercial.router)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    tok = lambda uid: {"Authorization": f"Bearer {auth.create_access_token({'sub': str(uid)})}"}
    yield c, db, tok


def cot(c, modelo="Minideck", localidad="Pilar", **kw):
    r = c.post("/api/comercial/contado/cotizar", headers=CAMILA, json={"modelo": modelo, "localidad": localidad, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ── Cotización ────────────────────────────────────────────────────────────────

def test_flete_general_3000_por_km_de_ida_y_precio_final_unico(m):
    c, _, _ = m
    q = cot(c)
    assert q["interno"]["tarifa_km"] == 3000 and q["interno"]["flete_bruto"] == 180000
    assert q["precio_final"] == 2490000 + 180000                         # UN precio, producto + traslado
    assert set(q) >= {"precio_final", "incluye", "pago"} and q["pago"] == "contra entrega, en domicilio"


@pytest.mark.parametrize("modelo,tarifa", [("Arco Romano Grande Recto", 5000), ("Playa y Abanico", 5000),
                                           ("Minimalista Mediana", 3000)])
def test_modelos_especiales_5000_por_km(m, modelo, tarifa):
    c, _, _ = m
    assert cot(c, modelo)["interno"]["tarifa_km"] == tarifa


def test_tarifas_configurables(m):
    c, db, _ = m
    db.add_all([ConfiguracionSistema(clave="flete_precio_km", valor="3500"),
                ConfiguracionSistema(clave="flete_km_especial", valor="6000"),
                ConfiguracionSistema(clave="flete_modelos_especiales", valor="Minimalista")])
    db.commit()
    assert cot(c)["interno"]["tarifa_km"] == 3500
    assert cot(c, "Minimalista Mediana")["interno"]["tarifa_km"] == 6000
    assert cot(c, "Playa y Abanico")["interno"]["tarifa_km"] == 3500


def test_sin_proveedor_de_rutas_no_inventa_distancias(m, monkeypatch):
    c, _, _ = m
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    q = cot(c, localidad="Bariloche", provincia="Río Negro")
    assert (q["ok"], q["motivo"], q["estado_proveedor"]) == (False, "distancia_no_disponible", "sin_proveedor")
    assert "precio_final" not in q


def test_localidad_ambigua_sin_provincia_no_se_adivina(m):
    c, db, _ = m
    cotizacion.cargar_distancia(db, "Pilar", "Córdoba", 700, "x x x", 1)
    q = cot(c)
    assert (q["ok"], q["motivo"], q["candidatos"]) == (False, "localidad_ambigua", ["Buenos Aires", "Córdoba"])
    assert cot(c, provincia="Buenos Aires")["interno"]["km_ida"] == 60


def test_excavacion_incluida_en_enterradas_y_no_en_autoportantes(m):
    c, _, _ = m
    assert "excavación necesaria" in cot(c, "Minimalista Mediana")["incluye"]
    assert "excavación necesaria" not in cot(c, "Autoportante")["incluye"]
    assert {"piscina", "traslado", "instalación", "equipo de filtrado completo"} <= set(cot(c)["incluye"])


def test_no_se_ofrecen_autoportantes_de_mas_de_4_10(m):
    c, _, _ = m
    assert cot(c, "Autoportante")["ok"] is True
    assert cot(c, "Autoportante Gigante")["motivo"] == "autoportante_fuera_de_rango"


def test_modelo_sin_precio_vigente(m):
    c, _, _ = m
    assert cot(c, "Modelo de 2019")["motivo"] == "modelo_sin_precio"


# ── Promociones ───────────────────────────────────────────────────────────────

def _promo(c, tok, desde, hasta, valor=50):
    return c.post("/api/comercial/promociones", headers=tok(1), json={
        "nombre": "Semana del flete", "valor": valor, "desde": desde.isoformat(), "hasta": hasta.isoformat()})


def test_50_por_ciento_del_flete_solo_reservando_fecha_en_la_semana(m):
    c, _, tok = m
    hoy = date.today()
    assert _promo(c, tok, hoy - timedelta(days=1), hoy + timedelta(days=5)).status_code == 200
    sin_reserva = cot(c)
    assert sin_reserva["interno"]["descuento_flete"] == 0
    assert sin_reserva["promocion_disponible"]["precio_final_con_promocion"] == 2490000 + 90000
    con_reserva = cot(c, reserva_fecha=True)
    assert con_reserva["interno"]["descuento_flete"] == 90000                # 50% del traslado, no del producto
    assert con_reserva["precio_final"] == 2490000 + 90000


def test_promocion_vencida_o_desactivada_no_aplica(m):
    c, _, tok = m
    hoy = date.today()
    _promo(c, tok, hoy - timedelta(days=10), hoy - timedelta(days=3))
    assert cot(c, reserva_fecha=True)["interno"]["descuento_flete"] == 0
    p = _promo(c, tok, hoy, hoy + timedelta(days=6)).json()["promocion"]
    c.post(f"/api/comercial/promociones/{p['id']}/desactivar", headers=tok(1))
    assert cot(c, reserva_fecha=True)["interno"]["descuento_flete"] == 0


def test_solo_el_propietario_autoriza_promociones(m):
    c, _, tok = m
    hoy = date.today()
    for h in (tok(2), tok(3), CAMILA):
        assert _promo_con(c, h, hoy).status_code in (401, 403)


def _promo_con(c, headers, hoy):
    return c.post("/api/comercial/promociones", headers=headers, json={
        "nombre": "x x x", "valor": 50, "desde": hoy.isoformat(), "hasta": hoy.isoformat()})


def test_distancias_las_carga_el_equipo_interno_con_fuente(m):
    c, _, tok = m
    body = {"localidad": "Campana", "provincia": "Buenos Aires", "km_ida": 15, "fuente": "Google Maps 31/10"}
    assert c.post("/api/comercial/distancias", headers=tok(3), json=body).status_code == 403
    assert c.post("/api/comercial/distancias", headers=CAMILA, json=body).status_code == 401
    assert c.post("/api/comercial/distancias", headers=tok(2), json={**body, "fuente": ""}).status_code == 400
    assert c.post("/api/comercial/distancias", headers=tok(2), json=body).status_code == 200
    assert cot(c, localidad="Campana", provincia="Buenos Aires")["interno"]["flete_bruto"] == 45000


# ── Cierre, registro y comisión ───────────────────────────────────────────────

def _cerrar(c, **kw):
    body = {"lead_id": 10, "producto": "PISCINA", "modelo": "Minideck", "color": "Celeste", "cliente_nombre": "Ana Pérez",
            "cliente_localidad": "Pilar", "cliente_provincia": "Buenos Aires", "cliente_domicilio": "Belgrano 123",
            "fecha_entrega_solicitada": (date.today() + timedelta(days=14)).isoformat(),
            "precio_final_acordado": 2490000 + 180000, "aceptacion_cliente": "Dale, la reservo", **kw}
    return c.post("/api/comercial/contado/cierres", headers=CAMILA, json=body)


def test_cierre_registra_todo_en_el_crm_con_desglose_interno(m):
    c, db, _ = m
    r = _cerrar(c)
    assert r.status_code == 200, r.text
    v = db.query(VentaContado).one()
    assert (v.cliente_nombre, v.cliente_telefono, v.modelo_especifico, v.color, v.cliente_localidad,
            v.cliente_domicilio) == ("Ana Pérez", "5491100000010", "Minideck", "Celeste", "Pilar", "Belgrano 123")
    assert (v.precio_final, v.flete_bruto, v.flete_calculado, v.precio_total_acordado) == (2490000, 180000, 180000, 2670000)
    assert v.fecha_entrega_solicitada == date.today() + timedelta(days=14)
    assert (v.modalidad_cobro, v.cobro_estado, v.circuito_estado) == ("CONTRAENTREGA", "PENDIENTE", "CIERRE_COMERCIAL_CONFIRMADO")
    assert "Pago contra entrega en domicilio, sin seña" in v.notas


def test_cierre_con_promocion_y_reserva_de_fecha(m):
    c, db, tok = m
    hoy = date.today()
    _promo(c, tok, hoy, hoy + timedelta(days=6))
    assert _cerrar(c).status_code == 403                                   # precio sin promo: no coincide
    assert _cerrar(c, precio_final_acordado=2490000 + 90000).status_code == 200
    v = db.query(VentaContado).one()
    assert (v.descuento_flete, v.flete_calculado, v.promocion_id) == (90000, 90000, 1)


@pytest.mark.parametrize("falta", ["cliente_domicilio", "color", "fecha_entrega_solicitada", "precio_final_acordado"])
def test_cierre_exige_los_datos_del_flujo(m, falta):
    c, _, _ = m
    assert _cerrar(c, **{falta: None}).status_code == 400


def test_cierre_sin_distancia_disponible_no_se_registra(m):
    c, db, _ = m
    r = _cerrar(c, cliente_localidad="Bariloche", cliente_provincia="Río Negro")
    assert r.status_code == 409 and db.query(VentaContado).count() == 0


def test_comision_al_entregar_sobre_el_producto_no_sobre_el_flete(m):
    c, db, tok = m
    v = _cerrar(c).json()["venta"]
    assert db.query(ComisionPropietario).count() == 0
    c.post(f"/api/comercial/contado/{v['id']}/confirmar-entrega", headers=tok(2), json={"evidencia": "Remito 0001-77"})
    com = db.query(ComisionPropietario).one()
    assert (com.base_calculo, com.monto) == (2490000, 249000.0)            # 10% de la piscina, no de $2.670.000


def test_vendedores_socios_usan_la_misma_herramienta(m, monkeypatch):
    c, db, tok = m
    from database.models import Aliado
    from routers import socios
    monkeypatch.setattr(socios, "SECRET_KEY", SECRET)
    db.add(Aliado(id=5, codigo="AL-500", nombre="Socio", telefono="1", estado="activo"))
    db.commit()
    socio = {"Authorization": "x"}
    c.cookies.set("socio_token", socios._crear_token_socio(5))
    r = c.post("/api/socio/cotizar", json={"modelo": "Minideck", "localidad": "Pilar", "provincia": "Buenos Aires"})
    assert r.status_code == 200 and r.json()["precio_final"] == 2490000 + 180000
    c.cookies.clear()
    assert c.post("/api/socio/cotizar", json={"modelo": "Minideck", "localidad": "Pilar"}).status_code == 401
    h = c.post("/api/comercial/cotizar", headers=tok(3), json={"modelo": "Minideck", "localidad": "Pilar",
                                                                 "provincia": "Buenos Aires"})
    assert h.json()["precio_final"] == 2490000 + 180000                   # vendedor humano del CRM
