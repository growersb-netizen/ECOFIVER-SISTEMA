"""
MercadoLibre — Publicaciones (cola de borradores unificada).
Carga manual / masiva / desde catálogo → cola de borradores → publicar en lote a ML.
Incluye semáforo de competitividad (precio de referencia manual + auto buy-box de catálogo).
Reutiliza el OAuth/token del módulo mercadolibre.
"""
import json
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import BorradorML, Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import _require_config_access
from routers.mercadolibre import (
    _ml_valid_token, _ml_headers, ML_BASE, ML_CATEGORIAS, API_KEY,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/mercadolibre/publicaciones", response_class=HTMLResponse)
async def pagina_publicaciones(request: Request, current_user: Usuario = Depends(_require_config_access)):
    return templates.TemplateResponse("ml_publicaciones.html", {
        "request": request, "user": current_user, "roles": get_user_roles(current_user),
    })


def _auth(x_api_key, current_user):
    ok = (x_api_key and x_api_key == API_KEY) or (
        current_user and any(r in get_user_roles(current_user) for r in ("ADMIN", "COORDINADOR_OPERATIVO")))
    if not ok:
        raise HTTPException(403, "Sin permisos")


def _dict(b: BorradorML) -> dict:
    try:
        fotos = json.loads(b.fotos_json or "[]")
    except Exception:
        fotos = []
    ref = b.precio_competencia if b.precio_competencia else b.precio_referencia
    semaforo = None
    if ref and b.precio:
        if b.precio < ref:
            semaforo = "rompes"
        elif b.precio <= ref * 1.05:
            semaforo = "en_linea"
        else:
            semaforo = "caro"
    return {
        "id": b.id, "origen": b.origen, "titulo": b.titulo, "descripcion": b.descripcion or "",
        "categoria": b.categoria or "", "producto": b.producto or "", "precio": b.precio or 0,
        "cantidad": b.cantidad or 1, "condicion": b.condicion or "new",
        "listing_type": b.listing_type or "gold_special", "fotos": fotos,
        "precio_referencia": b.precio_referencia, "precio_competencia": b.precio_competencia,
        "referencia_usada": ref, "semaforo": semaforo,
        "estado": b.estado, "item_id": b.item_id, "permalink": b.permalink,
        "error_msg": b.error_msg or "", "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@router.get("/api/ml/borradores")
async def listar(estado: Optional[str] = None, db: Session = Depends(get_db),
                 x_api_key: Optional[str] = Header(None),
                 current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    q = db.query(BorradorML)
    if estado:
        q = q.filter(BorradorML.estado == estado)
    items = q.order_by(BorradorML.id.desc()).all()
    return {"total": len(items), "borradores": [_dict(b) for b in items]}


@router.post("/api/ml/borradores")
async def crear(request: Request, db: Session = Depends(get_db),
                x_api_key: Optional[str] = Header(None),
                current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    d = await request.json()
    if not (d.get("titulo") or "").strip():
        raise HTTPException(400, "El título es obligatorio")
    b = BorradorML(
        origen=d.get("origen", "manual"),
        titulo=(d.get("titulo") or "").strip()[:60],
        descripcion=d.get("descripcion", ""),
        categoria=(d.get("categoria") or "").strip(),
        producto=(d.get("producto") or "").strip().upper() or None,
        precio=float(d.get("precio") or 0),
        cantidad=int(d.get("cantidad") or 1),
        condicion=d.get("condicion", "new"),
        listing_type=d.get("listing_type", "gold_special"),
        fotos_json=json.dumps(d.get("fotos") or []),
        atributos_json=json.dumps(d.get("atributos") or []),
        precio_referencia=(float(d["precio_referencia"]) if d.get("precio_referencia") else None),
        created_by_id=current_user.id if current_user else None,
    )
    db.add(b); db.commit(); db.refresh(b)
    return {"ok": True, **_dict(b)}


@router.put("/api/ml/borradores/{bid}")
async def editar(bid: int, request: Request, db: Session = Depends(get_db),
                 x_api_key: Optional[str] = Header(None),
                 current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")
    d = await request.json()
    if "titulo" in d:
        b.titulo = (d["titulo"] or "").strip()[:60]
    for f in ("descripcion", "categoria", "condicion", "listing_type"):
        if f in d:
            setattr(b, f, d[f])
    if "producto" in d:
        b.producto = (d["producto"] or "").strip().upper() or None
    if "precio" in d:
        b.precio = float(d["precio"] or 0)
    if "cantidad" in d:
        b.cantidad = int(d["cantidad"] or 1)
    if "fotos" in d:
        b.fotos_json = json.dumps(d["fotos"] or [])
    if "atributos" in d:
        b.atributos_json = json.dumps(d["atributos"] or [])
    if "precio_referencia" in d:
        b.precio_referencia = float(d["precio_referencia"]) if d["precio_referencia"] else None
    db.commit(); db.refresh(b)
    return {"ok": True, **_dict(b)}


@router.delete("/api/ml/borradores/{bid}")
async def borrar(bid: int, db: Session = Depends(get_db),
                 x_api_key: Optional[str] = Header(None),
                 current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")
    db.delete(b); db.commit()
    return {"ok": True}


async def _competencia_precio(db: Session, q: str) -> Optional[float]:
    """Precio de referencia automático via API de catálogo (buy-box), si ML lo permite."""
    try:
        tok = await _ml_valid_token(db)
        async with httpx.AsyncClient(timeout=15) as c:
            rc = await c.get(f"{ML_BASE}/products/search",
                             params={"site_id": "MLA", "status": "active", "q": q},
                             headers=_ml_headers(tok))
            if rc.status_code != 200:
                return None
            precios = []
            for p in rc.json().get("results", [])[:5]:
                rp = await c.get(f"{ML_BASE}/products/{p.get('id')}", headers=_ml_headers(tok))
                if rp.status_code == 200:
                    pw = (rp.json().get("buy_box_winner") or {}).get("price")
                    if pw:
                        precios.append(pw)
            return min(precios) if precios else None
    except Exception:
        return None


@router.post("/api/ml/borradores/{bid}/competencia")
async def competencia(bid: int, db: Session = Depends(get_db),
                      x_api_key: Optional[str] = Header(None),
                      current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")
    precio = await _competencia_precio(db, b.titulo)
    b.precio_competencia = precio
    db.commit(); db.refresh(b)
    return {"ok": True, "precio_competencia": precio, **_dict(b)}


async def _publicar(db: Session, b: BorradorML) -> dict:
    """Crea el ítem en ML a partir del borrador."""
    tok = await _ml_valid_token(db)
    categoria = b.categoria or ML_CATEGORIAS.get((b.producto or "").upper(), "MLA1647")
    try:
        fotos = json.loads(b.fotos_json or "[]")
    except Exception:
        fotos = []
    try:
        atributos = json.loads(b.atributos_json or "[]")
    except Exception:
        atributos = []
    payload = {
        "title": (b.titulo or "")[:60],
        "category_id": categoria,
        "price": b.precio or 0,
        "currency_id": "ARS",
        "available_quantity": b.cantidad or 1,
        "buying_mode": "buy_it_now",
        "listing_type_id": b.listing_type or "gold_special",
        "condition": b.condicion or "new",
        "pictures": [{"source": u} for u in fotos if u],
    }
    if atributos:
        payload["attributes"] = atributos
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{ML_BASE}/items", json=payload, headers=_ml_headers(tok))
        if r.status_code not in (200, 201):
            return {"ok": False, "error": r.text[:400]}
        item = r.json()
        if b.descripcion:
            try:
                await c.post(f"{ML_BASE}/items/{item['id']}/description",
                             json={"plain_text": b.descripcion}, headers=_ml_headers(tok))
            except Exception:
                pass
    return {"ok": True, "item_id": item.get("id"), "permalink": item.get("permalink")}


@router.post("/api/ml/borradores/{bid}/publicar")
async def publicar(bid: int, db: Session = Depends(get_db),
                   x_api_key: Optional[str] = Header(None),
                   current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")
    if b.estado == "publicada":
        raise HTTPException(409, "Ya está publicada")
    res = await _publicar(db, b)
    if res["ok"]:
        b.estado = "publicada"; b.item_id = res["item_id"]; b.permalink = res.get("permalink"); b.error_msg = ""
    else:
        b.estado = "error"; b.error_msg = res["error"]
    db.commit(); db.refresh(b)
    return {"ok": res["ok"], **_dict(b)}


@router.post("/api/ml/borradores/publicar-lote")
async def publicar_lote(request: Request, db: Session = Depends(get_db),
                        x_api_key: Optional[str] = Header(None),
                        current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    d = await request.json()
    ids = d.get("ids") or []
    pub, err, detalle = 0, 0, []
    for bid in ids:
        b = db.query(BorradorML).filter(BorradorML.id == bid).first()
        if not b or b.estado == "publicada":
            continue
        res = await _publicar(db, b)
        if res["ok"]:
            b.estado = "publicada"; b.item_id = res["item_id"]; b.permalink = res.get("permalink"); b.error_msg = ""; pub += 1
        else:
            b.estado = "error"; b.error_msg = res["error"]; err += 1
        db.commit()
        detalle.append({"id": bid, "ok": res["ok"], "item_id": b.item_id, "error": b.error_msg})
    return {"ok": True, "publicadas": pub, "errores": err, "detalle": detalle}
