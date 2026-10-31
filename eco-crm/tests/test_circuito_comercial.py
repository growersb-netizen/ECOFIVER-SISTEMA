"""
Circuito comercial (reglas del propietario), verificado en el backend:
  CONTADO: la IA cierra; entrega y cobro los confirma una persona.
  FINANCIACIÓN: la IA abre y deriva; Admisión humana aprueba, rechaza y cierra.
  COMISIONES: 10% contado al entregar; 2 cuotas iniciales al pagarse; sin duplicados.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base, get_db
from database.models import (ComisionPropietario, DistanciaLocalidad, Entrega, ExpedienteEvento, Lead, Usuario,
                             VentaContado, VentaFinanciada)
from routers import auth, circuito_comercial, instalacion, logistica, ventas_financiadas
from utils import circuito_comercial as cc

SECRET = "secreto-de-prueba-circuito-" + "x" * 16
KEY = "clave-servicio-circuito"
IA = {"Authorization": f"Bearer {KEY}", "X-Origen-Cliente": "multiagente"}
MCP = {"Authorization": f"Bearer {KEY}"}                       # mismo API key, sin identidad de agentes
PRECIO_PISCINA = 2490000                                        # Minideck (catálogo)
PRECIO_MODULO = 4990000                                         # Módulo ECO 12m²
FLETE_30KM = 30 * 3000
PRECIO_FINAL = PRECIO_PISCINA + FLETE_30KM                      # precio final único informado al cliente
CATALOGO = {"piscinas": {"precios": {"Minideck": PRECIO_PISCINA}, "medidas": {
    "Minideck": {"largo_m": 3.0, "profundidad_max_m": 0.7}}}}


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", SECRET)
    monkeypatch.setenv("API_KEY", KEY)
    monkeypatch.setattr(cc, "precio_catalogo", lambda prod, modelo: {
        ("PISCINA", "Minideck"): PRECIO_PISCINA, ("MODULO", "Módulo ECO 12m²"): PRECIO_MODULO}.get((prod, modelo)))
    from utils import cotizacion
    monkeypatch.setattr(cotizacion, "_catalogo", lambda: CATALOGO)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    db = S()
    roles = {1: '["ADMIN","PROPIETARIO"]', 2: '["ASESOR_APERTURA"]', 3: '["ADMISION"]', 4: '["LOGISTICA"]',
             5: '["COBRANZAS"]', 6: '["ADMIN"]', 7: '["ADMIN"]'}
    for uid, r in roles.items():
        db.add(Usuario(id=uid, nombre=f"u{uid}", email=f"u{uid}@t", password_hash="x", roles_json=r, activo=True,
                       es_agente_ia=(uid == 7), aliado_codigo=("AL-010" if uid == 6 else None)))
    db.add(Lead(id=10, nombre="Ana Pérez", telefono="5491100000010"))
    db.commit()
    from utils.cotizacion import cargar_distancia
    cargar_distancia(db, "Zárate", "", 30, "Google Maps (prueba)", 1)
    app = FastAPI()
    for r in (circuito_comercial, logistica, instalacion, ventas_financiadas):
        app.include_router(r.router)

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


def _cierre(c, agente="camila", **kw):
    body = {"lead_id": 10, "producto": "PISCINA", "modelo": "Minideck", "precio_final_acordado": PRECIO_FINAL,
            "color": "Celeste", "cliente_nombre": "Ana Pérez", "cliente_localidad": "Zárate",
            "cliente_domicilio": "Belgrano 123", "fecha_entrega_solicitada": "2099-01-15",
            "aceptacion_cliente": "Sí, la quiero, la pago contra entrega", **kw}
    return c.post("/api/comercial/contado/cierres", headers={**IA, "X-Agente": agente}, json=body)


# ── CONTADO ───────────────────────────────────────────────────────────────────

def test_ia_puede_cerrar_venta_de_contado(m):
    c, db, _ = m
    r = _cierre(c)
    assert r.status_code == 200, r.text
    v = r.json()["venta"]
    assert (v["circuito_estado"], v["cerrada_por"], v["precio_final"]) == ("CIERRE_COMERCIAL_CONFIRMADO", "agente:camila", PRECIO_PISCINA)
    assert _cierre(c).json()["creada"] is False                                   # idempotente
    r = c.post(f"/api/comercial/contado/{v['id']}/solicitar-entrega", headers={**IA, "X-Agente": "camila"})
    assert r.json()["venta"]["circuito_estado"] == "ENTREGA_PENDIENTE"
    assert db.query(ComisionPropietario).count() == 0                             # cerrar no genera comisión


@pytest.mark.parametrize("agente,kw,codigo", [
    ("nicolas", {}, 403),                                                         # financiación: no cierra contado
    ("valentina", {}, 403),
    ("luciano", {}, 403),                                                         # Luciano: viviendas, no piscinas
    ("camila", {"precio_final_acordado": PRECIO_FINAL - 200000}, 403),            # descuento no autorizado
    ("camila", {"modelo": "Modelo inventado"}, 400),
    ("camila", {"forma_pago": "FINANCIADO"}, 403),
    ("camila", {"aceptacion_cliente": ""}, 400),
    ("camila", {"lead_id": 999}, 400),
])
def test_cierres_no_permitidos(m, agente, kw, codigo):
    c, _, _ = m
    assert _cierre(c, agente, **kw).status_code == codigo


def test_luciano_cierra_viviendas_y_modulos(m):
    c, _, _ = m
    r = _cierre(c, "luciano", producto="MODULO", modelo="Módulo ECO 12m²", precio=PRECIO_MODULO, color=None,
                precio_final_acordado=None)
    assert r.status_code == 200 and r.json()["venta"]["producto"] == "MODULO"


def test_endpoints_de_ia_exigen_clave_e_identidad(m):
    c, _, tok = m
    body = {"lead_id": 10, "producto": "PISCINA", "modelo": "Minideck", "precio_final_acordado": PRECIO_FINAL,
            "cliente_nombre": "A", "cliente_localidad": "Zárate", "cliente_domicilio": "B", "aceptacion_cliente": "sí"}
    assert c.post("/api/comercial/contado/cierres", headers={"X-Origen-Cliente": "multiagente", "X-Agente": "camila"},
                  json=body).status_code == 401                                  # la identidad sola no autentica
    assert c.post("/api/comercial/contado/cierres", headers={**MCP, "X-Agente": "camila"}, json=body).status_code == 403
    assert c.post("/api/comercial/contado/cierres", headers=IA, json=body).status_code == 403   # sin agente
    assert c.post("/api/comercial/contado/cierres", headers=tok(1), json=body).status_code == 401


def test_ia_no_puede_confirmar_entrega_ni_registrar_cobro(m):
    c, db, tok = m
    v = _cierre(c).json()["venta"]
    for ruta in ("confirmar-entrega", "confirmar-cobro"):
        assert c.post(f"/api/comercial/contado/{v['id']}/{ruta}", headers=IA,
                      json={"evidencia": "remito 123"}).status_code == 401           # API key: no es persona
        assert c.post(f"/api/comercial/contado/{v['id']}/{ruta}", headers={**tok(1), "X-Origen-Cliente": "multiagente"},
                      json={"evidencia": "remito 123"}).status_code == 403
    assert c.post(f"/api/comercial/contado/{v['id']}/confirmar-entrega", headers=tok(7),
                  json={"evidencia": "remito 123"}).status_code == 403              # usuario técnico de IA
    assert db.query(ComisionPropietario).count() == 0


def test_ia_no_usa_endpoints_financieros_existentes(m):
    c, db, tok = m
    db.add(VentaFinanciada(id=1, cliente_nombre="X", producto="PISCINA", precio_total=1e6, valor_cuota=1e5,
                           cantidad_cuotas=10, estado_plan="ACTIVO"))
    db.commit()
    pago = {"monto": 100000, "modalidad": "efectivo"}
    assert c.post("/api/ventas-financiadas/1/pago", headers=IA, json=pago).status_code == 403
    assert c.post("/api/ventas-financiadas", headers=IA, json={"cliente_nombre": "X"}).status_code == 403
    r = c.post("/api/ventas-financiadas/1/pago", headers=MCP, json=pago)      # otros clientes: sin cambios
    assert r.status_code != 403


def test_entrega_y_cobro_por_personas_con_evidencia(m):
    c, db, tok = m
    v = _cierre(c).json()["venta"]
    url = f"/api/comercial/contado/{v['id']}"
    assert c.post(f"{url}/confirmar-cobro", headers=tok(5), json={"evidencia": "recibo 55"}).status_code == 409  # antes, entrega
    assert c.post(f"{url}/confirmar-entrega", headers=tok(2), json={"evidencia": "remito"}).status_code == 403   # vendedor
    assert c.post(f"{url}/confirmar-entrega", headers=tok(6), json={"evidencia": "remito"}).status_code == 403   # socio ADMIN
    assert c.post(f"{url}/confirmar-entrega", headers=tok(4), json={"evidencia": ""}).status_code == 400        # sin evidencia
    r = c.post(f"{url}/confirmar-entrega", headers=tok(4), json={"evidencia": "Remito 0001-245 firmado"})
    assert r.json()["venta"]["circuito_estado"] == "ENTREGA_CONFIRMADA"
    r = c.post(f"{url}/confirmar-cobro", headers=tok(5), json={"evidencia": "Recibo 77", "monto": PRECIO_PISCINA})
    assert r.json()["venta"]["circuito_estado"] == "COBRO_CONFIRMADO"


# ── COMISIÓN DE CONTADO ───────────────────────────────────────────────────────

def test_comision_contado_al_entregar_y_sin_duplicar(m):
    c, db, tok = m
    v = _cierre(c).json()["venta"]
    db.add(Entrega(id=50, venta_contado_id=v["id"], cliente_nombre="Ana", estado="COORDINADA"))
    db.commit()
    c.put("/api/logistica/entregas/50", headers=tok(4), json={"estado": "INSTALADA"})      # logística
    c.post(f"/api/comercial/contado/{v['id']}/confirmar-entrega", headers=tok(4), json={"evidencia": "remito repetido"})
    c.post(f"/api/instalacion/contraentregas/{v['id']}/cobro", headers=tok(5), json={"cobro_estado": "COBRADO"})
    com = db.query(ComisionPropietario).all()
    assert len(com) == 1
    assert (com[0].monto, com[0].regla, com[0].estado) == (249000.0, "10% del valor del producto", "GENERADA")
    db.expire_all()
    venta = db.get(VentaContado, v["id"])
    assert com[0].generada_at == venta.entrega_confirmada_at                       # fecha real de la entrega


def test_venta_cerrada_sin_entregar_es_proyectada(m):
    c, db, tok = m
    _cierre(c)
    p = c.get("/api/propietario/panel", headers=tok(1)).json()
    assert p["comisiones_generadas"]["total"] == 0
    assert p["comisiones_proyectadas"]["contado"] == 249000.0
    assert "PROYECCIÓN" in p["comisiones_proyectadas"]["fuente"]


# ── FINANCIACIÓN Y ADMISIÓN ───────────────────────────────────────────────────

def _abrir(c, agente="nicolas", **kw):
    body = {"producto": "PISCINA", "cliente_nombre": "Juan Gómez", "cliente_telefono": "5491100000011", "lead_id": 10,
            "modelo": "Minideck", "valor_cuota_estimado": 350000,
            "datos_apertura": {"localidad": "Campana", "dni": "12345678", "recibo_sueldo": "base64..."}, **kw}
    return c.post("/api/comercial/financiacion/expedientes", headers={**IA, "X-Agente": agente}, json=body)


def _estado_ia(c, exp_id, estado, agente="nicolas"):
    return c.post(f"/api/comercial/financiacion/expedientes/{exp_id}/estado", headers={**IA, "X-Agente": agente},
                  json={"estado": estado, "detalle": "x"})


def test_ia_abre_deriva_y_agenda_sin_datos_sensibles(m):
    c, db, tok = m
    e = _abrir(c).json()["expediente"]
    assert e["estado"] == "CONSULTA_RECIBIDA"
    for est in ("APERTURA_EN_PROCESO", "VIDEOLLAMADA_PENDIENTE", "EN_ADMISION"):
        assert _estado_ia(c, e["id"], est).status_code == 200
    det = c.get(f"/api/admision/expedientes/{e['id']}", headers=tok(3)).json()
    assert det["estado"] == "EN_ADMISION"
    assert det["datos_apertura"] == {"localidad": "Campana"}                      # DNI y recibo descartados
    assert "descartados: dni, recibo_sueldo" in det["eventos"][0]["detalle"]


@pytest.mark.parametrize("estado", ["APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION", "CIERRE_HUMANO_CONFIRMADO",
                                    "DOCUMENTACION_PENDIENTE"])
@pytest.mark.parametrize("agente", ["nicolas", "mateo", "maximo", "ezequiel"])
def test_ia_no_aprueba_rechaza_ni_cierra_y_queda_auditado(m, estado, agente):
    c, db, _ = m
    e = _abrir(c).json()["expediente"]
    for est in ("APERTURA_EN_PROCESO", "PRECALIFICADO", "EN_ADMISION"):
        _estado_ia(c, e["id"], est)
    assert _estado_ia(c, e["id"], estado, agente).status_code == 403
    intento = db.query(ExpedienteEvento).filter(ExpedienteEvento.detalle.like("INTENTO RECHAZADO%")).one()
    assert intento.actor == f"agente:{agente}"


def test_valentina_abre_pero_no_deriva(m):
    c, _, _ = m
    e = _abrir(c, "valentina").json()["expediente"]
    assert _estado_ia(c, e["id"], "APERTURA_EN_PROCESO", "valentina").status_code == 403


def test_solo_admision_decide_y_todo_queda_auditado(m):
    c, db, tok = m
    e = _abrir(c).json()["expediente"]
    for est in ("APERTURA_EN_PROCESO", "PRECALIFICADO", "EN_ADMISION"):
        _estado_ia(c, e["id"], est)
    url = f"/api/admision/expedientes/{e['id']}/estado"
    aprobar = {"estado": "APROBADO_POR_ADMISION", "detalle": "Identidad y capacidad verificadas en videollamada"}
    for uid in (1, 2, 4, 6, 7):                                                     # ni ADMIN, ni vendedor, ni socio, ni IA
        assert c.post(url, headers=tok(uid), json=aprobar).status_code == 403
    assert c.post(url, headers={**tok(3), "X-Origen-Cliente": "multiagente"}, json=aprobar).status_code == 403
    assert c.post(url, headers=tok(3), json={"estado": "APROBADO_POR_ADMISION", "detalle": ""}).status_code == 400
    assert c.post(url, headers=tok(3), json=aprobar).json()["expediente"]["estado"] == "APROBADO_POR_ADMISION"
    det = c.get(f"/api/admision/expedientes/{e['id']}", headers=tok(3)).json()
    ultimo = det["eventos"][-1]
    assert (ultimo["de"], ultimo["a"], ultimo["actor"]) == ("EN_ADMISION", "APROBADO_POR_ADMISION", "usuario:3")


def test_admision_rechaza(m):
    c, _, tok = m
    e = _abrir(c).json()["expediente"]
    for est in ("APERTURA_EN_PROCESO", "PRECALIFICADO", "EN_ADMISION"):
        _estado_ia(c, e["id"], est)
    r = c.post(f"/api/admision/expedientes/{e['id']}/estado", headers=tok(3),
               json={"estado": "RECHAZADO_POR_ADMISION", "detalle": "Ingresos no acreditados"})
    assert r.json()["expediente"]["estado"] == "RECHAZADO_POR_ADMISION"


def test_comision_financiada_solo_con_aprobacion_suscripcion_y_pago(m):
    c, db, tok = m
    db.add(VentaFinanciada(id=9, cliente_nombre="Juan Gómez", producto="PISCINA", precio_total=8_400_000,
                           valor_cuota=350_000, cantidad_cuotas=24, estado_plan="ACTIVO"))
    db.commit()
    e = _abrir(c).json()["expediente"]
    for est in ("APERTURA_EN_PROCESO", "PRECALIFICADO", "EN_ADMISION"):
        _estado_ia(c, e["id"], est)
    url = f"/api/admision/expedientes/{e['id']}"
    cuotas = lambda: c.post(f"{url}/cuotas-iniciales", headers=tok(5), json={"evidencia": "Recibos 1 y 2"})
    assert cuotas().status_code == 409                                             # sin aprobación
    c.post(f"{url}/estado", headers=tok(3), json={"estado": "APROBADO_POR_ADMISION", "detalle": "verificado ok"})
    assert cuotas().status_code == 409                                             # aprobado sin suscripción
    assert c.post(f"{url}/estado", headers=tok(3), json={"estado": "CIERRE_HUMANO_CONFIRMADO"}).status_code == 400
    c.post(f"{url}/estado", headers=tok(3), json={"estado": "CIERRE_HUMANO_CONFIRMADO", "venta_financiada_id": 9})
    assert db.query(ComisionPropietario).count() == 0                              # suscripción sin pago
    assert c.post(f"{url}/cuotas-iniciales", headers=IA, json={"evidencia": "x x x x x"}).status_code == 401
    assert cuotas().status_code == 200
    assert cuotas().status_code == 200                                             # reproceso
    com = db.query(ComisionPropietario).one()
    assert (com.tipo, com.monto, com.base_calculo, com.regla) == ("FINANCIADO", 700000.0, 350000.0, "100% de las 2 cuotas iniciales")


# ── PANEL DEL PROPIETARIO ─────────────────────────────────────────────────────

def test_panel_solo_propietario(m):
    c, _, tok = m
    assert c.get("/api/propietario/panel", headers=tok(1)).status_code == 200
    for uid in (2, 3, 6, 7):                                                        # incluido un socio con ADMIN
        assert c.get("/api/propietario/panel", headers=tok(uid)).status_code == 403
    assert c.get("/api/propietario/panel", headers=IA).status_code == 401


def test_panel_objetivos_gastos_y_cobro_de_comision(m):
    c, db, tok = m
    v = _cierre(c).json()["venta"]
    c.post(f"/api/comercial/contado/{v['id']}/confirmar-entrega", headers=tok(4), json={"evidencia": "remito 9"})
    periodo = datetime.utcnow().strftime("%Y-%m")
    c.post("/api/propietario/objetivos", headers=tok(1), json={"periodo": periodo, "indicador": "comisiones_generadas", "valor": 1_000_000})
    o2 = c.post("/api/propietario/objetivos", headers=tok(1), json={"periodo": periodo, "indicador": "comisiones_generadas",
                                                                   "valor": 498_000}).json()["objetivo"]
    assert o2["version"] == 2
    c.post("/api/propietario/gastos", headers=tok(1), json={"tipo": "GASTO", "fecha": f"{periodo}-01", "monto": 50000, "canal": "meta"})
    c.post("/api/propietario/gastos", headers=tok(1), json={"tipo": "PRESUPUESTO", "fecha": f"{periodo}-01", "monto": 200000})
    p = c.get(f"/api/propietario/panel?periodo={periodo}", headers=tok(1)).json()
    assert p["comisiones_generadas"]["total"] == 249000.0 and p["comisiones_cobradas"]["total"] == 0
    assert p["objetivos"]["comisiones_generadas"] == {"valor": 498000.0, "version": 2, "cumplimiento_pct": 50.0}
    assert p["inversion_publicitaria"] == {"gasto_real": 50000.0, "presupuesto": 200000.0, "fuente": "gastos_publicitarios del período"}
    assert p["resultado_personal"]["total"] == -50000.0                           # aún no cobró la comisión
    com = db.query(ComisionPropietario).one()
    assert c.post(f"/api/propietario/comisiones/{com.id}/cobrada", headers=tok(1), json={"evidencia": ""}).status_code == 400
    c.post(f"/api/propietario/comisiones/{com.id}/cobrada", headers=tok(1), json={"evidencia": "Transferencia 31/10"})
    p = c.get(f"/api/propietario/panel?periodo={periodo}", headers=tok(1)).json()
    assert p["comisiones_cobradas"]["total"] == 249000.0 and p["resultado_personal"]["total"] == 199000.0
    assert c.post(f"/api/propietario/comisiones/{com.id}/anular", headers=tok(1), json={"motivo": "x"}).status_code == 400
