"""
MercadoLibre — Publicaciones (cola de borradores unificada).
Carga manual / masiva / desde catálogo → cola de borradores → publicar en lote a ML.
Incluye semáforo de competitividad (precio de referencia manual + auto buy-box de catálogo).
Reutiliza el OAuth/token del módulo mercadolibre.
"""
import json
import asyncio
import time
import uuid
from typing import Optional, Dict, Any

import io
import re
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Header, UploadFile, File
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

# ── Cola de publicación en segundo plano ──────────────────────────────────────
_LOTES: Dict[str, Dict[str, Any]] = {}   # job_id → estado del lote
_TIPOS_CLASSIFIED = {"MODULO", "MODULO_DEPOSITO", "COMBO"}


async def _run_lote_bg(job_id: str, bids: list):
    """Publica borradores secuencialmente desde el servidor; el frontend solo hace polling."""
    from database.database import SessionLocal

    job = _LOTES[job_id]
    job["estado"] = "en_curso"
    delay_cl = 120  # segundos entre classified; se ajusta adaptativamente

    for i, bid in enumerate(bids):
        if job.get("cancelado"):
            break

        job["idx_actual"] = i

        db = SessionLocal()
        try:
            b = db.query(BorradorML).filter(BorradorML.id == bid).first()
            if not b or b.estado == "publicada":
                job["procesados"] = i + 1
                continue

            es_classified = (b.producto or "").upper() in _TIPOS_CLASSIFIED

            # Para classified: hasta 3 intentos con espera progresiva entre ellos
            res = None
            if es_classified:
                if job.get("cuota_classified_agotada"):
                    # ML ya rechazó con "not available for category" → no hay cuota libre disponible.
                    # Todos los siguientes classified fallarán igual; saltear sin reintentar.
                    res = {
                        "ok": False,
                        "error": "Cuota gratuita ML agotada para esta categoría. Intentá mañana o usá un listing type pago.",
                        "error_tipo": "cuota_classified",
                    }
                else:
                    for espera in [0, delay_cl, int(delay_cl * 1.5)]:
                        if espera > 0:
                            job["estado"] = "esperando"
                            job["esperando_hasta"] = time.time() + espera
                            await asyncio.sleep(espera)
                            job["estado"] = "en_curso"
                        if job.get("cancelado"):
                            break
                        res = await _publicar(db, b)
                        if res["ok"]:
                            delay_cl = max(int(delay_cl * 0.85), 90)
                            break
                        if res.get("error_tipo") == "cuota_classified":
                            # Cuota agotada: marcar y no reintentar ningún classified más
                            job["cuota_classified_agotada"] = True
                            break
                        if "temporarily" in (res.get("error") or "").lower():
                            delay_cl = min(int(delay_cl * 1.5), 600)
                        else:
                            break
            else:
                res = await _publicar(db, b)

            if res and res["ok"]:
                b.estado = "publicada"; b.item_id = res["item_id"]
                b.permalink = res.get("permalink"); b.error_msg = ""
                job["ok"] += 1
            else:
                error_msg = (res or {}).get("error", "Error desconocido")
                b.estado = "error"; b.error_msg = error_msg
                job["err"] += 1
                job["ultimos_errores"].append({"id": bid, "titulo": (b.titulo or "")[:40], "msg": error_msg[:100]})

            db.commit()
            job["procesados"] = i + 1
            job["ultimo_item"] = {"id": bid, "ok": bool(res and res["ok"]), "titulo": (b.titulo or "")[:40]}

        except Exception as ex:
            job["err"] += 1
            job["ultimos_errores"].append({"id": bid, "titulo": "", "msg": str(ex)[:100]})
            job["procesados"] = i + 1
        finally:
            db.close()

        # Pausa entre ítems (no en el último)
        if i < len(bids) - 1 and not job.get("cancelado"):
            if es_classified:
                job["estado"] = "esperando"
                job["esperando_hasta"] = time.time() + delay_cl
                await asyncio.sleep(delay_cl)
                job["estado"] = "en_curso"
            else:
                await asyncio.sleep(2)

    job["estado"] = "cancelado" if job.get("cancelado") else "completado"
    job["fin"] = time.time()
    job["esperando_hasta"] = None


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
        "categoria": b.categoria or "", "categoria_nombre": b.categoria_nombre or "",
        "seller_sku": b.seller_sku or "",
        "producto": b.producto or "", "precio": b.precio or 0,
        "cantidad": b.cantidad or 1, "condicion": b.condicion or "new", "costo": b.costo,
        "listing_type": b.listing_type or "gold_special", "cuotas_sin_interes": b.cuotas_sin_interes or 0,
        "fotos": fotos,
        "precio_referencia": b.precio_referencia, "precio_competencia": b.precio_competencia,
        "referencia_usada": ref, "semaforo": semaforo,
        "tipo_precio": b.tipo_precio or "completo",
        "modelo_nombre": b.modelo_nombre or "",
        "estado": b.estado, "item_id": b.item_id, "permalink": b.permalink,
        "error_msg": b.error_msg or "", "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@router.get("/api/ml/borradores")
async def listar(estado: Optional[str] = None, producto: Optional[str] = None,
                 db: Session = Depends(get_db),
                 x_api_key: Optional[str] = Header(None),
                 current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    q = db.query(BorradorML)
    if estado:
        q = q.filter(BorradorML.estado == estado)
    if producto:
        q = q.filter(BorradorML.producto == producto.upper())
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
        categoria_nombre=(d.get("categoria_nombre") or "").strip(),
        seller_sku=(d.get("seller_sku") or "").strip(),
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
        tipo_precio=d.get("tipo_precio", "completo"),
        modelo_nombre=(d.get("modelo_nombre") or "").strip(),
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
    for f in ("descripcion", "categoria", "categoria_nombre", "seller_sku", "condicion", "listing_type"):
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
    if "tipo_precio" in d:
        b.tipo_precio = d["tipo_precio"] or "completo"
    if "modelo_nombre" in d:
        b.modelo_nombre = (d["modelo_nombre"] or "").strip()
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


_PRODUCT_ID_ATTRS = {"PRODUCT_ID", "GTIN", "EAN", "UPC", "ISBN", "PRODUCT_IDENTIFIER"}

# Atributos que ML valida como numéricos; valores con texto causan number_invalid_format
_NUMERIC_ATTRS = {"CAPACITY", "VOLUME_CAPACITY", "LENGTH", "WIDTH", "HEIGHT",
                  "DEPTH", "WEIGHT", "NET_WEIGHT", "GROSS_WEIGHT", "VOLUME"}

# Categorías fijas por tipo de producto EcoFiver.
# El predictor automático usa el TÍTULO (ej. "autoportante" → automotores, "módulo" → software).
# Estas categorías se usan siempre que el producto esté en este dict — sin consultar el predictor.
CATEGORIAS_FIJAS: dict = {
    "PISCINA":          ("MLA373513", "Piletas de Fibra"),
    "MINIPISCINA":      ("MLA373513", "Piletas de Fibra"),
    "COMBO":            ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "MODULO":           ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "MODULO_DEPOSITO":  ("MLA413502", "Cabañas y Casas Prefabricadas"),
    # HIDROMASAJE, QUINCHO, PERGOLA, REPOSERA_FIBRA, CUCHA, ILUMINACION_PISCINA
    # → sin categoría fija (el predictor maneja bien estas palabras específicas)
}

# Categorías de ML que solo admiten buying_mode="classified" (viviendas, inmuebles, construcción).
# En modo classified: no va available_quantity ni condition.
CATEGORIAS_CLASIFICADAS: set = {
    "MLA413502",   # Cabañas y Casas Prefabricadas
    "MLA1459",     # Casas (inmuebles)
    "MLA1581",     # Departamentos (inmuebles)
    "MLA9266",     # Terrenos y Lotes
    "MLA413501",   # Construcción modular (variante)
}

# Unidades por defecto para atributos numéricos (ML las requiere explícitamente)
_ATTR_UNITS = {
    "CAPACITY": "L",
    "VOLUME_CAPACITY": "L",
    "LENGTH": "m",
    "WIDTH": "m",
    "HEIGHT": "m",
    "DEPTH": "m",
    "WEIGHT": "kg",
    "NET_WEIGHT": "kg",
    "GROSS_WEIGHT": "kg",
}


def _error_ml(r) -> str:
    """Parsea la respuesta de error de ML y devuelve un mensaje legible con status code."""
    prefix = f"HTTP {r.status_code}: "
    try:
        body = r.json()
        causes = body.get("cause") or body.get("error_cause") or []
        if isinstance(causes, dict):
            causes = [causes]
        if causes:
            parts = []
            for ca in causes[:4]:
                msg = ca.get("message") or ca.get("code") or "?"
                parts.append(f"{msg} ({ca.get('type', '?')})")
            return prefix + " | ".join(parts)
        if body.get("message"):
            return (prefix + body["message"])[:300]
        if body.get("error"):
            return (prefix + str(body["error"]))[:300]
    except Exception:
        pass
    texto = r.text[:250].strip()
    return prefix + (texto if texto else "respuesta vacía de ML")


def _sanitizar_valor_numerico(val: str) -> str:
    """Extrae el primer número válido de un string (ej: '6.40 m' → '6.4', '1.400' → '1.4')."""
    import re
    # Reemplazar coma decimal por punto
    val = val.replace(",", ".")
    # Extraer primer número flotante o entero
    m = re.search(r"\d+(?:\.\d+)?", val)
    if not m:
        return ""
    num = m.group(0).rstrip("0").rstrip(".") if "." in m.group(0) else m.group(0)
    return num or m.group(0)


async def _ml_classified_location(db: Session) -> dict:
    """
    Retorna el objeto `location` requerido por ML para publicaciones classified.

    ML classified_locations usa Base64(nombre) como ID — patrón confirmado:
      Base64("Buenos Aires") = "QnVlbm9zIEFpcmVz"  (obtenido de la API)
      Base64("Zárate")       = "WsOhcmF0ZQ=="       (calculado por el mismo patrón)
      Base64("Zarate")       = "WmFyYXRl"            (alternativa sin tilde)

    Los IDs se cachean en ConfiguracionSistema. Para resetear el caché usar
    DELETE /api/ml/location-config.
    """
    import base64
    from database.models import ConfiguracionSistema

    def _b64(name: str) -> str:
        return base64.b64encode(name.encode("utf-8")).decode("utf-8")

    def _get(clave: str):
        row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        return row.valor if row else None

    def _set(clave: str, valor: str):
        row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        if row:
            row.valor = valor
        else:
            db.add(ConfiguracionSistema(
                clave=clave, valor=valor,
                categoria="ml_location", es_secreto=False, estado="activa"
            ))
        db.commit()

    # state_id confirmado: "Buenos Aires Interior" es la zona de la Provincia (no CABA).
    # CABA en ML se llama "Buenos Aires" y tiene cities=[]. La Provincia interior tiene ciudades.
    # IDs verificados llamando GET /classified_locations/countries/AR el 2026-08-03.
    _STATE_BA_INTERIOR = "TUxBUFpPTmFpbnRl"  # "Buenos Aires Interior"
    state_id = _get("ml_loc_state_id") or _STATE_BA_INTERIOR
    city_id  = _get("ml_loc_city_id")

    if not city_id:
        try:
            async with httpx.AsyncClient(timeout=12) as hc:
                r = await hc.get(f"https://api.mercadolibre.com/classified_locations/states/{state_id}")
                if r.status_code == 200:
                    cities = r.json().get("cities") or []
                    # Buscar Zárate; si no está, usar la primera ciudad disponible
                    for city in cities:
                        cname = (city.get("name") or "").lower()
                        if "rate" in cname:
                            city_id = str(city["id"])
                            break
                    if not city_id and cities:
                        city_id = str(cities[0]["id"])
        except Exception:
            pass

        if city_id:
            _set("ml_loc_city_id", city_id)

    loc: dict = {"country": {"id": "AR"}}
    if state_id:
        loc["state"] = {"id": state_id}
    if city_id:
        loc["city"] = {"id": city_id}
    return loc


async def _publicar(db: Session, b: BorradorML) -> dict:
    """Crea el ítem en ML a partir del borrador."""
    tok = await _ml_valid_token(db)
    # Prioridad: 1) categoría manual del borrador → 2) fija por tipo de producto → 3) predictor por título
    categoria = b.categoria or ""
    cat_nombre = b.categoria_nombre or ""
    if not categoria and b.producto:
        fija = CATEGORIAS_FIJAS.get((b.producto or "").upper())
        if fija:
            categoria, cat_nombre = fija
    if not categoria:
        categoria = await _ml_categoria_sugerida(db, b.titulo)
    if not categoria:
        return {"ok": False, "error": "No se pudo detectar la categoría. Seleccioná el tipo de producto antes de publicar."}
    try:
        fotos = json.loads(b.fotos_json or "[]")
    except Exception:
        fotos = []
    try:
        atributos = json.loads(b.atributos_json or "[]")
    except Exception:
        atributos = []

    clean_attrs = []
    for attr in atributos:
        aid = (attr.get("id") or "").upper()
        val = str(attr.get("value_name") or "").strip()

        if any(k in aid for k in _PRODUCT_ID_ATTRS):
            # Solo incluir GTINs con formato válido (8/12/13/14 dígitos numéricos)
            if val.isdigit() and len(val) in (8, 12, 13, 14):
                clean_attrs.append(attr)
            # GTINs inválidos → omitir completamente

        elif any(k == aid for k in _NUMERIC_ATTRS):
            # Atributos numéricos de medidas: en piletas ML usa listas predefinidas con value_id.
            # Si no hay value_id (fue auto-generado, no seleccionado de ML), omitirlo —
            # enviar un número libre causa "El valor es incorrecto".
            # Si tiene value_id (cargado con "Cargar requeridos"), enviarlo tal cual.
            if attr.get("value_id"):
                clean_attrs.append(attr)

        else:
            clean_attrs.append(attr)

    # Auto-inyectar BRAND, MODEL y LINE — ML los exige y siempre son iguales para EcoFiver
    existing_ids = {(a.get("id") or "").upper() for a in clean_attrs}
    for attr_id, attr_val in [("BRAND", "EcoFiver"), ("MODEL", "EcoFiver"), ("LINE", "Premium")]:
        if attr_id not in existing_ids:
            clean_attrs.append({"id": attr_id, "value_name": attr_val})

    # Payload estándar (marketplace buy_it_now)
    # Si ML rechaza porque la categoría solo acepta classified, se reintenta automáticamente
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
    if clean_attrs:
        payload["attributes"] = clean_attrs

    async with httpx.AsyncClient(timeout=12) as hc:
        r = await hc.post(f"{ML_BASE}/items", json=payload, headers=_ml_headers(tok))
        if r.status_code not in (200, 201):
            # Auto-retry en modo classified si la categoría lo exige
            # (MLA413502 y otras categorías de vivienda/construcción solo aceptan classified)
            if "CLASSIFIED" in r.text.upper():
                location = await _ml_classified_location(db)
                payload_cl = {
                    "title": payload["title"],
                    "category_id": payload["category_id"],
                    "price": payload["price"],
                    "currency_id": "ARS",
                    "buying_mode": "classified",
                    "listing_type_id": "free",   # único listing type válido para classified
                    "location": location,
                    "pictures": payload.get("pictures", []),
                }
                if clean_attrs:
                    payload_cl["attributes"] = clean_attrs
                # Retry hasta 2 veces si ML dice "temporarily unavailable" (max 20s total).
                for intento in range(2):
                    r = await hc.post(f"{ML_BASE}/items", json=payload_cl, headers=_ml_headers(tok))
                    if r.status_code in (200, 201):
                        break
                    rt = r.text.upper()
                    # Cuota agotada o listing type no disponible para la categoría → error permanente,
                    # no tiene sentido reintentar. Marcamos con error_tipo para que el lote lo detecte.
                    if "NOT AVAILABLE FOR CATEGORY" in rt or ("NOT AVAILABLE" in rt and "LISTING" in rt):
                        return {"ok": False, "error": _error_ml(r), "error_tipo": "cuota_classified"}
                    if "TEMPORARILY" in rt or "TRY AGAIN" in rt:
                        await asyncio.sleep(10)
                    else:
                        break
            if r.status_code not in (200, 201):
                return {"ok": False, "error": _error_ml(r)}
        item = r.json()
        try:
            from routers.mercadolibre import _armar_descripcion_ml
            descripcion_final = _armar_descripcion_ml(db, b.descripcion or "", tipo=b.tipo_precio or "completo")
            if descripcion_final:
                await hc.post(f"{ML_BASE}/items/{item['id']}/description",
                              json={"plain_text": descripcion_final}, headers=_ml_headers(tok))
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
        await asyncio.sleep(2)
    return {"ok": True, "publicadas": pub, "errores": err, "detalle": detalle}


@router.post("/api/ml/lote-publicar")
async def lote_publicar_iniciar(
    request: Request, background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Inicia la publicación en segundo plano; retorna job_id para hacer polling."""
    _auth(x_api_key, current_user)
    d = await request.json()
    bids = [int(x) for x in (d.get("ids") or []) if x]
    if not bids:
        raise HTTPException(400, "Sin IDs")
    job_id = uuid.uuid4().hex[:8]
    _LOTES[job_id] = {
        "job_id": job_id, "estado": "iniciando",
        "total": len(bids), "procesados": 0, "ok": 0, "err": 0,
        "idx_actual": -1, "ultimo_item": None, "ultimos_errores": [],
        "esperando_hasta": None, "inicio": time.time(), "fin": None, "cancelado": False,
    }
    background_tasks.add_task(_run_lote_bg, job_id, bids)
    return {"job_id": job_id, "total": len(bids)}


@router.get("/api/ml/lote-status/{job_id}")
async def lote_status(
    job_id: str,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _auth(x_api_key, current_user)
    if job_id not in _LOTES:
        raise HTTPException(404, "Job no encontrado")
    job = dict(_LOTES[job_id])
    if job.get("esperando_hasta"):
        job["seg_restantes"] = max(0, int(job["esperando_hasta"] - time.time()))
    return job


@router.post("/api/ml/lote-cancelar/{job_id}")
async def lote_cancelar(
    job_id: str,
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    _auth(x_api_key, current_user)
    if job_id in _LOTES:
        _LOTES[job_id]["cancelado"] = True
    return {"ok": True}


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

    # Medidas de piscinas — lookup normalizado para tolerar diferencias de nombre
    import unicodedata, re as _re
    def _norm(s):
        s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
        return _re.sub(r"\s+", " ", s.lower().strip())

    pis = (cat.get("piscinas") or {})
    medidas_raw = pis.get("medidas") or {}
    medidas_norm = {_norm(k): v for k, v in medidas_raw.items()}

    def _atributos_piscina(modelo):
        m = medidas_raw.get(modelo) or medidas_norm.get(_norm(modelo)) or {}
        attrs = []
        if m.get("litros"):
            attrs.append({"id": "CAPACITY", "value_name": str(m["litros"])})
        if m.get("largo_m"):
            attrs.append({"id": "LENGTH", "value_name": str(m["largo_m"])})
        if m.get("ancho_m"):
            attrs.append({"id": "WIDTH", "value_name": str(m["ancho_m"])})
        prof = m.get("profundidad_max_m") or m.get("profundidad_min_m")
        if prof:
            attrs.append({"id": "DEPTH", "value_name": str(prof)})
        return attrs

    def _agregar(nombre, precio, producto, atributos=None):
        nonlocal creados
        if not nombre:
            return
        b = BorradorML(origen="catalogo", titulo=str(nombre)[:60],
                       producto=producto, precio=float(precio or 0),
                       cantidad=1, fotos_json="[]",
                       atributos_json=json.dumps(atributos or []),
                       created_by_id=current_user.id if current_user else None)
        db.add(b)
        creados += 1

    precios_p = pis.get("precios") or {}
    for modelo in pis.get("modelos") or []:
        _agregar(f"Piscina {modelo}", precios_p.get(modelo, 0), "PISCINA",
                 _atributos_piscina(modelo))
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
    """Genera N variantes de título con IA. Todos los demás campos se copian del borrador base."""
    _auth(x_api_key, current_user)
    import json as _json
    base = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not base:
        raise HTTPException(404, "Borrador no encontrado")
    d = await request.json()
    n = max(1, min(int(d.get("cantidad") or 10), 50))

    TIPO_LABEL = {
        "PISCINA": "Pileta / Piscina de fibra de vidrio",
        "MINIPISCINA": "Minipiscina de fibra de vidrio",
        "MODULO": "Vivienda modular Wood Frame",
        "MODULO_DEPOSITO": "Módulo depósito / Galpón prefabricado",
        "COMBO": "Combo piscina + módulo habitacional",
        "QUINCHO": "Quincho prefabricado",
        "PERGOLA": "Pérgola / Gazebo prefabricado",
        "HIDROMASAJE": "Hidromasaje / Jacuzzi / Spa",
        "REPOSERA_FIBRA": "Reposera de fibra de vidrio",
        "CUCHA": "Cucha / Casilla para perro de fibra",
        "ILUMINACION_PISCINA": "Iluminación LED para piscinas",
    }
    tipo_label = TIPO_LABEL.get(base.producto or "", base.producto or "producto")
    modelo_ctx = f" Modelo específico: {base.modelo_nombre}." if base.modelo_nombre else ""
    desc_ctx = (base.descripcion or "")[:500]

    prompt = (
        f"Sos especialista en publicaciones de MercadoLibre Argentina para la empresa EcoFiver "
        f"(fabricante de piscinas de fibra de vidrio, módulos habitacionales y accesorios, "
        f"fabricados en Zárate, Buenos Aires).\n\n"
        f"Producto: {tipo_label}.{modelo_ctx}\n"
        f"Título actual: {base.titulo}\n"
        + (f"Descripción de referencia: {desc_ctx}\n\n" if desc_ctx else "\n")
        + f"Generá {n} títulos alternativos DISTINTOS entre sí y distintos del título actual, "
        f"optimizados para el buscador de MercadoLibre:\n"
        f"- Máximo 60 caracteres cada uno\n"
        f"- Sin comas, guiones, pipes, signos ni mayúsculas sostenidas\n"
        f"- Variá el orden de las palabras clave y usá sinónimos válidos "
        f"(pileta/piscina, fibra/fibra de vidrio, modular/prefabricado, etc.)\n"
        f"- TODOS deben referirse exactamente a este producto — no inventes características ni modelos distintos\n"
        f"- Usá keywords longtail al comienzo para SEO\n\n"
        f"Devolvé EXCLUSIVAMENTE un JSON array con {n} strings, sin texto extra:\n"
        f'["título 1","título 2",...]'
    )
    try:
        txt = await ai_complete(db, prompt, max_tokens=n * 80 + 100, temperature=0.65)
    except Exception as e:
        raise HTTPException(400, f"IA no disponible: {e}")

    m = re.search(r"\[.*?\]", txt, re.S)
    try:
        titulos = _json.loads(m.group(0) if m else txt)
        if not isinstance(titulos, list):
            raise ValueError()
    except Exception:
        raise HTTPException(400, "La IA no devolvió un formato válido, probá de nuevo.")

    nuevos = []
    for tit in titulos[:n]:
        tit = str(tit).strip()[:60]
        if not tit:
            continue
        b = BorradorML(
            origen=base.origen,
            titulo=tit,
            descripcion=base.descripcion,           # igual al original — listo para publicar
            categoria=base.categoria,
            categoria_nombre=base.categoria_nombre,
            seller_sku=base.seller_sku,
            producto=base.producto,
            precio=base.precio,
            costo=base.costo,
            cantidad=base.cantidad,
            condicion=base.condicion,
            listing_type=base.listing_type,
            cuotas_sin_interes=base.cuotas_sin_interes,
            fotos_json=base.fotos_json,
            atributos_json=base.atributos_json,
            precio_referencia=base.precio_referencia,
            precio_competencia=base.precio_competencia,
            tipo_precio=base.tipo_precio,
            modelo_nombre=base.modelo_nombre,
            variante_de=base.id,
            created_by_id=current_user.id if current_user else None,
        )
        db.add(b)
        nuevos.append(b)
    db.commit()
    return {"ok": True, "creados": len(nuevos), "ids": [b.id for b in nuevos]}


@router.get("/api/ml/categoria-atributos")
async def categoria_atributos(categoria: Optional[str] = None, producto: Optional[str] = None,
                              titulo: Optional[str] = None,
                              db: Session = Depends(get_db), x_api_key=Header(None),
                              current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Atributos de una categoría de ML, separados en obligatorios (para que la
    publicación no falle al crearla) y opcionales relevantes (no bloquean la
    publicación, pero completarlos mejora la ficha técnica -- confirmado que
    eso da más exposición en los filtros de búsqueda de ML).
    """
    _auth(x_api_key, current_user)
    cat = categoria
    if not cat and titulo:
        cat = await _ml_categoria_sugerida(db, titulo)
    if not cat:
        return {"categoria": None, "atributos": [], "opcionales": [], "error": "Indicá categoría o título para detectarla."}
    tok = await _ml_valid_token(db)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ML_BASE}/categories/{cat}/attributes", headers=_ml_headers(tok))
    if r.status_code != 200:
        return {"categoria": cat, "atributos": [], "opcionales": [], "error": r.text[:200]}
    reqd, opcionales = [], []
    for a in r.json():
        tags = a.get("tags") or {}
        if tags.get("hidden") or tags.get("read_only"):
            continue
        item = {
            "id": a.get("id"), "name": a.get("name"),
            "tipo": a.get("value_type"),
            "valores": [v.get("name") for v in (a.get("values") or [])][:40],
        }
        if tags.get("required") or tags.get("catalog_required"):
            reqd.append(item)
        else:
            opcionales.append(item)
    return {"categoria": cat, "atributos": reqd, "opcionales": opcionales}


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


@router.get("/api/ml/location-config")
async def location_config(db: Session = Depends(get_db), x_api_key=Header(None),
                          current_user: Optional[Usuario] = Depends(get_current_user)):
    """Devuelve los IDs de location cacheados y el objeto que se envía a ML."""
    _auth(x_api_key, current_user)
    loc = await _ml_classified_location(db)
    from database.models import ConfiguracionSistema
    state_row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "ml_loc_state_id").first()
    city_row  = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == "ml_loc_city_id").first()
    state_id  = state_row.valor if state_row else None

    # Debug: listar TODOS los estados de Argentina para encontrar Buenos Aires Provincia
    todos_estados = []
    ciudades_raw  = []
    estado_debug  = {}
    async with httpx.AsyncClient(timeout=15) as hc:
        try:
            r = await hc.get("https://api.mercadolibre.com/classified_locations/countries/AR")
            if r.status_code == 200:
                todos_estados = [
                    {"id": s.get("id"), "name": s.get("name")}
                    for s in (r.json().get("states") or [])
                ]
        except Exception as ex:
            estado_debug["countries_error"] = str(ex)
        # Verificar el state actual y sus ciudades
        sid = (loc.get("state") or {}).get("id")
        if sid:
            try:
                r = await hc.get(f"https://api.mercadolibre.com/classified_locations/states/{sid}")
                data = r.json() if r.status_code == 200 else {}
                estado_debug["estado_actual"] = {
                    "status": r.status_code,
                    "name": data.get("name"),
                    "n_ciudades": len(data.get("cities") or []),
                    "ciudades_muestra": (data.get("cities") or [])[:10],
                }
                ciudades_raw = (data.get("cities") or [])[:20]
            except Exception as ex:
                estado_debug["estado_actual"] = {"error": str(ex)}

    return {
        "location": loc,
        "cached_state_id": state_id,
        "cached_city_id":  city_row.valor if city_row else None,
        "ml_todos_estados": todos_estados,
        "ml_estado_debug": estado_debug,
        "ml_ciudades_muestra": ciudades_raw,
    }


@router.delete("/api/ml/location-config")
async def location_config_reset(db: Session = Depends(get_db), x_api_key=Header(None),
                                current_user: Optional[Usuario] = Depends(get_current_user)):
    """Borra el caché de location para que se re-busque en el próximo publish."""
    _auth(x_api_key, current_user)
    from database.models import ConfiguracionSistema
    for clave in ("ml_loc_state_id", "ml_loc_city_id"):
        row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
        if row:
            db.delete(row)
    db.commit()
    return {"ok": True, "msg": "Caché de location borrado — se re-buscará en el próximo publish"}


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
