"""
Configuración del perfil de WhatsApp Business — EcoFiver.
Permite editar el "about", descripción, dirección, email, sitios web y rubro
del número de WhatsApp Business vía la API de Meta (WhatsApp Business Profile).

IMPORTANTE — limitación real de Meta (no es limitación nuestra):
El NOMBRE VISIBLE del WhatsApp Business (el que aparece arriba del chat) NO se
puede cambiar con un simple llamado a la API. Meta exige una solicitud de
verificación de nombre ("Display Name") que revisan manualmente y puede tardar
días. Esta pantalla muestra el nombre actual (solo lectura) y explica cómo
pedir el cambio desde Meta Business Suite.
"""
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import _require_config_access

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")
META_API_BASE = "https://graph.facebook.com/v19.0"

VERTICALS = [
    ("RETAIL", "Comercio minorista"),
    ("PROF_SERVICES", "Servicios profesionales"),
    ("HOTEL", "Hotelería"),
    ("CONSTRUCTION", "Construcción / Inmobiliaria"),
    ("OTHER", "Otro"),
]


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")


def _creds():
    token = os.getenv("WA_TOKEN", "")
    phone_id = os.getenv("WA_PHONE_ID", "")
    if not token or not phone_id:
        raise HTTPException(400, "WhatsApp no está configurado (falta WA_TOKEN / WA_PHONE_ID)")
    return token, phone_id


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@router.get("/whatsapp-business", response_class=HTMLResponse)
async def whatsapp_business_page(request: Request, current_user: Usuario = Depends(_require_config_access)):
    return templates.TemplateResponse("whatsapp_business.html", {
        "request": request, "user": current_user, "roles": get_user_roles(current_user),
        "verticals": VERTICALS,
    })


@router.get("/api/whatsapp/perfil")
async def get_perfil(db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None),
                     current_user: Optional[Usuario] = Depends(get_current_user)):
    """Trae el perfil actual de WhatsApp Business (about, descripción, dirección, etc.)."""
    _auth(x_api_key, current_user)
    token, phone_id = _creds()
    async with httpx.AsyncClient(timeout=15) as c:
        rp = await c.get(f"{META_API_BASE}/{phone_id}/whatsapp_business_profile",
                         params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
                         headers=_headers(token))
        rn = await c.get(f"{META_API_BASE}/{phone_id}",
                         params={"fields": "display_phone_number,verified_name,quality_rating"},
                         headers=_headers(token))
    if rp.status_code != 200:
        raise HTTPException(rp.status_code, f"Meta rechazó la consulta: {rp.text[:300]}")
    perfil = (rp.json().get("data") or [{}])[0]
    numero = rn.json() if rn.status_code == 200 else {}
    return {
        "ok": True,
        "perfil": {
            "about": perfil.get("about", ""),
            "description": perfil.get("description", ""),
            "address": perfil.get("address", ""),
            "email": perfil.get("email", ""),
            "websites": perfil.get("websites", []),
            "vertical": perfil.get("vertical", ""),
            "profile_picture_url": perfil.get("profile_picture_url", ""),
        },
        "numero": {
            "display_phone_number": numero.get("display_phone_number", ""),
            "verified_name": numero.get("verified_name", ""),
            "quality_rating": numero.get("quality_rating", ""),
        },
    }


@router.put("/api/whatsapp/perfil")
async def actualizar_perfil(request: Request, x_api_key: Optional[str] = Header(None),
                            current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Actualiza el perfil de WhatsApp Business.
    Body: { about, description, address, email, websites: [..], vertical }
    """
    _auth(x_api_key, current_user)
    token, phone_id = _creds()
    data = await request.json()

    payload = {"messaging_product": "whatsapp"}
    if "about" in data:
        payload["about"] = (data["about"] or "")[:139]
    if "description" in data:
        payload["description"] = (data["description"] or "")[:512]
    if "address" in data:
        payload["address"] = (data["address"] or "")[:256]
    if "email" in data:
        payload["email"] = (data["email"] or "")[:128]
    if "vertical" in data and data["vertical"]:
        payload["vertical"] = data["vertical"]
    if "websites" in data:
        sitios = [w.strip() for w in (data["websites"] or []) if w and w.strip()][:2]
        payload["websites"] = sitios

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{META_API_BASE}/{phone_id}/whatsapp_business_profile",
                         json=payload, headers=_headers(token))
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Meta rechazó la actualización: {r.text[:300]}")
    return {"ok": True}


@router.post("/api/whatsapp/foto-perfil")
async def subir_foto_perfil(file: UploadFile = File(...), x_api_key: Optional[str] = Header(None),
                            current_user: Optional[Usuario] = Depends(get_current_user)):
    """Sube y aplica una nueva foto de perfil de WhatsApp Business."""
    _auth(x_api_key, current_user)
    token, phone_id = _creds()
    content = await file.read()

    async with httpx.AsyncClient(timeout=40) as c:
        # 1) Subir la imagen como media
        r_media = await c.post(
            f"{META_API_BASE}/{phone_id}/media",
            headers=_headers(token),
            data={"messaging_product": "whatsapp"},
            files={"file": (file.filename or "foto.jpg", content, file.content_type or "image/jpeg")},
        )
        if r_media.status_code != 200:
            raise HTTPException(r_media.status_code, f"No se pudo subir la imagen: {r_media.text[:300]}")
        handle = r_media.json().get("id")

        # 2) Aplicarla como foto de perfil
        r_perfil = await c.post(
            f"{META_API_BASE}/{phone_id}/whatsapp_business_profile",
            headers=_headers(token),
            json={"messaging_product": "whatsapp", "profile_picture_handle": handle},
        )
    if r_perfil.status_code != 200:
        raise HTTPException(r_perfil.status_code, f"No se pudo aplicar la foto: {r_perfil.text[:300]}")
    return {"ok": True}
