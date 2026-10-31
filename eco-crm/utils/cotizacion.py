"""
Cotización de piscinas de contado (reglas comerciales del propietario).

- Precio del producto: catálogo vigente (nunca histórico).
- Traslado desde Zárate: km de ida × tarifa. General $3.000/km; modelos
  especiales $5.000/km. Tarifas configurables (ConfiguracionSistema):
  negocio_flete_km, flete_km_especial, flete_modelos_especiales. Sin config,
  los valores vigentes en el código.
- Distancias: servicio de rutas (utils/rutas.py, Google Routes, km reales por
  ruta, con caché). Si falla o no está configurado, no hay precio final.
- Promociones: solo las de promociones_comerciales vigentes y autorizadas.
  FLETE_PCT descuenta un % del traslado si el cliente reserva la fecha de
  instalación durante la vigencia (sin seña: sigue siendo pago contra entrega).
- Al cliente: UN precio final (producto + traslado neto). Internamente se
  conserva el desglose para que la comisión se calcule sobre el producto.
- Autoportantes: no se ofrecen de más de 4,10 m.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DistanciaLocalidad, PromocionComercial
from utils.motor_tareas import ErrorMotor

TARIFA_BASE_DEFECTO = 3000
TARIFA_ESPECIAL_DEFECTO = 5000
MODELOS_ESPECIALES_DEFECTO = ("Arco Romano Grande", "Playa y Abanico")
LARGO_MAX_AUTOPORTANTE = 4.10
INCLUYE = ["piscina", "traslado", "instalación", "equipo de filtrado completo"]
INCLUYE_ENTERRADA = ["excavación necesaria", "obra completa de instalación"]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def clave_localidad(localidad: str, provincia: str = "") -> str:
    return normalizar(localidad) + (f"|{normalizar(provincia)}" if provincia else "")


def _config(db: Session, clave: str) -> Optional[str]:
    try:
        from routers.configuracion import get_config_value
        return get_config_value(clave, db)
    except Exception:
        return None


def tarifas(db: Session) -> dict:
    def num(clave, defecto):
        try:
            return float(_config(db, clave) or defecto)
        except ValueError:
            return float(defecto)
    especiales = _config(db, "flete_modelos_especiales")
    lista = [m.strip() for m in especiales.split(",")] if especiales else list(MODELOS_ESPECIALES_DEFECTO)
    base = _config(db, "flete_precio_km") or _config(db, "negocio_flete_km") or TARIFA_BASE_DEFECTO
    try:
        base = float(base)
    except ValueError:
        base = float(TARIFA_BASE_DEFECTO)
    return {"base_km": base,
            "especial_km": num("flete_km_especial", TARIFA_ESPECIAL_DEFECTO),
            "modelos_especiales": [m for m in lista if m]}


def tarifa_km(t: dict, modelo: str) -> float:
    m = normalizar(modelo)
    return t["especial_km"] if any(m.startswith(normalizar(e)) for e in t["modelos_especiales"]) else t["base_km"]


def es_autoportante(modelo: str) -> bool:
    return "portante" in normalizar(modelo)


def promocion_vigente(db: Session, producto: str, hoy: date) -> Optional[PromocionComercial]:
    return (db.query(PromocionComercial)
            .filter(PromocionComercial.activa == True, PromocionComercial.tipo == "FLETE_PCT",  # noqa: E712
                    PromocionComercial.producto == producto, PromocionComercial.desde <= hoy,
                    PromocionComercial.hasta >= hoy)
            .order_by(PromocionComercial.valor.desc()).first())


def _catalogo():
    from routers.catalogo import load_catalogo
    return load_catalogo()


def cotizar_piscina(db: Session, modelo: str, localidad: str, provincia: str = "",
                    reserva_fecha: bool = False, hoy: Optional[date] = None, direccion: str = "",
                    cliente_http=None) -> dict:
    """Cotización del servidor. ok=False con motivo cuando no se puede cotizar sin inventar."""
    hoy = hoy or date.today()
    cat = _catalogo()
    precios = cat.get("piscinas", {}).get("precios", {})
    medidas = cat.get("piscinas", {}).get("medidas", {})
    if modelo not in precios:
        return {"ok": False, "motivo": "modelo_sin_precio", "detalle": f"'{modelo}' no tiene precio vigente en el catálogo"}
    largo = (medidas.get(modelo) or {}).get("largo_m")
    if es_autoportante(modelo) and largo and float(largo) > LARGO_MAX_AUTOPORTANTE:
        return {"ok": False, "motivo": "autoportante_fuera_de_rango",
                "detalle": f"No se ofrecen autoportantes de más de {LARGO_MAX_AUTOPORTANTE} m"}
    from utils.rutas import resolver
    r = resolver(db, localidad, provincia, direccion, cliente_http)
    if r["estado"] == "ambigua":
        return {"ok": False, "motivo": "localidad_ambigua", "candidatos": r["candidatos"],
                "detalle": f"'{localidad}' existe en más de una provincia: indicar provincia"}
    if r["estado"] != "ok":
        return {"ok": False, "motivo": "distancia_no_disponible", "estado_proveedor": r["estado"],
                "detalle": r.get("detalle", "") + " — no se puede dar un precio final: reintentar o verificar una persona"}
    d = r["fila"]
    t = tarifas(db)
    precio_producto = float(precios[modelo])
    km = float(d.km_ida)
    tkm = tarifa_km(t, modelo)
    flete_bruto = round(km * tkm, 2)
    promo = promocion_vigente(db, "PISCINA", hoy)
    aplica = bool(promo) and (reserva_fecha or not promo.requiere_reserva_fecha)
    descuento = round(flete_bruto * promo.valor / 100, 2) if aplica else 0.0
    flete_neto = round(flete_bruto - descuento, 2)
    enterrada = not es_autoportante(modelo) and float((medidas.get(modelo) or {}).get("profundidad_max_m") or 0) >= 1.0
    out = {
        "ok": True, "modelo": modelo, "localidad": d.localidad,
        "precio_final": round(precio_producto + flete_neto),
        "incluye": INCLUYE + (INCLUYE_ENTERRADA if enterrada else []),
        "pago": "contra entrega, en domicilio",
        "interno": {"precio_producto": precio_producto, "km_ida": km, "tarifa_km": tkm, "flete_bruto": flete_bruto,
                    "descuento_flete": descuento, "flete_neto": flete_neto,
                    "promocion_id": promo.id if aplica else None, "fuente_distancia": d.fuente,
                    "proveedor": d.proveedor, "estado_distancia": d.estado, "ruta": d.ruta_ref,
                    "destino": d.destino_texto or d.localidad},
    }
    if promo and not aplica:
        out["promocion_disponible"] = {
            "nombre": promo.nombre, "condicion": "reservar la fecha de instalación durante la promoción",
            "hasta": promo.hasta.isoformat(),
            "precio_final_con_promocion": round(precio_producto + flete_bruto - round(flete_bruto * promo.valor / 100, 2))}
    return out


def cargar_distancia(db: Session, localidad: str, provincia: str, km_ida: float, fuente: str,
                     usuario_id: Optional[int], direccion: str = "") -> DistanciaLocalidad:
    """Verificación humana: fija (o corrige) la distancia para el origen actual. Prevalece sobre la calculada."""
    from utils.rutas import clave_destino, origen
    if not (localidad or "").strip():
        raise ErrorMotor("Falta la localidad")
    if km_ida is None or not (0 <= float(km_ida) <= 3000):
        raise ErrorMotor("Kilómetros inválidos")
    if len((fuente or "").strip()) < 3:
        raise ErrorMotor("Indicá la fuente de la distancia (verificable)")
    origen_texto, origen_clave = origen(db)
    clave = clave_destino(localidad, provincia, direccion, origen_clave)
    fila = db.query(DistanciaLocalidad).filter_by(clave=clave).first() or DistanciaLocalidad(clave=clave)
    fila.tipo = "DIRECCION" if direccion else "LOCALIDAD"
    fila.localidad, fila.provincia, fila.km_ida = localidad.strip()[:120], (provincia or "").strip()[:80], float(km_ida)
    fila.destino_texto = (direccion or fila.destino_texto or "")[:300]
    fila.origen_texto, fila.origen_clave = origen_texto[:300], origen_clave[:300]
    fila.proveedor, fila.estado, fila.fuente, fila.cargado_por_id = "manual", "VERIFICADA", fuente.strip()[:200], usuario_id
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def crear_promocion(db: Session, *, nombre: str, valor: float, desde: date, hasta: date, usuario_id: int,
                    producto: str = "PISCINA", requiere_reserva_fecha: bool = True, nota: str = "") -> PromocionComercial:
    if not (0 <= float(valor) <= 100):
        raise ErrorMotor("El porcentaje debe estar entre 0 y 100 (se aplica solo al traslado)")
    if hasta < desde:
        raise ErrorMotor("La promoción termina antes de empezar")
    if len((nombre or "").strip()) < 3:
        raise ErrorMotor("Poné un nombre a la promoción")
    p = PromocionComercial(nombre=nombre.strip()[:150], tipo="FLETE_PCT", valor=float(valor), producto=producto,
                           desde=desde, hasta=hasta, requiere_reserva_fecha=requiere_reserva_fecha, activa=True,
                           autorizada_por_id=usuario_id, nota=(nota or "")[:2000])
    db.add(p)
    db.commit()
    db.refresh(p)
    return p
