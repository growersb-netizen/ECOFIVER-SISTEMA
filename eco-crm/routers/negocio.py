"""
Configuración del negocio — datos y variables editables.
Nombre, marca, datos fiscales, condiciones para descripciones, markup, flete y
tasas de cuotas sin interés (usadas para el cálculo de ganancia en Publicaciones ML).
Se guarda en ConfiguracionSistema (claves negocio_*).
"""
import os
from typing import Optional

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
    "negocio_nombre": "Eco Módulos & Piscinas",
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
    # Tasas (%) de costo de cuotas sin interés para el vendedor
    "negocio_cuotas_3": "9",
    "negocio_cuotas_6": "16",
    "negocio_cuotas_9": "22",
    "negocio_cuotas_12": "27",
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
        "9": float(_get(db, "negocio_cuotas_9") or 0),
        "12": float(_get(db, "negocio_cuotas_12") or 0),
    }
    return data


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
