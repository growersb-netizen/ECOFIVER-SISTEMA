"""
web_cms.py — Módulo Web CMS del CRM
Permite gestionar el contenido de la web (módulos, piscinas, galería, testimonios,
financiación, config y blog) directamente desde el CRM, usando la API del sitio web.
"""
import os
import logging
import httpx
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from routers.auth import get_current_user, get_user_roles
from database.models import Usuario

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")

WEB_BASE_URL = os.getenv("WEB_BASE_URL", "https://www.ecomodulosypiscinas.com.ar")
WEB_API_KEY  = os.getenv("WEB_API_KEY", "eco-crm-api-key-2024")

HEADERS = {"x-api-key": WEB_API_KEY, "Content-Type": "application/json"}
TIMEOUT = 15.0


def _web_headers(content_type: str = "application/json") -> dict:
    return {"x-api-key": WEB_API_KEY, "Content-Type": content_type}


# ─── PAGE ─────────────────────────────────────────────────────────────────────

@router.get("/web", response_class=HTMLResponse)
async def web_cms_page(
    request: Request,
    tab: Optional[str] = "modulos",
    current_user: Usuario = Depends(get_current_user),
):
    roles = get_user_roles(current_user) if current_user else []
    if "ADMIN" not in roles and "COORDINADOR_OPERATIVO" not in roles:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("web_cms.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "initial_tab": tab,
        "web_base_url": WEB_BASE_URL,
    })


# ─── PROXY: MÓDULOS ───────────────────────────────────────────────────────────

@router.get("/api/web/modulos")
async def proxy_get_modulos(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/modulos", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/modulos/{item_id}")
async def proxy_put_modulo(item_id: str, request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/modulos/{item_id}", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: PISCINAS ──────────────────────────────────────────────────────────

@router.get("/api/web/piscinas")
async def proxy_get_piscinas(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/piscinas", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/piscinas/{item_id}")
async def proxy_put_piscina(item_id: str, request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/piscinas/{item_id}", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: OBRAS / GALERÍA ───────────────────────────────────────────────────

@router.get("/api/web/obras")
async def proxy_get_obras(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/obras", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.post("/api/web/obras")
async def proxy_post_obra(request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{WEB_BASE_URL}/api/admin/obras", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/obras/{item_id}")
async def proxy_put_obra(item_id: str, request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/obras/{item_id}", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.delete("/api/web/obras/{item_id}")
async def proxy_delete_obra(item_id: str, current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.delete(f"{WEB_BASE_URL}/api/admin/obras/{item_id}", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: TESTIMONIOS ───────────────────────────────────────────────────────

@router.get("/api/web/testimonios")
async def proxy_get_testimonios(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/testimonios", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.post("/api/web/testimonios")
async def proxy_post_testimonio(request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{WEB_BASE_URL}/api/admin/testimonios", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/testimonios/{item_id}")
async def proxy_put_testimonio(item_id: str, request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/testimonios/{item_id}", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.delete("/api/web/testimonios/{item_id}")
async def proxy_delete_testimonio(item_id: str, current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.delete(f"{WEB_BASE_URL}/api/admin/testimonios/{item_id}", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: COEFICIENTES ──────────────────────────────────────────────────────

@router.get("/api/web/coeficientes")
async def proxy_get_coeficientes(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/coeficientes", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/coeficientes")
async def proxy_put_coeficientes(request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/coeficientes", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: CONFIG SITIO ──────────────────────────────────────────────────────

@router.get("/api/web/config")
async def proxy_get_config(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/config", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/config")
async def proxy_put_config(request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/config", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: BLOG ──────────────────────────────────────────────────────────────

@router.get("/api/web/blog")
async def proxy_get_blog(current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{WEB_BASE_URL}/api/admin/blog", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.post("/api/web/blog")
async def proxy_post_blog(request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{WEB_BASE_URL}/api/admin/blog", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.put("/api/web/blog/{item_id}")
async def proxy_put_blog(item_id: str, request: Request, current_user: Usuario = Depends(get_current_user)):
    body = await request.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.put(f"{WEB_BASE_URL}/api/admin/blog/{item_id}", json=body, headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


@router.delete("/api/web/blog/{item_id}")
async def proxy_delete_blog(item_id: str, current_user: Usuario = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.delete(f"{WEB_BASE_URL}/api/admin/blog/{item_id}", headers=HEADERS)
    return JSONResponse(content=r.json(), status_code=r.status_code)


# ─── PROXY: UPLOAD IMAGEN ─────────────────────────────────────────────────────

@router.post("/api/web/upload")
async def proxy_upload(
    file: UploadFile = File(...),
    current_user: Usuario = Depends(get_current_user),
):
    """Sube la imagen a R2 a través de la API del sitio web."""
    content = await file.read()
    files = {"file": (file.filename, content, file.content_type)}
    # Multipart: sin Content-Type header manual (httpx lo genera solo con files=)
    h = {"x-api-key": WEB_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{WEB_BASE_URL}/api/admin/upload", headers=h, files=files)
    return JSONResponse(content=r.json(), status_code=r.status_code)
