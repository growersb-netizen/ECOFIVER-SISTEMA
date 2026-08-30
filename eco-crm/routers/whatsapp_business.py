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
META_API_BASE = "https://graph.facebook.com/v22.0"

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
        err_body = {}
        try:
            err_body = rp.json()
        except Exception:
            pass
        code = (err_body.get("error") or {}).get("code", 0)
        if code == 190:
            return {
                "ok": False,
                "error_code": 190,
                "detail": (
                    "El token WA_TOKEN ya no es válido porque la App de Meta fue eliminada o el token expiró. "
                    "Para solucionarlo: 1) Accedé a business.facebook.com → WhatsApp Accounts → tu número "
                    "→ Configuración de API y generá un token nuevo. 2) Actualizá WA_TOKEN en Railway con el nuevo valor."
                ),
            }
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
    """
    Sube y aplica una nueva foto de perfil de WhatsApp Business.

    Flujo correcto según Meta:
      1) Crear sesión de upload (Graph Upload API): POST /v22.0/app/uploads
      2) Subir binario a la sesión:              POST /v22.0/{session_id}
         → retorna un handle con prefijo "h:"
      3) Aplicar el handle al perfil:            POST /{phone_id}/whatsapp_business_profile
         con { profile_picture_handle: "h:..." }
    """
    _auth(x_api_key, current_user)
    token, phone_id = _creds()
    content = await file.read()
    file_type = file.content_type or "image/jpeg"
    file_name = file.filename or "foto.jpg"

    async with httpx.AsyncClient(timeout=60) as c:
        # 1) Crear sesión de upload
        r_session = await c.post(
            "https://graph.facebook.com/v22.0/app/uploads",
            headers=_headers(token),
            params={
                "file_length": len(content),
                "file_type": file_type,
                "file_name": file_name,
            },
        )
        if r_session.status_code != 200:
            raise HTTPException(
                r_session.status_code,
                f"No se pudo crear sesión de upload: {r_session.text[:300]}"
            )
        session_id = r_session.json().get("id")
        if not session_id:
            raise HTTPException(500, f"Meta no devolvió session id: {r_session.text[:200]}")

        # 2) Subir el binario a la sesión
        r_upload = await c.post(
            f"https://graph.facebook.com/v22.0/{session_id}",
            headers={
                **_headers(token),
                "file_offset": "0",
                "Content-Type": "application/octet-stream",
            },
            content=content,
        )
        if r_upload.status_code != 200:
            raise HTTPException(
                r_upload.status_code,
                f"No se pudo subir el archivo: {r_upload.text[:300]}"
            )
        handle = r_upload.json().get("h")
        if not handle:
            raise HTTPException(500, f"Meta no devolvió handle: {r_upload.text[:200]}")

        # 3) Aplicar el handle como foto de perfil
        r_perfil = await c.post(
            f"{META_API_BASE}/{phone_id}/whatsapp_business_profile",
            headers=_headers(token),
            json={"messaging_product": "whatsapp", "profile_picture_handle": handle},
        )
    if r_perfil.status_code != 200:
        raise HTTPException(r_perfil.status_code, f"No se pudo aplicar la foto: {r_perfil.text[:300]}")
    return {"ok": True, "handle": handle}


@router.post("/api/whatsapp/portada")
async def subir_portada(file: UploadFile = File(...), x_api_key: Optional[str] = Header(None),
                        current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Sube y aplica la imagen de portada (cover) de WhatsApp Business.

    Mismo flujo de Graph Upload API que la foto de perfil, pero usando
    el campo 'cover_photo_handle' en whatsapp_business_profile.
    """
    _auth(x_api_key, current_user)
    token, phone_id = _creds()
    content = await file.read()
    file_type = file.content_type or "image/jpeg"
    file_name = file.filename or "portada.jpg"

    async with httpx.AsyncClient(timeout=60) as c:
        # 1) Crear sesión de upload
        r_session = await c.post(
            "https://graph.facebook.com/v22.0/app/uploads",
            headers=_headers(token),
            params={
                "file_length": len(content),
                "file_type": file_type,
                "file_name": file_name,
            },
        )
        if r_session.status_code != 200:
            raise HTTPException(
                r_session.status_code,
                f"No se pudo crear sesión de upload: {r_session.text[:300]}"
            )
        session_id = r_session.json().get("id")
        if not session_id:
            raise HTTPException(500, f"Meta no devolvió session id: {r_session.text[:200]}")

        # 2) Subir el binario
        r_upload = await c.post(
            f"https://graph.facebook.com/v22.0/{session_id}",
            headers={
                **_headers(token),
                "file_offset": "0",
                "Content-Type": "application/octet-stream",
            },
            content=content,
        )
        if r_upload.status_code != 200:
            raise HTTPException(
                r_upload.status_code,
                f"No se pudo subir el archivo: {r_upload.text[:300]}"
            )
        handle = r_upload.json().get("h")
        if not handle:
            raise HTTPException(500, f"Meta no devolvió handle: {r_upload.text[:200]}")

        # 3) Aplicar como portada/cover
        r_portada = await c.post(
            f"{META_API_BASE}/{phone_id}/whatsapp_business_profile",
            headers=_headers(token),
            json={"messaging_product": "whatsapp", "cover_photo_handle": handle},
        )
    if r_portada.status_code != 200:
        raise HTTPException(r_portada.status_code, f"No se pudo aplicar la portada: {r_portada.text[:300]}")
    return {"ok": True, "handle": handle}


@router.post("/api/whatsapp/audit/cambiar-nombre")
async def cambiar_nombre_wa(
    request: Request,
    t: str = "",
    phone_id_override: str = "",
):
    """
    Envía solicitud de cambio de nombre de WhatsApp Business a Meta.
    Meta revisa la solicitud (puede tardar minutos u horas).
    """
    import os as _os
    expected = _os.getenv("ML_AUDIT_TOKEN", "eco-audit-2026")
    if t != expected:
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    nuevo_nombre = (body.get("nuevo_nombre") or "").strip()
    if not nuevo_nombre:
        raise HTTPException(400, "Falta 'nuevo_nombre' en el body")

    token = _os.getenv("WA_TOKEN", "")
    phone_id = phone_id_override or _os.getenv("WA_PHONE_ID", "")
    if not token or not phone_id:
        raise HTTPException(400, "Faltan WA_TOKEN / WA_PHONE_ID en las variables de entorno")

    # 1) Leer nombre actual
    async with httpx.AsyncClient(timeout=15) as c:
        rn = await c.get(
            f"{META_API_BASE}/{phone_id}",
            params={"fields": "display_phone_number,verified_name,name_status"},
            headers=_headers(token),
        )
    nombre_actual = rn.json().get("verified_name", "?") if rn.status_code == 200 else "?"
    name_status = rn.json().get("name_status", "?") if rn.status_code == 200 else "?"

    # 2) Enviar solicitud de cambio de nombre
    async with httpx.AsyncClient(timeout=15) as c:
        rc = await c.post(
            f"{META_API_BASE}/{phone_id}",
            headers=_headers(token),
            json={"new_name": nuevo_nombre},
        )

    ok = rc.status_code in (200, 201)
    return {
        "ok": ok,
        "nombre_anterior": nombre_actual,
        "name_status_anterior": name_status,
        "nuevo_nombre_solicitado": nuevo_nombre,
        "http": rc.status_code,
        "respuesta_meta": rc.json() if rc.content else {},
    }
