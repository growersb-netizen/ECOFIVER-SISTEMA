"""
Distancias por ruta desde la fábrica (servicio centralizado de fletes).

- Origen: dirección de la fábrica configurable (fabrica_direccion; por defecto Zárate).
- Proveedor: Google Maps Platform — Geocoding API (ubicar el destino) y Routes
  API computeRoutes (km reales por ruta, en auto; nunca en línea recta).
  Clave: google_maps_api_key (panel de configuración) o GOOGLE_MAPS_API_KEY.
- Caché (distancias_localidades): origen, destino, km, proveedor, fecha, ruta y
  estado. Una distancia VERIFICADA por una persona tiene prioridad. Si cambia la
  dirección de la fábrica, lo calculado para el origen anterior no se usa.
- Localidad ambigua (mismo nombre en varias provincias, o coincidencia parcial):
  se pide la provincia; no se adivina.
- Si el proveedor falla o no está configurado: no hay distancia (y por lo tanto
  no hay precio final): se reintenta o lo verifica una persona.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from database.models import DistanciaLocalidad

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ORIGEN_DEFECTO = "Zárate, Buenos Aires, Argentina"
TIMEOUT = 10.0
_origenes: dict[str, tuple[float, float]] = {}       # geocodificación de la fábrica (por dirección)


def _norm(t: str) -> str:
    from utils.cotizacion import normalizar
    return normalizar(t)


def _config(db: Session, clave: str) -> Optional[str]:
    from utils.cotizacion import _config as c
    return c(db, clave)


def origen(db: Session) -> tuple[str, str]:
    texto = (_config(db, "fabrica_direccion") or ORIGEN_DEFECTO).strip()
    return texto, _norm(texto)


def _api_key(db: Session) -> str:
    return (_config(db, "google_maps_api_key") or os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()


def clave_destino(localidad: str, provincia: str, direccion: str, origen_clave: str) -> str:
    if direccion:
        base = "dir:" + _norm(f"{direccion} {localidad} {provincia}")
    else:
        base = "loc:" + _norm(localidad) + (f"|{_norm(provincia)}" if provincia else "")
    return f"{base}@{origen_clave}"[:300]


class ErrorProveedor(Exception):
    pass


def _geocodificar(cliente: httpx.Client, key: str, texto: str, provincia: str = "") -> list[dict]:
    comps = "country:AR" + (f"|administrative_area:{provincia}" if provincia else "")
    r = cliente.get(GEOCODE_URL, params={"address": texto, "components": comps, "region": "ar",
                                         "language": "es", "key": key})
    if r.status_code != 200:
        raise ErrorProveedor(f"Geocoding HTTP {r.status_code}")
    data = r.json()
    estado = data.get("status")
    if estado == "ZERO_RESULTS":
        return []
    if estado != "OK":
        raise ErrorProveedor(f"Geocoding: {estado}")       # REQUEST_DENIED, OVER_QUERY_LIMIT, etc.
    out = []
    for res in data.get("results", []):
        comp = {t: c.get("long_name") for c in res.get("address_components", []) for t in c.get("types", [])}
        loc = res["geometry"]["location"]
        out.append({"lat": loc["lat"], "lng": loc["lng"], "direccion": res.get("formatted_address", ""),
                    "provincia": comp.get("administrative_area_level_1", ""),
                    "localidad": comp.get("locality") or comp.get("administrative_area_level_2", ""),
                    "parcial": bool(res.get("partial_match"))})
    return out


def _ruta_km(cliente: httpx.Client, key: str, o: tuple[float, float], d: tuple[float, float]) -> tuple[float, str]:
    cuerpo = {"origin": {"location": {"latLng": {"latitude": o[0], "longitude": o[1]}}},
              "destination": {"location": {"latLng": {"latitude": d[0], "longitude": d[1]}}},
              "travelMode": "DRIVE", "routingPreference": "TRAFFIC_UNAWARE", "languageCode": "es-AR", "units": "METRIC"}
    r = cliente.post(ROUTES_URL, json=cuerpo, headers={
        "X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.description"})
    if r.status_code != 200:
        raise ErrorProveedor(f"Routes HTTP {r.status_code}")
    rutas = r.json().get("routes") or []
    if not rutas or not rutas[0].get("distanceMeters"):
        raise ErrorProveedor("Routes: sin ruta por camino")
    ruta = rutas[0]
    km = round(ruta["distanceMeters"] / 1000, 1)
    return km, f"{km} km por ruta · {ruta.get('duration', '')} · {ruta.get('description', '')}".strip(" ·")


def resolver(db: Session, localidad: str, provincia: str = "", direccion: str = "",
             cliente: Optional[httpx.Client] = None) -> dict:
    """
    {"estado": "ok", "fila": DistanciaLocalidad}
    {"estado": "ambigua", "candidatos": [provincias]}
    {"estado": "no_encontrada" | "sin_proveedor" | "error", "detalle": ...}
    """
    localidad, provincia, direccion = (localidad or "").strip(), (provincia or "").strip(), (direccion or "").strip()
    if not localidad:
        return {"estado": "no_encontrada", "detalle": "Falta la localidad"}
    origen_texto, origen_clave = origen(db)
    clave = clave_destino(localidad, provincia, direccion, origen_clave)
    fila = db.query(DistanciaLocalidad).filter_by(clave=clave).first()
    if fila:
        return {"estado": "ok", "fila": fila}
    if not provincia and not direccion:      # ¿ya hay cacheadas varias provincias con ese nombre?
        candidatas = (db.query(DistanciaLocalidad)
                      .filter(DistanciaLocalidad.clave.like(f"loc:{_norm(localidad)}|%"),
                              DistanciaLocalidad.origen_clave == origen_clave).all())
        if len(candidatas) == 1:
            return {"estado": "ok", "fila": candidatas[0]}
        if len(candidatas) > 1:
            return {"estado": "ambigua", "candidatos": sorted({c.provincia for c in candidatas})}

    key = _api_key(db)
    if not key:
        return {"estado": "sin_proveedor", "detalle": "Proveedor de rutas no configurado (google_maps_api_key)"}
    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=TIMEOUT)
    try:
        texto = ", ".join(x for x in (direccion, localidad, provincia, "Argentina") if x)
        resultados = _geocodificar(cliente, key, texto, provincia)
        if not resultados:
            return {"estado": "no_encontrada", "detalle": f"No se encontró '{texto}'"}
        provincias = sorted({r["provincia"] for r in resultados if r["provincia"]})
        if not provincia and not direccion and (len(provincias) > 1 or resultados[0]["parcial"]):
            return {"estado": "ambigua", "candidatos": provincias or [resultados[0]["direccion"]]}
        destino = resultados[0]
        if origen_clave not in _origenes:
            o = _geocodificar(cliente, key, origen_texto)
            if not o:
                return {"estado": "error", "detalle": "No se pudo ubicar la dirección de la fábrica"}
            _origenes[origen_clave] = (o[0]["lat"], o[0]["lng"])
        km, ref = _ruta_km(cliente, key, _origenes[origen_clave], (destino["lat"], destino["lng"]))
    except (ErrorProveedor, httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning(f"[Rutas] Falla del proveedor para '{localidad}': {e}")
        return {"estado": "error", "detalle": f"Falla del proveedor de rutas: {e}"}
    finally:
        if propio:
            cliente.close()
    prov_final = provincia or destino["provincia"]
    clave_final = clave_destino(localidad, prov_final, direccion, origen_clave)
    fila = db.query(DistanciaLocalidad).filter_by(clave=clave_final).first() or DistanciaLocalidad(clave=clave_final)
    fila.tipo = "DIRECCION" if direccion else "LOCALIDAD"
    fila.localidad, fila.provincia = localidad[:120], prov_final[:80]
    fila.destino_texto, fila.origen_texto, fila.origen_clave = destino["direccion"][:300], origen_texto[:300], origen_clave[:300]
    fila.km_ida, fila.proveedor, fila.ruta_ref, fila.estado = km, "google_routes", ref[:2000], "CALCULADA"
    fila.fuente = "Google Routes API (ruta en auto)"
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return {"estado": "ok", "fila": fila}
