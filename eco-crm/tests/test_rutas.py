"""
Servicio de distancias por ruta (Google Geocoding + Routes simulados, sin red ni costo):
km reales por ruta (no línea recta), caché, localidades ambiguas, dirección exacta,
cambio de origen y fallas del proveedor sin precio inventado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base
from database.models import ConfiguracionSistema, DistanciaLocalidad
from utils import cotizacion, rutas

CATALOGO = {"piscinas": {"precios": {"Minideck": 2490000, "Arco Romano Grande Recto": 7990000},
                         "medidas": {"Minideck": {"largo_m": 3.0, "profundidad_max_m": 0.7},
                                     "Arco Romano Grande Recto": {"largo_m": 8.1, "profundidad_max_m": 1.8}}}}

LUGARES = {   # texto geocodificado → resultados [(lat, lng, provincia, localidad, formateada)]
    "zarate": [(-34.09, -59.03, "Buenos Aires", "Zárate", "Zárate, Buenos Aires")],
    "pilar": [(-34.45, -58.91, "Buenos Aires", "Pilar", "Pilar, Buenos Aires"),
              (-31.68, -63.88, "Córdoba", "Pilar", "Pilar, Córdoba")],
    "pilar|buenos aires": [(-34.45, -58.91, "Buenos Aires", "Pilar", "Pilar, Buenos Aires")],
    "campana": [(-34.16, -58.96, "Buenos Aires", "Campana", "Campana, Buenos Aires")],
    "belgrano 123 campana": [(-34.17, -58.95, "Buenos Aires", "Campana", "Belgrano 123, Campana")],
}
RUTAS = {(-34.45, -58.91): 63_400, (-34.16, -58.96): 14_800, (-34.17, -58.95): 21_300, (-34.30, -58.80): 50_000}


class Google:
    def __init__(self):
        self.llamadas, self.falla = [], None

    def handler(self, req: httpx.Request):
        self.llamadas.append(req.url.path)
        if self.falla:
            return httpx.Response(self.falla, json={})
        if req.url.path.endswith("/geocode/json"):
            assert req.url.params["key"] == "clave-google"
            texto = cotizacion.normalizar(req.url.params["address"].replace("Argentina", ""))
            prov = req.url.params["components"].split("administrative_area:")[-1] if "administrative_area" in req.url.params["components"] else ""
            res = next((v for k, v in sorted(LUGARES.items(), key=lambda kv: -len(kv[0]))
                        if "|" not in k and texto.startswith(k)), [])
            if prov:
                res = [r for r in res if cotizacion.normalizar(r[2]) == cotizacion.normalizar(prov)]
            if not res:
                return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})
            return httpx.Response(200, json={"status": "OK", "results": [
                {"formatted_address": f, "geometry": {"location": {"lat": la, "lng": ln}},
                 "address_components": [{"long_name": pr, "types": ["administrative_area_level_1"]},
                                        {"long_name": lo, "types": ["locality"]}]} for la, ln, pr, lo, f in res]})
        assert req.url.path.endswith("computeRoutes") and req.headers["X-Goog-Api-Key"] == "clave-google"
        cuerpo = __import__("json").loads(req.content)
        assert cuerpo["travelMode"] == "DRIVE"                                     # ruta en auto, no línea recta
        d = cuerpo["destination"]["location"]["latLng"]
        metros = RUTAS[(d["latitude"], d["longitude"])]
        return httpx.Response(200, json={"routes": [{"distanceMeters": metros, "duration": "3600s",
                                                     "description": "RN9"}]})


@pytest.fixture
def m(monkeypatch):
    monkeypatch.setattr(cotizacion, "_catalogo", lambda: CATALOGO)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "clave-google")
    rutas._origenes.clear()
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    g = Google()
    cliente = httpx.Client(transport=httpx.MockTransport(g.handler))
    q = lambda **kw: cotizacion.cotizar_piscina(db, kw.pop("modelo", "Minideck"), kw.pop("localidad", "Pilar"),
                                                cliente_http=cliente, **kw)
    yield db, g, q


def test_km_reales_por_ruta_y_tarifa_general(m):
    db, g, q = m
    r = q(provincia="Buenos Aires")
    assert r["ok"] and r["interno"]["km_ida"] == 63.4 and r["interno"]["proveedor"] == "google_routes"
    assert r["interno"]["flete_bruto"] == round(63.4 * 3000, 2)
    assert r["precio_final"] == round(2490000 + 63.4 * 3000)
    assert "computeRoutes" in g.llamadas[-1]


def test_tarifa_especial(m):
    db, g, q = m
    assert q(modelo="Arco Romano Grande Recto", provincia="Buenos Aires")["interno"]["flete_bruto"] == round(63.4 * 5000, 2)


def test_cache_evita_consultas_repetidas(m):
    db, g, q = m
    q(provincia="Buenos Aires")
    n = len(g.llamadas)
    q(provincia="Buenos Aires")
    q(modelo="Arco Romano Grande Recto", provincia="Buenos Aires")
    assert len(g.llamadas) == n
    fila = db.query(DistanciaLocalidad).one()
    assert (fila.origen_texto, fila.estado, fila.proveedor) == ("Zárate, Buenos Aires, Argentina", "CALCULADA", "google_routes")
    assert fila.destino_texto == "Pilar, Buenos Aires" and "RN9" in fila.ruta_ref and fila.actualizado_at


def test_localidad_ambigua_pide_provincia(m):
    db, g, q = m
    r = q()
    assert (r["ok"], r["motivo"], r["candidatos"]) == (False, "localidad_ambigua", ["Buenos Aires", "Córdoba"])
    assert db.query(DistanciaLocalidad).count() == 0


def test_recalculo_por_direccion_exacta(m):
    db, g, q = m
    por_localidad = q(localidad="Campana", provincia="Buenos Aires")["interno"]["km_ida"]
    por_direccion = q(localidad="Campana", provincia="Buenos Aires", direccion="Belgrano 123")["interno"]["km_ida"]
    assert (por_localidad, por_direccion) == (14.8, 21.3)
    assert {f.tipo for f in db.query(DistanciaLocalidad)} == {"LOCALIDAD", "DIRECCION"}


@pytest.mark.parametrize("status", [403, 429, 500])
def test_falla_del_proveedor_no_inventa_precio(m, status):
    db, g, q = m
    g.falla = status
    r = q(provincia="Buenos Aires")
    assert (r["ok"], r["motivo"], r["estado_proveedor"]) == (False, "distancia_no_disponible", "error")
    assert "precio_final" not in r and "verificar una persona" in r["detalle"]
    assert db.query(DistanciaLocalidad).count() == 0


def test_cambio_de_origen_recalcula(m):
    db, g, q = m
    q(provincia="Buenos Aires")
    db.add(ConfiguracionSistema(clave="fabrica_direccion", valor="Campana, Buenos Aires, Argentina"))
    db.commit()
    LUGARES["campana buenos aires"] = LUGARES["campana"]
    RUTAS[(-34.45, -58.91)] = 50_000
    try:
        r = q(provincia="Buenos Aires")
    finally:
        RUTAS[(-34.45, -58.91)] = 63_400
    assert r["interno"]["km_ida"] == 50.0
    assert db.query(DistanciaLocalidad).count() == 2                            # la del origen anterior no se usa


def test_verificacion_humana_prevalece(m):
    db, g, q = m
    cotizacion.cargar_distancia(db, "Pilar", "Buenos Aires", 58, "Medido con el camión (remito 12)", None)
    n = len(g.llamadas)
    r = q(provincia="Buenos Aires")
    assert r["interno"]["km_ida"] == 58 and r["interno"]["estado_distancia"] == "VERIFICADA"
    assert len(g.llamadas) == n


def test_sin_clave_de_google(m, monkeypatch):
    db, g, q = m
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY")
    r = q(provincia="Buenos Aires")
    assert (r["ok"], r["estado_proveedor"]) == (False, "sin_proveedor") and g.llamadas == []


@pytest.mark.parametrize("pct,flete", [(0, 190200), (50, 95100), (70, 57060), (100, 0)])
def test_promociones_de_flete_solo_sobre_el_traslado(m, pct, flete):
    from datetime import date, timedelta
    db, g, q = m
    cotizacion.crear_promocion(db, nombre=f"Flete {pct}%", valor=pct, desde=date.today(),
                               hasta=date.today() + timedelta(days=6), usuario_id=None,
                               requiere_reserva_fecha=(pct == 50))
    r = q(provincia="Buenos Aires", reserva_fecha=True)
    assert r["interno"]["flete_neto"] == pytest.approx(flete, abs=1)
    assert r["precio_final"] == round(2490000 + r["interno"]["flete_neto"])     # el producto no se toca
