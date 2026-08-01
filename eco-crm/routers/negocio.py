"""
Configuración del negocio — datos y variables editables.
Nombre, marca, datos fiscales, condiciones para descripciones, markup, flete y
tasas de cuotas sin interés (usadas para el cálculo de ganancia en Publicaciones ML).
Se guarda en ConfiguracionSistema (claves negocio_*).
"""
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ConfiguracionSistema, Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import _require_config_access

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")

# clave -> valor por defecto
CAMPOS = {
    "negocio_nombre": "EcoFiver",
    "negocio_apodo": "",
    "negocio_cuit": "",
    "negocio_direccion": "",
    "negocio_localidad": "",
    "negocio_telefono": "",
    "negocio_email": "",
    "negocio_web": "",
    "negocio_condiciones": "",     # texto para insertar en descripciones (garantía, envío, etc.)
    "negocio_markup": "0",         # % ganancia sugerido
    "negocio_flete_km": "3000",    # $/km de referencia
    "negocio_margen_fijo_ml": "150000",  # $ de ganancia fija que debe quedar limpia en cada venta de ML, además del contado
    # ── Costos de MercadoLibre (según simulación oficial provista) ──────────
    "negocio_ml_comision_clasificada": "13",       # % comisión con producto clasificado en catálogo ML
    "negocio_ml_comision_no_clasificada": "16.5",  # % comisión sin clasificar
    "negocio_ml_iag": "1",       # % Impuesto a los Ingresos Brutos... IAG (fijo sobre precio)
    "negocio_ml_iva": "3",       # % IVA (sobre comisión, expresado como % del precio)
    "negocio_ml_iibb": "3.5",    # % Ingresos Brutos
    # Costo (%) de financiar cuotas sin interés — "Cuota Simple" de Mercado Pago
    "negocio_cuotas_3": "7.3",
    "negocio_cuotas_6": "13.85",
}


def costo_total_rate(db: Session, cuotas: int = 0, clasificada: bool = True) -> float:
    """
    Devuelve la tasa total (como decimal, ej 0.205) que MercadoLibre descuenta de una venta:
    comisión + IAG + IVA + IIBB + costo de financiar cuotas sin interés (si aplica).
    Basado en la simulación oficial de costos de MercadoLibre.
    """
    comision = float(_get(db, "negocio_ml_comision_clasificada" if clasificada else "negocio_ml_comision_no_clasificada") or 0)
    iag = float(_get(db, "negocio_ml_iag") or 0)
    iva = float(_get(db, "negocio_ml_iva") or 0)
    iibb = float(_get(db, "negocio_ml_iibb") or 0)
    cuota_rate = 0.0
    if cuotas == 3:
        cuota_rate = float(_get(db, "negocio_cuotas_3") or 0)
    elif cuotas == 6:
        cuota_rate = float(_get(db, "negocio_cuotas_6") or 0)
    return (comision + iag + iva + iibb + cuota_rate) / 100.0


def _margen_fijo(db: Session) -> float:
    try:
        return float(_get(db, "negocio_margen_fijo_ml") or 0)
    except Exception:
        return 0.0


def precio_sugerido_ml(db: Session, precio_contado: float, cuotas: int = 0, clasificada: bool = True) -> dict:
    """
    Precio al que hay que publicar en ML (estimado, con las tasas configuradas
    a mano) para que, después de todos los costos, el neto disponible sea el
    precio de contado MÁS el margen fijo configurado (negocio_margen_fijo_ml).
    Fallback cuando no se puede consultar la tasa real de ML (sin token, sin
    categoría, etc.) — preferir siempre precio_sugerido_ml_real si hay token.
    """
    rate = costo_total_rate(db, cuotas, clasificada)
    if rate >= 1:
        rate = 0.99
    margen = _margen_fijo(db)
    objetivo = precio_contado + margen
    sugerido = objetivo / (1 - rate) if objetivo else 0
    return {
        "precio_contado": precio_contado,
        "margen_fijo": margen,
        "neto_objetivo": objetivo,
        "tasa_total_pct": round(rate * 100, 2),
        "precio_sugerido": round(sugerido, 2),
        "costo_total": round(sugerido - objetivo, 2),
        "cuotas": cuotas,
        "clasificada": clasificada,
        "fuente": "estimado",
    }


async def precio_sugerido_ml_real(db: Session, precio_contado: float, cuotas: int = 0,
                                   categoria: Optional[str] = None, listing_type: str = "gold_special") -> dict:
    """
    Igual que precio_sugerido_ml pero consultando la tasa REAL vigente de ML
    (GET /sites/MLA/listing_prices) en vez de los porcentajes cargados a mano
    en Configuración — esos pueden quedar desactualizados si ML cambia sus
    costos. Se necesita un token de ML válido; si falla, HTTPException para
    que el caller haga fallback al estimado.
    """
    from routers.mercadolibre import ML_BASE, _ml_valid_token, _ml_headers

    margen = _margen_fijo(db)
    objetivo = precio_contado + margen
    if not objetivo:
        raise HTTPException(400, "precio_contado inválido")

    token = await _ml_valid_token(db)

    async def _fee_en(precio: float) -> float:
        params = {"price": precio, "listing_type_id": listing_type}
        if categoria:
            params["category_id"] = categoria
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(f"{ML_BASE}/sites/MLA/listing_prices", params=params, headers=_ml_headers(token))
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"ML no devolvió el costo: {r.text[:200]}")
        data = r.json()
        entry = data[0] if isinstance(data, list) else data
        fee = entry.get("sale_fee_amount")
        if fee is None:
            raise HTTPException(502, "ML no devolvió sale_fee_amount")
        return float(fee)

    # 1er paso: estimar con una tasa aproximada, calcular la tasa real a ese precio
    guess = objetivo / (1 - costo_total_rate(db, 0, True))
    fee_guess = await _fee_en(guess)
    rate_real = fee_guess / guess if guess else 0

    cuota_rate = 0.0
    if cuotas == 3:
        cuota_rate = float(_get(db, "negocio_cuotas_3") or 0) / 100.0
    elif cuotas == 6:
        cuota_rate = float(_get(db, "negocio_cuotas_6") or 0) / 100.0
    rate_total = min(rate_real + cuota_rate, 0.95)

    sugerido = objetivo / (1 - rate_total)

    # 2do paso: verificar contra el precio final (la tasa puede variar levemente entre tramos de precio)
    fee_final = await _fee_en(sugerido)
    neto_final = sugerido - fee_final - (sugerido * cuota_rate)
    diferencia = objetivo - neto_final
    if abs(diferencia) > 500:
        sugerido += diferencia  # ajuste fino

    return {
        "precio_contado": precio_contado,
        "margen_fijo": margen,
        "neto_objetivo": objetivo,
        "tasa_total_pct": round(rate_total * 100, 2),
        "precio_sugerido": round(sugerido, 2),
        "costo_total": round(sugerido - objetivo, 2),
        "cuotas": cuotas,
        "categoria": categoria,
        "listing_type": listing_type,
        "fuente": "real_ml",
    }


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO", "ADMINISTRACION")))
    if not ok:
        raise HTTPException(403, "Sin permisos")


def _get(db: Session, clave: str) -> str:
    e = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if e and e.valor is not None:
        return e.valor
    return CAMPOS.get(clave, "")


def _set(db: Session, clave: str, valor: str):
    e = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if e:
        e.valor = valor
        e.estado = "activa" if valor else "sin_configurar"
    else:
        db.add(ConfiguracionSistema(clave=clave, valor=valor, es_secreto=False,
                                    estado="activa" if valor else "sin_configurar"))
    db.commit()


@router.get("/negocio", response_class=HTMLResponse)
async def negocio_page(request: Request, current_user: Usuario = Depends(_require_config_access)):
    return templates.TemplateResponse("negocio.html", {
        "request": request, "user": current_user, "roles": get_user_roles(current_user),
    })


@router.get("/api/negocio/config")
async def get_config(db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
                     current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    data = {k: _get(db, k) for k in CAMPOS}
    # Tasas de cuotas como dict numérico listo para usar
    data["cuotas_rates"] = {
        "3": float(_get(db, "negocio_cuotas_3") or 0),
        "6": float(_get(db, "negocio_cuotas_6") or 0),
    }
    return data


@router.get("/api/negocio/precio-sugerido-ml")
async def api_precio_sugerido(precio_contado: float, cuotas: int = 0, clasificada: bool = True,
                              categoria: Optional[str] = None, listing_type: str = "gold_special",
                              db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
                              current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Precio de publicación sugerido en ML para que quede neto el precio de
    contado + el margen fijo configurado. Intenta con la tasa REAL vigente de
    ML (necesita cuenta conectada); si no se puede, usa el estimado con las
    tasas cargadas a mano en Configuración del negocio.
    """
    _auth(x_api_key, current_user)
    try:
        return await precio_sugerido_ml_real(db, precio_contado, cuotas, categoria, listing_type)
    except Exception:
        return precio_sugerido_ml(db, precio_contado, cuotas, clasificada)


@router.post("/api/negocio/config")
async def save_config(request: Request, db: Session = Depends(get_db),
                      x_api_key: Optional[str] = Header(None),
                      current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    data = await request.json()
    guardados = 0
    for k in CAMPOS:
        if k in data:
            _set(db, k, str(data[k]).strip())
            guardados += 1
    return {"ok": True, "guardados": guardados}
