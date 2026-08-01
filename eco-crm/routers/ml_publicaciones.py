"""
MercadoLibre — Publicaciones (cola de borradores unificada).
Carga manual / masiva / desde catálogo → cola de borradores → publicar en lote a ML.
Incluye semáforo de competitividad (precio de referencia manual + auto buy-box de catálogo).
Reutiliza el OAuth/token del módulo mercadolibre.
"""
import json
from typing import Optional

import io
import re
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import BorradorML, Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import _require_config_access
from routers.mercadolibre import (
    _ml_valid_token, _ml_headers, ML_BASE, ML_CATEGORIAS, API_KEY,
)
from utils.ai_client import ai_complete

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/mercadolibre/publicaciones")
async def pagina_publicaciones(current_user: Usuario = Depends(_require_config_access)):
    """
    La cola de borradores se fusionó dentro de /mercadolibre (pestaña
    "Borradores y costos ML") para no tener dos paneles de MercadoLibre
    haciendo lo mismo. Se deja este redirect por si hay algún bookmark viejo.
    """
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/mercadolibre", status_code=302)


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
        "cantidad": b.cantidad or 1, "condicion": b.condicion or "new", "costo": b.costo,
        "listing_type": b.listing_type or "gold_special", "cuotas_sin_interes": b.cuotas_sin_interes or 0,
        "fotos": fotos,
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
        costo=(float(d["costo"]) if d.get("costo") else None),
        cantidad=int(d.get("cantidad") or 1),
        condicion=d.get("condicion", "new"),
        listing_type=d.get("listing_type", "gold_special"),
        cuotas_sin_interes=int(d.get("cuotas_sin_interes") or 0),
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
    if "cuotas_sin_interes" in d:
        b.cuotas_sin_interes = int(d["cuotas_sin_interes"] or 0)
    if "producto" in d:
        b.producto = (d["producto"] or "").strip().upper() or None
    if "precio" in d:
        b.precio = float(d["precio"] or 0)
    if "costo" in d:
        b.costo = float(d["costo"]) if d["costo"] else None
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
    categoria = b.categoria or await _ml_categoria_sugerida(db, b.titulo)
    if not categoria:
        return {"ok": False, "error": "No se pudo detectar la categoría de ML para este título. Cargá la categoría manualmente en el borrador."}
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


# ═══════════════════════════════════════════════════════════════════════════════
# CARGA MASIVA · CATÁLOGO · VARIANTES IA · ATRIBUTOS · FOTOS
# ═══════════════════════════════════════════════════════════════════════════════

def _col(row, *names):
    for n in names:
        for k in row.keys():
            if str(k).strip().lower() == n:
                v = row[k]
                return "" if v is None else str(v).strip()
    return ""


@router.post("/api/ml/borradores/importar")
async def importar_masiva(file: UploadFile = File(...), db: Session = Depends(get_db),
                          x_api_key=Header(None), current_user: Optional[Usuario] = Depends(get_current_user)):
    """Carga masiva desde Excel/CSV. Columnas: titulo, precio, producto, descripcion, cantidad, fotos, precio_referencia."""
    _auth(x_api_key, current_user)
    import pandas as pd
    content = await file.read()
    try:
        if (file.filename or "").lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el archivo: {e}")

    creados = 0
    for _, r in df.iterrows():
        row = r.to_dict()
        titulo = _col(row, "titulo", "title", "nombre", "producto")
        if not titulo or titulo.lower() == "nan":
            continue
        precio_raw = _col(row, "precio", "price").replace("$", "").replace(".", "").replace(",", ".")
        ref_raw = _col(row, "precio_referencia", "referencia", "competencia").replace("$", "").replace(".", "").replace(",", ".")
        fotos = [u.strip() for u in re.split(r"[;\n|]", _col(row, "fotos", "imagenes", "fotos_urls")) if u.strip()]
        try:
            precio = float(precio_raw) if precio_raw else 0
        except Exception:
            precio = 0
        try:
            ref = float(ref_raw) if ref_raw else None
        except Exception:
            ref = None
        b = BorradorML(
            origen="masiva", titulo=titulo[:60],
            descripcion=_col(row, "descripcion", "description", "detalle"),
            producto=(_col(row, "producto", "tipo").upper() or "MODULO"),
            precio=precio, precio_referencia=ref,
            cantidad=int(float(_col(row, "cantidad", "stock") or 1)),
            fotos_json=__import__("json").dumps(fotos),
            created_by_id=current_user.id if current_user else None,
        )
        db.add(b)
        creados += 1
    db.commit()
    return {"ok": True, "creados": creados}


@router.post("/api/ml/borradores/desde-catalogo")
async def desde_catalogo(db: Session = Depends(get_db), x_api_key=Header(None),
                         current_user: Optional[Usuario] = Depends(get_current_user)):
    """Genera borradores a partir del catálogo del CRM (mejor esfuerzo)."""
    _auth(x_api_key, current_user)
    try:
        from routers.catalogo import load_catalogo
        cat = load_catalogo() or {}
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el catálogo: {e}")

    creados = 0

    def _agregar(nombre, precio, producto):
        nonlocal creados
        if not nombre:
            return
        b = BorradorML(origen="catalogo", titulo=str(nombre)[:60],
                       producto=producto, precio=float(precio or 0),
                       cantidad=1, fotos_json="[]",
                       created_by_id=current_user.id if current_user else None)
        db.add(b)
        creados += 1

    pis = (cat.get("piscinas") or {})
    precios_p = pis.get("precios") or {}
    for modelo in pis.get("modelos") or []:
        _agregar(f"Piscina {modelo}", precios_p.get(modelo, 0), "PISCINA")
    mod = (cat.get("modulos") or {})
    precios_m = mod.get("precios") or {}
    modelos_mod = (mod.get("modelos") or []) + (mod.get("modelos_custom") or [])
    for modelo in modelos_mod:
        _agregar(f"Módulo {modelo}", precios_m.get(modelo, 0), "MODULO")
    db.commit()
    return {"ok": True, "creados": creados}


@router.post("/api/ml/borradores/{bid}/variantes")
async def generar_variantes(bid: int, request: Request, db: Session = Depends(get_db),
                            x_api_key=Header(None), current_user: Optional[Usuario] = Depends(get_current_user)):
    """Genera N variantes (título + descripción) con IA a partir de un borrador base."""
    _auth(x_api_key, current_user)
    import json as _json
    base = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not base:
        raise HTTPException(404, "Borrador no encontrado")
    d = await request.json()
    n = max(1, min(int(d.get("cantidad") or 3), 8))

    prompt = (
        f"Generá {n} variantes DISTINTAS para vender este producto en MercadoLibre Argentina. "
        f"Producto: '{base.titulo}'. Descripción base: '{(base.descripcion or '')[:400]}'. "
        f"Cada variante: un título atractivo y con palabras clave DISTINTO (máximo 60 caracteres) y "
        f"una descripción de venta de 2-4 líneas. Variá el enfoque/keywords para cubrir más búsquedas. "
        f"Devolvé EXCLUSIVAMENTE un JSON array válido, sin texto extra, con este formato: "
        f'[{{"titulo":"...","descripcion":"..."}}]'
    )
    try:
        txt = await ai_complete(db, prompt, max_tokens=1200, temperature=0.9)
    except Exception as e:
        raise HTTPException(400, f"IA no disponible: {e}")

    m = re.search(r"\[.*\]", txt, re.S)
    try:
        variantes = _json.loads(m.group(0) if m else txt)
    except Exception:
        raise HTTPException(400, "La IA no devolvió un formato válido, probá de nuevo.")

    creados = 0
    for v in variantes[:n]:
        tit = (v.get("titulo") or "").strip()[:60]
        if not tit:
            continue
        b = BorradorML(
            origen=base.origen, titulo=tit, descripcion=(v.get("descripcion") or "").strip(),
            categoria=base.categoria, producto=base.producto, precio=base.precio,
            cantidad=base.cantidad, condicion=base.condicion, listing_type=base.listing_type,
            fotos_json=base.fotos_json, atributos_json=base.atributos_json,
            precio_referencia=base.precio_referencia, precio_competencia=base.precio_competencia,
            variante_de=base.id, created_by_id=current_user.id if current_user else None,
        )
        db.add(b)
        creados += 1
    db.commit()
    return {"ok": True, "creados": creados}


@router.get("/api/ml/categoria-atributos")
async def categoria_atributos(categoria: Optional[str] = None, producto: Optional[str] = None,
                              titulo: Optional[str] = None,
                              db: Session = Depends(get_db), x_api_key=Header(None),
                              current_user: Optional[Usuario] = Depends(get_current_user)):
    """Atributos OBLIGATORIOS de una categoría de ML (para que la publicación no falle)."""
    _auth(x_api_key, current_user)
    cat = categoria
    if not cat and titulo:
        cat = await _ml_categoria_sugerida(db, titulo)
    if not cat:
        return {"categoria": None, "atributos": [], "error": "Indicá categoría o título para detectarla."}
    tok = await _ml_valid_token(db)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ML_BASE}/categories/{cat}/attributes", headers=_ml_headers(tok))
    if r.status_code != 200:
        return {"categoria": cat, "atributos": [], "error": r.text[:200]}
    reqd = []
    for a in r.json():
        tags = a.get("tags") or {}
        if tags.get("required") or tags.get("catalog_required"):
            reqd.append({
                "id": a.get("id"), "name": a.get("name"),
                "tipo": a.get("value_type"),
                "valores": [v.get("name") for v in (a.get("values") or [])][:40],
            })
    return {"categoria": cat, "atributos": reqd}


@router.post("/api/ml/fotos")
async def subir_foto(file: UploadFile = File(...), db: Session = Depends(get_db),
                     x_api_key=Header(None), current_user: Optional[Usuario] = Depends(get_current_user)):
    """Sube una foto a los servidores de MercadoLibre y devuelve su URL."""
    _auth(x_api_key, current_user)
    tok = await _ml_valid_token(db)
    content = await file.read()
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(f"{ML_BASE}/pictures",
                         headers={"Authorization": f"Bearer {tok}"},
                         files={"file": (file.filename or "foto.jpg", content, file.content_type or "image/jpeg")})
    if r.status_code not in (200, 201):
        return {"ok": False, "error": r.text[:300]}
    j = r.json()
    url = None
    variations = j.get("variations") or []
    if variations:
        url = variations[0].get("url") or variations[0].get("secure_url")
    url = url or j.get("url")
    return {"ok": True, "id": j.get("id"), "url": url}


async def _ml_categoria_sugerida(db, titulo: str):
    """Predice la categoría de ML a partir del título (domain_discovery)."""
    try:
        tok = await _ml_valid_token(db)
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(f"{ML_BASE}/sites/MLA/domain_discovery/search",
                            params={"q": titulo, "limit": 1}, headers=_ml_headers(tok))
        if r.status_code == 200 and r.json():
            return r.json()[0].get("category_id")
    except Exception:
        pass
    return None


@router.get("/api/ml/categoria-sugerida")
async def categoria_sugerida(titulo: str, db: Session = Depends(get_db), x_api_key=Header(None),
                             current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    cat = await _ml_categoria_sugerida(db, titulo)
    nombre = None
    if cat:
        try:
            tok = await _ml_valid_token(db)
            async with httpx.AsyncClient(timeout=10) as c:
                rr = await c.get(f"{ML_BASE}/categories/{cat}", headers=_ml_headers(tok))
            if rr.status_code == 200:
                nombre = rr.json().get("name")
        except Exception:
            pass
    return {"categoria": cat, "nombre": nombre}


@router.get("/api/ml/fees")
async def calcular_fees(precio: float, listing_type: str = "gold_special",
                        categoria: Optional[str] = None, costo: Optional[float] = None,
                        db: Session = Depends(get_db), x_api_key=Header(None),
                        current_user: Optional[Usuario] = Depends(get_current_user)):
    """Comisión de MercadoLibre por venta y ganancia neta, en función del precio."""
    _auth(x_api_key, current_user)
    tok = await _ml_valid_token(db)
    params = {"price": precio, "listing_type_id": listing_type}
    if categoria:
        params["category_id"] = categoria
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(f"{ML_BASE}/sites/MLA/listing_prices", params=params, headers=_ml_headers(tok))
    if r.status_code != 200:
        return {"ok": False, "error": r.text[:200]}
    data = r.json()
    fee = None
    if isinstance(data, list):
        for x in data:
            if x.get("listing_type_id") == listing_type:
                fee = x.get("sale_fee_amount")
                break
        if fee is None and data:
            fee = data[0].get("sale_fee_amount")
    elif isinstance(data, dict):
        fee = data.get("sale_fee_amount")
    neto = (precio - fee) if fee is not None else None
    ganancia = (neto - costo) if (neto is not None and costo) else neto
    return {"ok": True, "precio": precio, "comision": fee, "neto": neto,
            "costo": costo, "ganancia": ganancia}


@router.post("/api/ml/borradores/{bid}/duplicar")
async def duplicar(bid: int, db: Session = Depends(get_db), x_api_key=Header(None),
                   current_user: Optional[Usuario] = Depends(get_current_user)):
    """Duplica un borrador (para cargar rápido variaciones a mano)."""
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")
    nuevo = BorradorML(
        origen=b.origen, titulo=(b.titulo + " (copia)")[:60], descripcion=b.descripcion,
        categoria=b.categoria, producto=b.producto, precio=b.precio, costo=b.costo,
        cantidad=b.cantidad, condicion=b.condicion, listing_type=b.listing_type,
        fotos_json=b.fotos_json, atributos_json=b.atributos_json,
        precio_referencia=b.precio_referencia, precio_competencia=b.precio_competencia,
        variante_de=b.id, created_by_id=current_user.id if current_user else None,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"ok": True, **_dict(nuevo)}
