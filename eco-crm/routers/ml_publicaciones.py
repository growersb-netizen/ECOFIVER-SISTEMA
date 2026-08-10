"""
MercadoLibre — Publicaciones (cola de borradores unificada).
Carga manual / masiva / desde catálogo → cola de borradores → publicar en lote a ML.
Incluye semáforo de competitividad (precio de referencia manual + auto buy-box de catálogo).
Reutiliza el OAuth/token del módulo mercadolibre.
"""
import json
import asyncio
import logging
import time
import uuid
from typing import Optional, Dict, Any

import io
import re
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Header, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import BorradorML, PublicacionML, Usuario
from routers.auth import get_current_user, get_user_roles
from routers.configuracion import _require_config_access
from routers.mercadolibre import (
    _ml_valid_token, _ml_headers, ML_BASE, ML_CATEGORIAS, API_KEY,
)
from utils.ai_client import ai_complete
from utils.contexto_ecofiver import ctx_seo_ml

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ── Cola de publicación en segundo plano ──────────────────────────────────────
_LOTES: Dict[str, Dict[str, Any]] = {}   # job_id → estado del lote
# Tipos que usan buying_mode="classified" (categorías ML que lo requieren, ej: MLA413502)
_TIPOS_CLASSIFIED = {
    "MODULO", "MODULO_HABITACIONAL", "MODULO_DEPOSITO", "VIVIENDA_MODULAR",
    "QUINCHO", "PERGOLA", "COMBO", "GARITA_SEGURIDAD",
}

# Tipos que van por courier (Mercado Envíos) con envío gratis absorbido en el precio
_TIPOS_CON_ENVIO_GRATIS = {
    "HIDROMASAJE", "BANERA", "RECEPTACULO",
    "REPOSERA_FIBRA", "CUCHA",
    "ACCESORIO_PISCINA", "ACCESORIO_HIDROMASAJE",
    "ILUMINACION_PISCINA", "EQUIPO_PISCINA", "REPUESTO_PISCINA",
}


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
                _sincronizar_pub_ml(db, b)   # crear/actualizar registro PublicacionML
                job["ok"] += 1
            else:
                error_msg = (res or {}).get("error", "Error desconocido")
                b.estado = "error"; b.error_msg = error_msg
                job["err"] += 1
                job["ultimos_errores"].append({"id": bid, "titulo": (b.titulo or "")[:40], "msg": error_msg[:100]})

            # Commit con retry — SQLite puede estar bloqueado por otro job concurrente
            for _retry_db in range(5):
                try:
                    db.commit()
                    break
                except Exception as _e_commit:
                    if "database is locked" in str(_e_commit).lower() and _retry_db < 4:
                        await asyncio.sleep(2 + _retry_db * 2)
                    else:
                        raise

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
        "precio_contado": b.precio_contado,
        "incluir_envio": bool(b.incluir_envio),
        "costo_flete": b.costo_flete,
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
        precio_contado=(float(d["precio_contado"]) if d.get("precio_contado") else None),
        incluir_envio=bool(d.get("incluir_envio", False)),
        costo_flete=(float(d["costo_flete"]) if d.get("costo_flete") else None),
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
    if "precio_contado" in d:
        b.precio_contado = float(d["precio_contado"]) if d["precio_contado"] else None
    if "incluir_envio" in d:
        b.incluir_envio = bool(d["incluir_envio"])
    if "costo_flete" in d:
        b.costo_flete = float(d["costo_flete"]) if d["costo_flete"] else None
    db.commit(); db.refresh(b)
    return {"ok": True, **_dict(b)}


# ── Configuración de margen extra ML ─────────────────────────────────────────

_ML_MARGEN_KEY = "ml_margen_extra"
_ML_MARGEN_DEFAULT = 5.0  # porcentaje, e.g. 5.0 → 5%

@router.get("/api/ml/config/margen")
async def get_margen(db: Session = Depends(get_db),
                     x_api_key: Optional[str] = Header(None),
                     current_user: Optional[Usuario] = Depends(get_current_user)):
    """Devuelve el % de margen extra configurado (sobre el precio de contado). Default: 5%."""
    _auth(x_api_key, current_user)
    from database.models import ConfiguracionSistema
    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == _ML_MARGEN_KEY).first()
    val = float(row.valor) if row and row.valor else _ML_MARGEN_DEFAULT
    return {"ok": True, "margen": val}


@router.put("/api/ml/config/margen")
async def set_margen(request: Request, db: Session = Depends(get_db),
                     x_api_key: Optional[str] = Header(None),
                     current_user: Optional[Usuario] = Depends(get_current_user)):
    """Actualiza el % de margen extra (entre 1% y 30%)."""
    _auth(x_api_key, current_user)
    d = await request.json()
    val = max(1.0, min(30.0, float(d.get("margen") or _ML_MARGEN_DEFAULT)))
    from database.models import ConfiguracionSistema
    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == _ML_MARGEN_KEY).first()
    if row:
        row.valor = str(val)
    else:
        db.add(ConfiguracionSistema(
            clave=_ML_MARGEN_KEY, valor=str(val),
            categoria="ml_pricing", es_secreto=False, estado="activa"
        ))
    db.commit()
    return {"ok": True, "margen": val}


# ── Recalcular precios de todos los borradores con precio_contado ─────────────

@router.post("/api/ml/borradores/recalcular-precios")
async def recalcular_precios(request: Request, db: Session = Depends(get_db),
                             x_api_key: Optional[str] = Header(None),
                             current_user: Optional[Usuario] = Depends(get_current_user)):
    """
    Recalcula el precio ML de todos los borradores que tienen precio_contado guardado.
    Usa: precio_ml = (contado*(1+margen) + flete) / (1 - tasa_comision - tasa_cuotas - iibb)
    Body: { margen: float (%), iibb: float (%), tasas_cuotas: {3: %, 6: %, ...} }
    Devuelve: { actualizados: N, sin_contado: M, total: T }
    """
    _auth(x_api_key, current_user)
    d = await request.json()

    # Leer margen (del body, o del config guardado)
    from database.models import ConfiguracionSistema
    cfg_margen = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == _ML_MARGEN_KEY).first()
    margen_pct = float(d.get("margen") or (float(cfg_margen.valor) if cfg_margen else _ML_MARGEN_DEFAULT))
    margen_factor = margen_pct / 100.0

    iibb_pct = float(d.get("iibb") or 0) / 100.0

    # Tasas de comisión con IVA (21%)
    IVA = 1.21
    comision_rates = {"gold_special": 0.09 * IVA, "gold_pro": 0.135 * IVA}

    # Tasas de cuotas sin interés con IVA — pueden venir en el body para usar los del cliente
    cuotas_neto = {0: 0, 3: 0.085, 6: 0.148, 9: 0.206, 12: 0.262, 18: 0.360}
    cuotas_body = d.get("tasas_cuotas") or {}
    for k, v in cuotas_body.items():
        try:
            cuotas_neto[int(k)] = float(v) / 100.0
        except Exception:
            pass
    cuotas_rates = {k: v * IVA for k, v in cuotas_neto.items()}

    borradores = db.query(BorradorML).filter(BorradorML.precio_contado != None).all()
    actualizados = 0
    sin_contado = db.query(BorradorML).filter(BorradorML.precio_contado == None).count()
    total = db.query(BorradorML).count()

    for b in borradores:
        contado = b.precio_contado or 0
        if contado <= 0:
            continue
        lt = b.listing_type or "gold_special"
        cuotas = b.cuotas_sin_interes or 0
        flete = (b.costo_flete or 0) if b.incluir_envio else 0

        tasa_comision = comision_rates.get(lt, 0.09 * IVA)
        tasa_cuotas = cuotas_rates.get(cuotas, 0) if (cuotas > 0 and lt == "gold_pro") else 0
        tasa_total = tasa_comision + tasa_cuotas + iibb_pct

        if tasa_total >= 1:
            continue  # evitar división por cero o precios negativos
        # precio_ml = (contado*(1+margen) + flete) / (1 - tasa_total)
        # Redondear a centenas
        precio_nuevo = round((contado * (1 + margen_factor) + flete) / (1 - tasa_total) / 100) * 100
        if precio_nuevo != b.precio and precio_nuevo > 0:
            b.precio = precio_nuevo
            actualizados += 1

    db.commit()
    return {
        "ok": True,
        "actualizados": actualizados,
        "sin_contado": sin_contado,
        "total": total,
        "margen_usado": margen_pct,
        "iibb_usado": iibb_pct * 100,
    }


# ── Regenerar títulos y descripciones de módulos con IA (background) ──────────

_TIPOS_MODULO = {"MODULO", "MODULO_HABITACIONAL", "VIVIENDA_MODULAR", "MODULO_DEPOSITO",
                 "QUINCHO", "PERGOLA", "COMBO"}

# Estado del job de regeneración (simple, en memoria)
_REGEN_JOB: Dict[str, Any] = {}

_TIPO_LABEL_MODULO = {
    "MODULO":             "módulo habitacional de celulosa estructural / espacio habitacional prefabricado",
    "MODULO_HABITACIONAL":"módulo habitacional de celulosa estructural (6-18 m²) — espacio auxiliar, NO es vivienda",
    "VIVIENDA_MODULAR":   "vivienda modular de celulosa estructural / casa prefabricada (24 m² en adelante)",
    "MODULO_DEPOSITO":    "módulo depósito / galpón prefabricado de celulosa estructural",
    "QUINCHO":            "quincho prefabricado",
    "PERGOLA":            "pérgola / gazebo",
    "COMBO":              "combo piscina y módulo habitacional",
}


_log_regen = logging.getLogger("ml.regen_ia")


def _regen_sanear_titulo(tit: str) -> str:
    import re as _re
    # Whitelist: solo letras (incluyendo tildes/ñ), números, espacios y
    # puntuación básica que ML acepta. Todo lo demás → espacio.
    tit = _re.sub(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9 \-\+\.\/\(\)&']", ' ', tit)
    tit = _re.sub(r'\s+', ' ', tit).strip()
    if len(tit) > 60:
        cut = tit[:60]
        tit = (cut[:cut.rfind(' ')] if ' ' in cut else cut).strip()
    return tit


def _prompt_regen(tipo_label: str, palabras: str) -> tuple[str, str]:
    """Devuelve (system, user_prompt) para regenerar título+desc de un módulo."""
    from utils.contexto_ecofiver import ctx_empresa, ctx_seo_ml
    system = ctx_empresa()
    user_prompt = (
        ctx_seo_ml(tipo_producto=tipo_label, descripcion_existente=palabras[:400])
        + "\n\n════════════════════════════════════════\n"
        "TAREA: Generá TÍTULO y DESCRIPCIÓN para MercadoLibre Argentina.\n"
        f"Producto: {palabras[:300]}\n\n"
        'Respondé SOLO con JSON válido, sin texto extra ni markdown:\n'
        '{"titulo": "...", "descripcion": "..."}'
    )
    return system, user_prompt


async def _regen_un_borrador(bid: int, job_dict: dict) -> None:
    """Procesa un solo borrador: genera IA y guarda. Actualiza job_dict."""
    import json as _json
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        b = db.query(BorradorML).filter(BorradorML.id == bid).first()
        if not b:
            return
        tipo_label = _TIPO_LABEL_MODULO.get(b.producto or "MODULO", "módulo habitacional prefabricado")
        palabras = b.modelo_nombre or b.titulo or tipo_label
        system, user_prompt = _prompt_regen(tipo_label, palabras)
        texto = await ai_complete(db, user_prompt, system=system, max_tokens=2800, temperature=0.6)
        try:
            result = _json.loads(texto)
        except Exception:
            import re as _re
            m = _re.search(r'\{.*\}', texto, _re.DOTALL)
            if not m:
                raise ValueError(f"IA no devolvió JSON válido: {texto[:120]}")
            result = _json.loads(m.group())

        tit = _regen_sanear_titulo(result.get("titulo") or "")
        desc = result.get("descripcion", "")
        if not tit:
            raise ValueError("Título vacío después de sanear")
        if len(desc) < 200:
            raise ValueError(f"Descripción muy corta ({len(desc)} chars)")
        if tit:
            b.titulo = tit
        if desc:
            b.descripcion = desc
        db.commit()
        job_dict["actualizados"] += 1
    except Exception as exc:
        err_msg = str(exc)[:200]
        job_dict["errores"] += 1
        job_dict.setdefault("ultimo_error", err_msg)
        _log_regen.error("[regen_modulos bid=%s] %s", bid, err_msg)
    finally:
        db.close()


async def _regen_modulos_bg(bid_list: list, db_maker):
    """Background task: regenera IA para cada borrador de módulo en bid_list."""
    _REGEN_JOB["estado"] = "en_curso"
    _REGEN_JOB["total"] = len(bid_list)
    _REGEN_JOB["actualizados"] = 0
    _REGEN_JOB["errores"] = 0
    _REGEN_JOB.pop("ultimo_error", None)

    # Verificar proveedor antes de empezar (falla rápido)
    from database.database import SessionLocal
    _db_test = SessionLocal()
    try:
        from utils.ai_client import get_active_provider
        pname, _ = get_active_provider(_db_test)
        if not pname:
            _REGEN_JOB["estado"] = "error"
            _REGEN_JOB["ultimo_error"] = "No hay proveedor de IA configurado. Andá a Configuración → API Keys."
            _log_regen.error("[regen_modulos] Sin proveedor IA — abortando")
            return
        _log_regen.info("[regen_modulos] Proveedor: %s — %d borradores", pname, len(bid_list))
    finally:
        _db_test.close()

    for i, bid in enumerate(bid_list):
        _REGEN_JOB["idx"] = i
        await _regen_un_borrador(bid, _REGEN_JOB)

    _REGEN_JOB["estado"] = "completado"
    _log_regen.info("[regen_modulos] Completado: %d ok, %d errores",
                    _REGEN_JOB["actualizados"], _REGEN_JOB["errores"])


@router.post("/api/ml/borradores/regenerar-ia-modulos")
async def regenerar_ia_modulos(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Lanza en BACKGROUND la regeneración de título + descripción con IA
    para todos los borradores de módulos. Devuelve inmediatamente con el total.
    Body opcional: { "tipos": ["MODULO", "VIVIENDA_MODULAR"], "estado": "borrador" }
    """
    _auth(x_api_key, current_user)
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass

    tipos_filtro = list(set(data.get("tipos") or _TIPOS_MODULO))
    estado_filtro = data.get("estado")

    q = db.query(BorradorML.id).filter(BorradorML.producto.in_(tipos_filtro))
    if estado_filtro:
        q = q.filter(BorradorML.estado == estado_filtro)
    bid_list = [row[0] for row in q.all()]

    if not bid_list:
        return {"ok": True, "total": 0, "mensaje": "No hay borradores de módulos para regenerar."}

    _REGEN_JOB.update({"estado": "iniciado", "total": len(bid_list), "actualizados": 0, "errores": 0, "idx": 0})

    from database.database import SessionLocal as _SL
    background_tasks.add_task(_regen_modulos_bg, bid_list, _SL)

    return {
        "ok": True,
        "total": len(bid_list),
        "mensaje": f"Regenerando {len(bid_list)} borradores en segundo plano. Actualizá la lista en unos minutos.",
    }


@router.get("/api/ml/borradores/regenerar-ia-modulos/estado")
async def regenerar_ia_estado(
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Estado del job de regeneración en curso."""
    _auth(x_api_key, current_user)
    return _REGEN_JOB or {"estado": "sin_job"}


# ── Actualizar publicaciones VIVAS en ML con IA ───────────────────────────────

_ACTUALIZAR_VIVO_JOB: Dict[str, Any] = {}

# Caché de atributos válidos por categoría ML (TTL 1 hora; se reinicia con el proceso)
_CAT_ATTRS_CACHE: Dict[str, Any] = {}


_log_actualizar = logging.getLogger("ml.actualizar_vivo")


async def _actualizar_publicados_bg(bid_list: list):
    """Background task: actualiza título+descripción en ML para publicaciones ya activas."""
    import json as _json
    from database.database import SessionLocal

    _ACTUALIZAR_VIVO_JOB["estado"] = "en_curso"
    _ACTUALIZAR_VIVO_JOB["total"] = len(bid_list)
    _ACTUALIZAR_VIVO_JOB["actualizados"] = 0
    _ACTUALIZAR_VIVO_JOB["errores"] = 0
    _ACTUALIZAR_VIVO_JOB["detalles"] = []
    _ACTUALIZAR_VIVO_JOB.pop("ultimo_error", None)

    # ── Fail-fast: verificar proveedor IA ────────────────────────────────────
    _db_test = SessionLocal()
    try:
        from utils.ai_client import get_active_provider
        pname, _ = get_active_provider(_db_test)
        if not pname:
            _ACTUALIZAR_VIVO_JOB["estado"] = "error"
            _ACTUALIZAR_VIVO_JOB["ultimo_error"] = "No hay proveedor de IA configurado. Andá a Configuración → API Keys."
            _log_actualizar.error("[actualizar_vivo] Sin proveedor IA — abortando")
            return
        _log_actualizar.info("[actualizar_vivo] Proveedor: %s — %d ítems", pname, len(bid_list))
    finally:
        _db_test.close()

    async with httpx.AsyncClient(timeout=120) as hc:
        for i, bid in enumerate(bid_list):
            _ACTUALIZAR_VIVO_JOB["idx"] = i
            db = SessionLocal()
            try:
                b = db.query(BorradorML).filter(BorradorML.id == bid).first()
                if not b or not b.item_id:
                    continue

                tipo_label = _TIPO_LABEL_MODULO.get(b.producto or "MODULO", "módulo habitacional prefabricado")
                palabras = b.modelo_nombre or b.titulo or tipo_label
                system, user_prompt = _prompt_regen(tipo_label, palabras)
                try:
                    texto = await ai_complete(db, user_prompt, system=system, max_tokens=2800, temperature=0.6)
                    try:
                        result = _json.loads(texto)
                    except Exception:
                        import re as _re2
                        m = _re2.search(r'\{.*\}', texto, _re2.DOTALL)
                        if not m:
                            raise ValueError(f"IA no devolvió JSON: {texto[:100]}")
                        result = _json.loads(m.group())

                    tit = _regen_sanear_titulo(result.get("titulo") or "")
                    desc = result.get("descripcion", "")

                    if not tit or len(desc) < 200:
                        raise ValueError(f"Texto IA demasiado corto (tit={len(tit)}, desc={len(desc)})")

                    # ── Token ML ─────────────────────────────────────────────
                    tok = await _ml_valid_token(db)
                    # ── Guardar en BD (siempre — independiente de ML) ────────
                    # El objetivo principal es tener el CRM con títulos/descripciones
                    # actualizados. La actualización en ML es secundaria.
                    tit = _forzar_keywords_titulo(tit, b.producto or "")
                    b.titulo = tit
                    b.descripcion = desc
                    try:
                        pub = db.query(PublicacionML).filter(PublicacionML.item_id == b.item_id).first()
                        if pub:
                            pub.titulo = tit
                            pub.descripcion = desc
                    except Exception:
                        pass
                    db.commit()

                    # ── Intentar actualizar en ML (soft-fail) ────────────────
                    # Los classified listings (módulos, quinchos, etc.) frecuentemente
                    # rechazan updates de título via API (cause_id 277 de ML).
                    # Si ML falla: el CRM ya tiene los datos nuevos → contar como ✅.
                    ml_tit_ok = ml_desc_ok = False
                    ml_warn = ""
                    if tok:
                        hdrs = _ml_headers(tok)
                        try:
                            r_tit = await hc.put(
                                f"{ML_BASE}/items/{b.item_id}",
                                json={"title": tit},
                                headers=hdrs,
                            )
                            ml_tit_ok = r_tit.status_code in (200, 201)
                        except Exception as _ex:
                            ml_warn += f"tít excepción: {str(_ex)[:40]}; "

                        try:
                            from routers.mercadolibre import _armar_descripcion_ml
                            desc_final = _armar_descripcion_ml(db, desc, tipo=b.tipo_precio or "completo")
                        except Exception:
                            desc_final = desc
                        try:
                            r_desc = await hc.put(
                                f"{ML_BASE}/items/{b.item_id}/description",
                                json={"plain_text": desc_final},
                                headers=hdrs,
                            )
                            ml_desc_ok = r_desc.status_code in (200, 201)
                            if not ml_desc_ok and not ml_tit_ok:
                                ml_warn = (
                                    f"ML no actualizado — "
                                    f"tít {r_tit.status_code if not ml_tit_ok else 'ok'}; "
                                    f"desc {r_desc.status_code}: {r_desc.text[:40]}"
                                )
                            elif not ml_tit_ok:
                                ml_warn = f"ML tít {r_tit.status_code} (classified — normal)"
                        except Exception as _ex2:
                            ml_warn += f"desc excepción: {str(_ex2)[:40]}"

                    # Contar siempre como actualizado (CRM ok); ML es best-effort
                    _ACTUALIZAR_VIVO_JOB["actualizados"] += 1
                    if ml_tit_ok and ml_desc_ok:
                        _log_actualizar.info("[actualizar_vivo] %s OK (local+ML)", b.item_id)
                    else:
                        if ml_warn:
                            _ACTUALIZAR_VIVO_JOB["detalles"].append({"id": b.item_id, "warn": ml_warn})
                            _ACTUALIZAR_VIVO_JOB["ultimo_error"] = ml_warn
                        _log_actualizar.info("[actualizar_vivo] %s OK local; ML: %s", b.item_id, ml_warn or "sin token")

                except Exception as ex:
                    err_msg = str(ex)[:200]
                    _ACTUALIZAR_VIVO_JOB["errores"] += 1
                    _ACTUALIZAR_VIVO_JOB["detalles"].append({"id": getattr(b, "item_id", bid), "error": err_msg})
                    _ACTUALIZAR_VIVO_JOB["ultimo_error"] = err_msg
                    _log_actualizar.error("[actualizar_vivo bid=%s] %s", bid, err_msg)
            finally:
                db.close()

    _ACTUALIZAR_VIVO_JOB["estado"] = "completado"
    _log_actualizar.info("[actualizar_vivo] Completado: %d ok, %d errores",
                         _ACTUALIZAR_VIVO_JOB["actualizados"], _ACTUALIZAR_VIVO_JOB["errores"])


@router.post("/api/ml/publicaciones/actualizar-ia-modulos")
async def actualizar_publicados_ia(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Regenera título + descripción con IA y los actualiza en MercadoLibre
    para todas las publicaciones de módulos ya publicadas (estado='publicada').
    Body opcional: { "tipos": ["MODULO", "VIVIENDA_MODULAR"] }
    """
    _auth(x_api_key, current_user)
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass

    tipos_filtro = list(set(data.get("tipos") or _TIPOS_MODULO))

    # Solo borradores con item_id (ya publicados)
    bid_list = [
        row[0] for row in
        db.query(BorradorML.id)
          .filter(BorradorML.producto.in_(tipos_filtro))
          .filter(BorradorML.estado == "publicada")
          .filter(BorradorML.item_id.isnot(None))
          .all()
    ]

    if not bid_list:
        return {"ok": True, "total": 0, "mensaje": "No hay publicaciones activas de módulos para actualizar."}

    _ACTUALIZAR_VIVO_JOB.update({
        "estado": "iniciado", "total": len(bid_list),
        "actualizados": 0, "errores": 0, "idx": 0, "detalles": [],
    })
    background_tasks.add_task(_actualizar_publicados_bg, bid_list)

    return {
        "ok": True,
        "total": len(bid_list),
        "mensaje": f"Actualizando {len(bid_list)} publicaciones en MercadoLibre en segundo plano.",
    }


@router.get("/api/ml/publicaciones/actualizar-ia-modulos/estado")
async def actualizar_publicados_estado(
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Estado del job de actualización de publicaciones vivas."""
    _auth(x_api_key, current_user)
    return _ACTUALIZAR_VIVO_JOB or {"estado": "sin_job"}


@router.get("/api/ml/test-ia")
async def test_ia(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Diagnóstico rápido del proveedor de IA.
    Llama a ai_complete con un prompt mínimo y devuelve el resultado o el error exacto.
    """
    _auth(x_api_key, current_user)
    from utils.ai_client import get_active_provider, get_ai_key_info
    info = get_ai_key_info(db)
    if not info.get("configurado"):
        return {"ok": False, "proveedor": None, "error": "Ningún proveedor de IA configurado (DB ni env vars)"}
    try:
        resultado = await ai_complete(db, 'Respondé solo con el JSON: {"saludo": "hola"}',
                                      max_tokens=50, temperature=0)
        return {"ok": True, "proveedor": info.get("proveedor"), "modelo": info.get("modelo"),
                "respuesta": resultado}
    except Exception as exc:
        return {"ok": False, "proveedor": info.get("proveedor"), "modelo": info.get("modelo"),
                "error": str(exc)[:500]}


@router.delete("/api/ml/borradores/{bid}")
async def borrar(bid: int, db: Session = Depends(get_db),
                 x_api_key: Optional[str] = Header(None),
                 current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    b = db.query(BorradorML).filter(BorradorML.id == bid).first()
    if not b:
        raise HTTPException(404, "Borrador no encontrado")

    ml_cerrada = False
    ml_error: Optional[str] = None
    item_id_local = b.item_id

    # Si está publicada/pausada en ML, intentar cerrar/pausar antes de borrar localmente
    if b.item_id and b.estado in ("publicada", "pausada"):
        try:
            tok = await _ml_valid_token(db)
            async with httpx.AsyncClient(timeout=15) as hc:
                # Intentar cerrar (funciona para listings normales Y clasificados)
                r = await hc.put(
                    f"{ML_BASE}/items/{b.item_id}",
                    json={"status": "closed"},
                    headers=_ml_headers(tok),
                )
                if r.is_success:
                    ml_cerrada = True
                else:
                    # Fallback: intentar pausar (solo listings normales)
                    r2 = await hc.put(
                        f"{ML_BASE}/items/{b.item_id}",
                        json={"status": "paused"},
                        headers=_ml_headers(tok),
                    )
                    if r2.is_success:
                        ml_cerrada = True
                    else:
                        ml_error = f"ML {r.status_code}: {r.text[:200]}"
        except Exception as ex:
            ml_error = str(ex)[:200]

    db.delete(b)
    db.commit()
    return {"ok": True, "ml_cerrada": ml_cerrada, "ml_error": ml_error, "item_id": item_id_local}


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
    # ── Módulos y construcción (classified) ───────────────────────────────────
    "COMBO":              ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "MODULO":             ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "MODULO_HABITACIONAL":("MLA413502", "Cabañas y Casas Prefabricadas"),
    "MODULO_DEPOSITO":    ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "VIVIENDA_MODULAR":   ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "QUINCHO":            ("MLA413502", "Cabañas y Casas Prefabricadas"),
    "GARITA_SEGURIDAD":   ("MLA413502", "Cabañas y Casas Prefabricadas"),
    # ── Hidromasajes y bañeras ────────────────────────────────────────────────
    # MLA88471 = Jacuzzis e Hidromasajes (verificado en producción MLA)
    "HIDROMASAJE":        ("MLA88471",  "Jacuzzis e Hidromasajes"),
    "BANERA":             ("MLA88471",  "Jacuzzis e Hidromasajes"),
    # ── Piscinas ─────────────────────────────────────────────────────────────
    # MLA373513 = Piletas de Fibra de Vidrio (verificado en producción MLA)
    "PISCINA":            ("MLA373513", "Piletas de Fibra de Vidrio"),
    "MINIPISCINA":        ("MLA373513", "Piletas de Fibra de Vidrio"),
}

# Palabras clave mínimas obligatorias por tipo para que ML categorice correctamente.
# Si el título NO contiene ninguna de estas palabras, se prepende el prefijo mínimo.
_TITULO_KEYWORDS_MINIMAS: dict = {
    "HIDROMASAJE":        (["hidromasaje", "jacuzzi", "spa"],               "Hidromasaje Jacuzzi"),
    "BANERA":             (["bañera", "banera", "jacuzzi", "hidromasaje"],  "Bañera Hidromasaje"),
    "RECEPTACULO":        (["receptáculo", "receptaculo", "ducha"],         "Receptáculo Ducha"),
    "PISCINA":            (["piscina", "pileta"],                           "Piscina"),
    "MINIPISCINA":        (["piscina", "pileta", "minipiscina"],            "Minipiscina"),
    "MODULO":             (["módulo", "modulo", "cabaña", "cabana"],        "Módulo"),
    "MODULO_HABITACIONAL":(["módulo", "modulo"],                            "Módulo"),
    "MODULO_DEPOSITO":    (["depósito", "deposito", "módulo", "modulo", "galpón", "galpon"], "Módulo Depósito"),
    "VIVIENDA_MODULAR":   (["vivienda", "módulo", "modulo", "casa"],        "Vivienda Modular"),
    "QUINCHO":            (["quincho"],                                     "Quincho"),
    "PERGOLA":            (["pérgola", "pergola"],                          "Pérgola"),
    "COMBO":              (["combo", "piscina", "pileta"],                  "Combo Piscina"),
    "ACCESORIO_HIDROMASAJE":(["accesorio", "spa", "hidromasaje", "jacuzzi"],"Accesorio Spa"),
    "ACCESORIO_PISCINA":  (["accesorio", "piscina", "pileta"],              "Accesorio Piscina"),
    "ILUMINACION_PISCINA":(["iluminación", "iluminacion", "led", "piscina"],"Iluminación LED Piscina"),
}


def _forzar_keywords_titulo(titulo: str, tipo_prod: str) -> str:
    """
    Garantiza que el título contenga las palabras clave mínimas para que ML
    categorice correctamente el producto. Si faltan, prepende el prefijo mínimo.
    Siempre devuelve un título ≤ 60 caracteres.
    """
    conf = _TITULO_KEYWORDS_MINIMAS.get(tipo_prod)
    if not conf or not titulo:
        return titulo[:60] if titulo else titulo
    keywords, prefijo = conf
    tit_low = titulo.lower()
    if any(k in tit_low for k in keywords):
        return titulo[:60]
    # No tiene keywords → prepende el prefijo mínimo
    nuevo = f"{prefijo} {titulo}"
    if len(nuevo) > 60:
        nuevo = nuevo[:60]
        if ' ' in nuevo:
            nuevo = nuevo[:nuevo.rfind(' ')].strip()
    return nuevo

# Títulos de fallback usados cuando el predictor falla para un tipo de producto.
# Permite que "Tina Spa Compacto 110x110", "Bañera Orbis" y similares
# obtengan una categoría válida incluso si el predictor no reconoce el título exacto.
_FALLBACK_TITULO_POR_TIPO: dict = {
    "HIDROMASAJE":          "Hidromasaje jacuzzi spa con jets acrílico sanitario",
    "BANERA":               "Bañera hidromasaje jacuzzi con jets acrílico",
    "RECEPTACULO":          "Receptáculo plato de ducha acrílico",
    "PISCINA":              "Piscina pileta fibra de vidrio",
    "MINIPISCINA":          "Minipiscina pileta compacta fibra de vidrio",
    "ACCESORIO_HIDROMASAJE":"Accesorio para hidromasaje jacuzzi spa",
    "ACCESORIO_PISCINA":    "Accesorio para piscina pileta",
    "ILUMINACION_PISCINA":  "Iluminación LED sumergible para piscina pileta",
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


async def _ml_cat_attributes(categoria: str, tok: str) -> Optional[set]:
    """
    Retorna el set de IDs de atributos válidos (no deprecated) para la categoría.
    Cacheado 1 hora.
    - Devuelve None si la llamada falla (no se pudo consultar → el caller decide).
    - Devuelve set() vacío si la API respondió pero la categoría no tiene atributos válidos.
    - Devuelve {ids...} si hay atributos válidos.
    El caller usa None para "no sé → no filtr para buy_it_now, sí limpio para classified".
    """
    import time as _time
    cached = _CAT_ATTRS_CACHE.get(categoria)
    if cached and _time.time() - cached["ts"] < 3600:
        return cached["ids"]
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get(
                f"{ML_BASE}/categories/{categoria}/attributes",
                headers=_ml_headers(tok),
            )
        if r.status_code != 200:
            return None  # API no respondió bien → desconocido
        valid_ids = {
            (a.get("id") or "").upper()
            for a in r.json()
            if not (a.get("tags") or {}).get("deprecated")
        }
        _CAT_ATTRS_CACHE[categoria] = {"ids": valid_ids, "ts": _time.time()}
        return valid_ids
    except Exception:
        return None  # error de red/timeout → desconocido


def _ml_strip_deprecated_root_field(payload: dict, error_text: str) -> tuple:
    """
    Parsea el error de ML buscando el campo root deprecated y lo elimina del payload.
    Ej: 'Warranty field is deprecated' → elimina payload['warranty'].
    Retorna (payload_modificado, campo_eliminado) o (payload_sin_cambios, '').
    """
    import re as _re
    patterns = [
        r"(\w+)\s+field\s+is\s+deprecated",
        r"field\s+['\"]?(\w+)['\"]?\s+is\s+deprecated",
        r"['\"]?(\w+)['\"]?\s+is\s+deprecated",
    ]
    for pat in patterns:
        m = _re.search(pat, error_text, _re.IGNORECASE)
        if m:
            field = m.group(1).lower()
            if field in payload:
                payload.pop(field)
                return payload, field
    return payload, ""


async def _publicar(db: Session, b: BorradorML) -> dict:
    """Crea el ítem en ML a partir del borrador."""
    tok = await _ml_valid_token(db)

    # Determinar tipo de producto — primero del campo, si no desde el título
    tipo_prod = (b.producto or "").upper()
    if not tipo_prod and b.titulo:
        _tl = b.titulo.lower()
        if any(k in _tl for k in ["hidromasaje", "jacuzzi", "spa", "tina spa"]):
            tipo_prod = "HIDROMASAJE"
        elif any(k in _tl for k in ["bañera", "banera"]):
            tipo_prod = "BANERA"
        elif any(k in _tl for k in ["receptáculo", "receptaculo", "plato de ducha"]):
            tipo_prod = "RECEPTACULO"
        elif any(k in _tl for k in ["piscina", "pileta"]):
            tipo_prod = "PISCINA"

    # Prioridad: 1) categoría manual del borrador → 2) fija por tipo de producto → 3) predictor por título
    categoria = b.categoria or ""
    cat_nombre = b.categoria_nombre or ""
    if not categoria and tipo_prod:
        fija = CATEGORIAS_FIJAS.get(tipo_prod)
        if fija:
            categoria, cat_nombre = fija
    if not categoria:
        categoria = await _ml_categoria_sugerida(db, b.titulo)
    # Fallback: si el predictor no reconoció el título, intentar con un título genérico
    # según el tipo de producto (ej. "Tina Spa Compacto" → predictor con "Hidromasaje jacuzzi…")
    if not categoria and tipo_prod:
        fallback_titulo = _FALLBACK_TITULO_POR_TIPO.get(tipo_prod)
        if fallback_titulo:
            categoria = await _ml_categoria_sugerida(db, fallback_titulo)
    if not categoria:
        return {"ok": False, "error": "No se pudo detectar la categoría. Seleccioná el tipo de producto antes de publicar."}

    # Obtener atributos válidos para la categoría (cacheado 1h).
    # Se usa para filtrar clean_attrs y evitar IDs deprecated que ML ya no acepta.
    _valid_attr_ids = await _ml_cat_attributes(categoria, tok)

    try:
        fotos = json.loads(b.fotos_json or "[]")
    except Exception:
        fotos = []
    try:
        atributos = json.loads(b.atributos_json or "[]")
    except Exception:
        atributos = []
    # tipo_prod ya definido al inicio de la función (no redefinir aquí)

    # Tipos que usan texto libre para atributos de medidas (no listas predefinidas de ML).
    # Para piscinas ML usa value_id de lista; para hidromasajes/bañeras acepta texto.
    _TIPOS_DIM_LIBRE = {"HIDROMASAJE", "BANERA", "RECEPTACULO"}

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
            # Atributos numéricos de medidas:
            # - Piscinas: ML usa listas predefinidas → solo incluir si tiene value_id
            # - Hidromasajes/bañeras/receptáculos: ML acepta texto libre → incluir siempre si tiene valor
            if attr.get("value_id"):
                clean_attrs.append(attr)
            elif tipo_prod in _TIPOS_DIM_LIBRE and val:
                clean_attrs.append(attr)

        else:
            clean_attrs.append(attr)

    # Auto-inyectar BRAND, MODEL, LINE y GARANTÍA — siempre iguales para EcoFiver
    existing_ids = {(a.get("id") or "").upper() for a in clean_attrs}
    for attr_id, attr_val in [
        ("BRAND",         "EcoFiver"),
        ("MODEL",         "EcoFiver"),
        ("LINE",          "Premium"),
        ("WARRANTY_TYPE", "Garantía del vendedor"),
        ("WARRANTY_TIME", "10 años"),
    ]:
        if attr_id not in existing_ids:
            clean_attrs.append({"id": attr_id, "value_name": attr_val})

    # Auto-inyectar atributos obligatorios según tipo de producto.
    # IS_INFLATABLE es un error bloqueante en categorías de spas/piletas.
    # COLOR es warning pero mejora la ficha.
    _ATTRS_DEFAULT_TIPO = {
        "HIDROMASAJE":    [("IS_INFLATABLE", "No"), ("COLOR", "Blanco")],
        "PISCINA":        [("IS_INFLATABLE", "No"), ("COLOR", "Blanco")],
        "MINIPISCINA":    [("IS_INFLATABLE", "No"), ("COLOR", "Blanco")],
        "BANERA":         [("IS_INFLATABLE", "No"), ("COLOR", "Blanco")],
        "RECEPTACULO":    [("IS_INFLATABLE", "No"), ("COLOR", "Blanco")],
        "REPOSERA_FIBRA": [("COLOR", "Blanco")],
    }
    # Refrescar set con lo que ya se inyectó arriba
    existing_ids = {(a.get("id") or "").upper() for a in clean_attrs}
    for attr_id, attr_val in _ATTRS_DEFAULT_TIPO.get(tipo_prod, []):
        if attr_id.upper() not in existing_ids:
            clean_attrs.append({"id": attr_id, "value_name": attr_val})

    # Auto-inyectar dimensiones para tipos que ML las requiere pero los borradores
    # generados masivamente no las tienen en atributos_json.
    # Se parsean del título (ej. "Spa Cuadrado 110x110" → W=110cm, L=110cm)
    # y HEIGHT se inyecta con default según tipo (altura real del producto).
    if tipo_prod in _TIPOS_DIM_LIBRE:
        existing_ids = {(a.get("id") or "").upper() for a in clean_attrs}
        _dim_m = re.search(r'(\d{2,3})[xX×](\d{2,3})', b.titulo or "")
        if _dim_m:
            w_cm, l_cm = _dim_m.group(1), _dim_m.group(2)
            if "WIDTH" not in existing_ids:
                clean_attrs.append({"id": "WIDTH", "value_name": f"{w_cm} cm"})
            if "LENGTH" not in existing_ids:
                clean_attrs.append({"id": "LENGTH", "value_name": f"{l_cm} cm"})
        # Altura del producto (dimensión vertical, no la planta)
        _ALTURA_DEFAULT = {"HIDROMASAJE": "65 cm", "BANERA": "60 cm", "RECEPTACULO": "15 cm"}
        existing_ids = {(a.get("id") or "").upper() for a in clean_attrs}
        if "HEIGHT" not in existing_ids:
            clean_attrs.append({"id": "HEIGHT", "value_name": _ALTURA_DEFAULT.get(tipo_prod, "65 cm")})

    # Filtrar clean_attrs según atributos válidos de la categoría.
    # _valid_attr_ids = None  → API falló, no se puede filtrar (no bloquear publicación)
    # _valid_attr_ids = set() → categoría sin atributos (ej. real estate) → limpiar todo
    # _valid_attr_ids = {...} → filtrar a esos IDs
    if _valid_attr_ids is not None:
        clean_attrs = [a for a in clean_attrs if (a.get("id") or "").upper() in _valid_attr_ids]

    # Título con keywords mínimas garantizadas (previene categorización errónea por ML)
    titulo_final = _forzar_keywords_titulo((b.titulo or "").strip(), tipo_prod)

    # Shipping: me2+gratis para productos de courier (hidromasajes, bañeras, accesorios);
    # not_specified para productos de gran porte (piscinas, módulos, etc.).
    # local_pick_up=True en todos: habilita "Retiro en persona" siempre.
    if tipo_prod in _TIPOS_CON_ENVIO_GRATIS:
        _shipping = {"mode": "me2", "free_shipping": True, "local_pick_up": True}
    else:
        _shipping = {"mode": "not_specified", "free_shipping": False, "local_pick_up": True}

    # Payload estándar (marketplace buy_it_now)
    # Si ML rechaza porque la categoría solo acepta classified, se reintenta automáticamente
    payload = {
        "title": titulo_final,
        "category_id": categoria,
        "price": b.precio or 0,
        "currency_id": "ARS",
        "available_quantity": b.cantidad or 1,
        "buying_mode": "buy_it_now",
        "listing_type_id": b.listing_type or "gold_special",
        "condition": b.condicion or "new",
        "pictures": [{"source": u} for u in fotos if u],
        "shipping": _shipping,
        # Nota: "warranty" fue eliminado — ML deprecated ese campo root (2026-08).
        # La garantía se publica como atributo WARRANTY_TYPE/WARRANTY_TIME en clean_attrs.
    }
    if clean_attrs:
        payload["attributes"] = clean_attrs

    async with httpx.AsyncClient(timeout=12) as hc:
        # Retry automático: si ML rechaza un campo root como deprecated, se elimina y se reintenta.
        for _dep_try in range(6):
            r = await hc.post(f"{ML_BASE}/items", json=payload, headers=_ml_headers(tok))
            if r.status_code in (200, 201):
                break
            if "deprecated" in r.text.lower():
                payload, _removed = _ml_strip_deprecated_root_field(payload, r.text)
                if _removed:
                    continue  # reintentar sin el campo deprecated
            break  # error no-deprecated: no reintentar aquí
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
                    "available_quantity": b.cantidad or 1,
                    "buying_mode": "classified",
                    "condition": b.condicion or "new",
                    "listing_type_id": "free",
                    "location": location,
                    "pictures": payload.get("pictures", []),
                    "shipping": {"local_pick_up": True},
                    # "warranty" eliminado — campo root deprecated en ML (2026-08)
                }
                # Para classified: solo incluir attrs explícitamente válidos para la categoría.
                # Si _valid_attr_ids es None (API falló) → NO enviar attrs: una categoría
                # de real estate/construcción rechazará BRAND, WARRANTY_*, MODEL, etc.
                _cl_attrs = [a for a in clean_attrs if _valid_attr_ids is not None and (a.get("id") or "").upper() in _valid_attr_ids]
                if _cl_attrs:
                    payload_cl["attributes"] = _cl_attrs

                # Probar listing types en orden.
                # listing_type_id es OBLIGATORIO para MLA413502 (cause_id 369 cuando falta).
                # No intentamos "sin-lt" porque ML lo rechaza de inmediato.
                _first_error: str = ""
                _last_error: str = ""
                for lt_cl in ["free", "gold_special", "classic"]:
                    payload_cl["listing_type_id"] = lt_cl
                    for intento in range(2):
                        # Auto-strip campos root deprecated antes de cada intento classified
                        for _cl_dep in range(4):
                            r = await hc.post(f"{ML_BASE}/items", json=payload_cl, headers=_ml_headers(tok))
                            if r.status_code in (200, 201):
                                break
                            if "deprecated" in r.text.lower():
                                payload_cl, _cl_rem = _ml_strip_deprecated_root_field(payload_cl, r.text)
                                if _cl_rem:
                                    continue
                            break
                        if r.status_code in (200, 201):
                            break
                        if not _first_error:
                            _first_error = f"[{lt_cl}] {r.status_code}: {r.text[:200]}"
                        _last_error = f"[{lt_cl}] {r.status_code}: {r.text[:200]}"
                        rt = r.text.upper()
                        if (
                            "NOT AVAILABLE FOR CATEGORY" in rt
                            or ("NOT AVAILABLE" in rt and "LISTING" in rt)
                            or "NULL FOR PARAMS" in rt
                            or "WAS NULL" in rt
                            or "BODY.REQUIRED" in rt
                            or "CAUSE_ID" in rt  # cualquier error estructural → probar siguiente
                        ):
                            break  # este lt_cl no funciona → probar el siguiente
                        if "TEMPORARILY" in rt or "TRY AGAIN" in rt:
                            await asyncio.sleep(10)
                        else:
                            break  # otro error — no reintentar con este lt_cl
                    if r.status_code in (200, 201):
                        break  # publicado → salir del loop de listing types
                # Si ningún listing type funcionó, mostrar primer Y último error para diagnóstico
                if r.status_code not in (200, 201):
                    if _first_error:
                        _err_msg = f"Classified listing falló. {_first_error}"
                        if _last_error and _last_error != _first_error:
                            _err_msg += f" | Último: {_last_error}"
                        return {"ok": False, "error": _err_msg, "error_tipo": "cuota_classified"}
                    rt = r.text.upper()
                    if "NOT AVAILABLE FOR CATEGORY" in rt or ("NOT AVAILABLE" in rt and "LISTING" in rt):
                        return {"ok": False, "error": _error_ml(r), "error_tipo": "cuota_classified"}

            # Auto-retry si la categoría predicha es claramente incorrecta para el tipo de producto.
            # Señales en el error 400: ML pide DOOR_TYPE (aberturas), IS_SUITABLE_FOR_INTERIOR
            # (aberturas/pisos), "Tipo de alimentación" (bombas) — ninguno aplica a jacuzzis/bañeras.
            if r.status_code not in (200, 201) and tipo_prod in _TIPOS_DIM_LIBRE:
                err_upper = r.text.upper()
                _WRONG_CAT_SIGNALS = [
                    "DOOR_TYPE", "IS_SUITABLE_FOR_INTERIOR", "IS_SUITABLE_FOR_EXTERIOR",
                    "TIPO DE ALIMENTACI",   # "Tipo de alimentación" truncado
                    "POTENCIA_",
                ]
                if any(sig in err_upper for sig in _WRONG_CAT_SIGNALS):
                    _ALT_TITULOS: dict = {
                        "HIDROMASAJE": [
                            "Jacuzzi bañera con jets hidromasaje",
                            "Bañera de hidromasaje acrílica con jets agua",
                            "Tina jacuzzi spa con bomba jets",
                        ],
                        "BANERA":      [
                            "Bañera individual de acrílico sanitario",
                            "Tina de baño acrílica",
                        ],
                        "RECEPTACULO": [
                            "Plato de ducha receptáculo acrílico",
                            "Receptáculo ducha bajo perfil acrílico",
                        ],
                    }
                    for alt_t in _ALT_TITULOS.get(tipo_prod, []):
                        new_cat = await _ml_categoria_sugerida(db, alt_t)
                        if new_cat and new_cat != payload["category_id"]:
                            payload["category_id"] = new_cat
                            r = await hc.post(f"{ML_BASE}/items", json=payload, headers=_ml_headers(tok))
                            if r.status_code in (200, 201):
                                break
                            await asyncio.sleep(0.3)

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


def _sincronizar_pub_ml(db: Session, b: BorradorML) -> None:
    """Crea o actualiza el registro PublicacionML cuando se publica un borrador.
    Nota: PublicacionML no tiene columna 'permalink' — se omite aquí.
    """
    if not b.item_id:
        return
    try:
        pub = db.query(PublicacionML).filter(PublicacionML.item_id == b.item_id).first()
        if pub:
            pub.titulo      = b.titulo      or pub.titulo
            pub.descripcion = b.descripcion or pub.descripcion or ""
            pub.precio      = b.precio      or pub.precio
            pub.estado_ml   = "active"
        else:
            db.add(PublicacionML(
                item_id     = b.item_id,
                titulo      = b.titulo      or "",
                descripcion = b.descripcion or "",
                precio      = b.precio      or 0,
                estado_ml   = "active",
            ))
    except Exception as _e_sync:
        import logging as _log
        _log.getLogger(__name__).warning(f"[sync_pub_ml] {b.item_id}: {_e_sync}")


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
        _sincronizar_pub_ml(db, b)
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
            _sincronizar_pub_ml(db, b)
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
        ctx_seo_ml(tipo_producto=tipo_label, modelo=base.modelo_nombre or "", descripcion_existente=desc_ctx)
        + f"\n\n════════════════════════════════════════════\n"
        f"TAREA: Generá {n} títulos alternativos para MercadoLibre.\n"
        f"════════════════════════════════════════════\n\n"
        f"Producto: {tipo_label}.{modelo_ctx}\n"
        f"Título actual (NO repetir): {base.titulo}\n"
        + (f"Descripción de referencia: {desc_ctx}\n\n" if desc_ctx else "\n")
        + f"Reglas adicionales:\n"
        f"- Los {n} títulos deben ser DISTINTOS entre sí y distintos del título actual\n"
        f"- Variá el orden de palabras clave y usá sinónimos válidos (pileta/piscina, modular/prefabricado)\n"
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
async def categoria_sugerida(titulo: str, tipo_producto: Optional[str] = None,
                             db: Session = Depends(get_db), x_api_key=Header(None),
                             current_user: Optional[Usuario] = Depends(get_current_user)):
    _auth(x_api_key, current_user)
    # Si el tipo de producto tiene categoría fija, usarla directamente (evita predictor de ML).
    # Esto previene que módulos/quinchos/etc. sean clasificados como "bloques de hormigón".
    cat = None
    nombre = None
    if tipo_producto:
        fija = CATEGORIAS_FIJAS.get(tipo_producto.upper())
        if fija:
            cat, nombre = fija
    if not cat:
        cat = await _ml_categoria_sugerida(db, titulo)
    if cat and not nombre:
        try:
            tok = await _ml_valid_token(db)
            async with httpx.AsyncClient(timeout=10) as c:
                rr = await c.get(f"{ML_BASE}/categories/{cat}", headers=_ml_headers(tok))
            if rr.status_code == 200:
                nombre = rr.json().get("name")
        except Exception:
            pass
    return {"categoria": cat, "nombre": nombre}


# ── Sets de imágenes ─────────────────────────────────────────────────────────
# Guardados en ConfiguracionSistema con categoria="imagen_set".
# valor = JSON {nombre, tipo_producto, urls}

@router.get("/api/ml/imagen-sets")
async def imagen_sets_list(tipo_producto: Optional[str] = None,
                           db: Session = Depends(get_db), x_api_key=Header(None),
                           current_user: Optional[Usuario] = Depends(get_current_user)):
    """Lista todos los sets de imágenes guardados, opcionalmente filtrados por tipo."""
    _auth(x_api_key, current_user)
    from database.models import ConfiguracionSistema
    rows = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.categoria == "imagen_set",
        ConfiguracionSistema.estado == "activa"
    ).order_by(ConfiguracionSistema.clave).all()
    sets = []
    for row in rows:
        try:
            data = json.loads(row.valor or "{}")
            if tipo_producto and data.get("tipo_producto") and data["tipo_producto"] != tipo_producto.upper():
                continue
            sets.append({
                "id": row.clave,
                "nombre": data.get("nombre", row.clave),
                "tipo_producto": data.get("tipo_producto", ""),
                "urls": data.get("urls", []),
            })
        except Exception:
            pass
    return {"sets": sets}


class ImagenSetIn(BaseModel):
    nombre: str
    tipo_producto: Optional[str] = None
    urls: list


@router.post("/api/ml/imagen-sets")
async def imagen_sets_save(body: ImagenSetIn, db: Session = Depends(get_db),
                           x_api_key=Header(None),
                           current_user: Optional[Usuario] = Depends(get_current_user)):
    """Crea o actualiza un set de imágenes."""
    _auth(x_api_key, current_user)
    from database.models import ConfiguracionSistema
    import re as _re
    # Clave estable basada en el nombre (slug)
    slug = _re.sub(r"[^a-z0-9_]", "_", body.nombre.lower().strip())[:40]
    clave = f"imgset_{slug}"
    data = {
        "nombre": body.nombre.strip(),
        "tipo_producto": (body.tipo_producto or "").upper() or None,
        "urls": [u.strip() for u in body.urls if u.strip()],
    }
    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if row:
        row.valor = json.dumps(data, ensure_ascii=False)
        row.estado = "activa"
    else:
        db.add(ConfiguracionSistema(
            clave=clave, valor=json.dumps(data, ensure_ascii=False),
            categoria="imagen_set", es_secreto=False, estado="activa"
        ))
    db.commit()
    return {"ok": True, "id": clave, "nombre": data["nombre"]}


@router.delete("/api/ml/imagen-sets/{set_id}")
async def imagen_sets_delete(set_id: str, db: Session = Depends(get_db),
                             x_api_key=Header(None),
                             current_user: Optional[Usuario] = Depends(get_current_user)):
    """Elimina un set de imágenes."""
    _auth(x_api_key, current_user)
    from database.models import ConfiguracionSistema
    row = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == set_id,
        ConfiguracionSistema.categoria == "imagen_set"
    ).first()
    if not row:
        raise HTTPException(404, "Set no encontrado")
    db.delete(row)
    db.commit()
    return {"ok": True}


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


@router.post("/api/ml/borradores/reparar-categorias")
async def reparar_categorias(
    db: Session = Depends(get_db), x_api_key=Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Aplica CATEGORIAS_FIJAS a todos los borradores con tipo de producto conocido.
    Si el tipo está en CATEGORIAS_FIJAS, sobreescribe la categoría con el valor correcto.
    Si el tipo no está (accesorio, repuesto, etc.), limpia solo categorías conocidas como inválidas.
    """
    _auth(x_api_key, current_user)

    # Categorías con IDs inexistentes en ML Argentina (jamás válidas)
    INVALIDAS_SIEMPRE = {"MLA9226", "MLA1647"}

    borradores = db.query(BorradorML).all()
    aplicados = 0
    limpiados = 0

    for b in borradores:
        tipo = (b.producto or "").upper()
        fija = CATEGORIAS_FIJAS.get(tipo)
        if fija:
            cat_id, cat_nombre = fija
            if b.categoria != cat_id:
                b.categoria = cat_id
                b.categoria_nombre = cat_nombre
                aplicados += 1
        elif b.categoria in INVALIDAS_SIEMPRE:
            b.categoria = ""
            b.categoria_nombre = ""
            limpiados += 1

    if aplicados or limpiados:
        db.commit()

    return {
        "ok": True,
        "categorias_aplicadas": aplicados,
        "invalidas_limpiadas": limpiados,
        "categorias_fijas": {k: v[0] for k, v in CATEGORIAS_FIJAS.items()},
        "mensaje": (
            f"{aplicados} borradores actualizados con categoría fija, "
            f"{limpiados} categorías inválidas limpiadas."
        ),
    }


@router.get("/api/ml/categorias/buscar")
async def buscar_categorias_ml(
    q: str,
    db: Session = Depends(get_db),
    x_api_key=Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Busca categorías reales de ML Argentina usando domain_discovery.
    Devuelve IDs y nombres verificados — nada se adivina.
    q: texto de búsqueda (ej: "hidromasaje", "pileta fibra", "casa prefabricada")
    """
    _auth(x_api_key, current_user)
    try:
        tok = await _ml_valid_token(db)
        async with httpx.AsyncClient(timeout=12) as hc:
            r = await hc.get(
                f"{ML_BASE}/sites/MLA/domain_discovery/search",
                params={"q": q, "limit": 8},
                headers=_ml_headers(tok),
            )
        if r.status_code != 200:
            return {"ok": False, "error": f"ML respondió {r.status_code}: {r.text[:200]}", "resultados": []}
        items = r.json() or []
        resultados = []
        for item in items:
            cat_id   = item.get("category_id", "")
            cat_name = item.get("category_name", "")
            # Verificar que la categoría existe y obtener nombre oficial
            if cat_id and not cat_name:
                try:
                    rr = await hc.get(f"{ML_BASE}/categories/{cat_id}", headers=_ml_headers(tok))
                    if rr.status_code == 200:
                        cat_name = rr.json().get("name", "")
                except Exception:
                    pass
            if cat_id:
                resultados.append({
                    "id":     cat_id,
                    "nombre": cat_name or item.get("domain_name", ""),
                    "dominio": item.get("domain_id", ""),
                })
        return {"ok": True, "resultados": resultados}
    except Exception as ex:
        return {"ok": False, "error": str(ex), "resultados": []}


@router.get("/api/ml/categorias/navegar")
async def navegar_categorias_ml(
    id: Optional[str] = None,
    x_api_key=Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Navega el árbol de categorías de ML Argentina.
    id=None → categorías de primer nivel (top-level).
    id=MLA1234 → hijos de esa categoría.
    Usa la API pública de ML (no requiere token, pero lo usa si está disponible).
    """
    _auth(x_api_key, current_user)
    try:
        # La API de categorías ML es pública — no requiere token
        async with httpx.AsyncClient(timeout=12) as hc:
            if id:
                r = await hc.get(f"{ML_BASE}/categories/{id}")
                if r.status_code != 200:
                    return {"ok": False, "error": f"Categoría {id}: {r.status_code}", "categorias": []}
                data  = r.json()
                hijos = data.get("children_categories") or []
                return {
                    "ok":        True,
                    "actual":    {"id": data.get("id"), "nombre": data.get("name")},
                    "categorias": [{"id": c["id"], "nombre": c["name"]} for c in hijos],
                    "es_hoja":   len(hijos) == 0,
                }
            else:
                r = await hc.get(f"{ML_BASE}/sites/MLA/categories")
                if r.status_code != 200:
                    return {"ok": False, "error": f"ML {r.status_code}", "categorias": []}
                cats = r.json() or []
                return {
                    "ok":        True,
                    "actual":    None,
                    "categorias": [{"id": c["id"], "nombre": c["name"]} for c in cats],
                    "es_hoja":   False,
                }
    except Exception as ex:
        return {"ok": False, "error": str(ex), "categorias": []}


@router.post("/api/ml/borradores/asignar-categoria")
async def asignar_categoria_bulk(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key=Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Asigna una categoría ML a todos los borradores que coincidan con el filtro.
    Body:
      categoria        ID de categoría ML (obligatorio)
      categoria_nombre Nombre descriptivo para mostrar
      ids              Lista de IDs de borradores (si se da, ignora filtro_producto)
      filtro_producto  Tipo de producto (ej: "HIDROMASAJE") — aplica a todos los de ese tipo
      filtro_estado    Solo borradores en este estado (default: todos excepto publicada)
    """
    _auth(x_api_key, current_user)
    data      = await request.json()
    categoria       = (data.get("categoria") or "").strip()
    categoria_nombre = (data.get("categoria_nombre") or "").strip()
    ids_lista       = data.get("ids")       # lista de int
    filtro_producto  = (data.get("filtro_producto") or "").strip().upper()
    filtro_estado    = (data.get("filtro_estado") or "").strip()

    if not categoria:
        raise HTTPException(400, "Debés indicar una categoría ML (campo 'categoria').")

    q = db.query(BorradorML).filter(BorradorML.estado != "publicada")
    if ids_lista:
        q = db.query(BorradorML).filter(BorradorML.id.in_(ids_lista))
    elif filtro_producto:
        q = q.filter(BorradorML.producto == filtro_producto)
    if filtro_estado:
        q = q.filter(BorradorML.estado == filtro_estado)

    borradores  = q.all()
    actualizados = len(borradores)
    for b in borradores:
        b.categoria       = categoria
        b.categoria_nombre = categoria_nombre
    if actualizados:
        db.commit()

    return {
        "ok":          True,
        "actualizados": actualizados,
        "categoria":    categoria,
        "categoria_nombre": categoria_nombre,
        "mensaje": f"{actualizados} borradores actualizados con categoría {categoria} ({categoria_nombre}).",
    }


@router.post("/api/ml/borradores/bulk-precio")
async def bulk_precio_borradores(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Cambia el precio de múltiples borradores en un solo paso."""
    _auth(x_api_key, current_user)
    data = await request.json()
    ids = data.get("ids", [])
    precio = data.get("precio")
    if not ids:
        raise HTTPException(400, "ids requerido")
    if precio is None or float(precio) <= 0:
        raise HTTPException(400, "precio inválido")
    precio = float(precio)
    actualizados = 0
    for bid in ids:
        b = db.query(BorradorML).filter(BorradorML.id == bid).first()
        if b:
            b.precio = precio
            actualizados += 1
    if actualizados:
        db.commit()
    return {"ok": True, "actualizados": actualizados}


@router.post("/api/ml/publicaciones/pausar")
async def pausar_publicaciones(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Pausa publicaciones en MercadoLibre y actualiza el estado local a 'pausada'."""
    _auth(x_api_key, current_user)
    data = await request.json()
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids requerido")

    tok = await _ml_valid_token(db)
    if not tok:
        raise HTTPException(401, "Sin token ML válido")
    hdrs = _ml_headers(tok)

    results: Dict[str, Any] = {"ok": 0, "error": 0, "detalles": []}
    async with httpx.AsyncClient(timeout=30) as hc:
        for bid in ids:
            b = db.query(BorradorML).filter(BorradorML.id == bid).first()
            if not b or not b.item_id:
                results["error"] += 1
                results["detalles"].append({"id": bid, "error": "Sin item_id — no publicada en ML"})
                continue
            try:
                r = await hc.put(
                    f"{ML_BASE}/items/{b.item_id}",
                    json={"status": "paused"},
                    headers=hdrs,
                )
                if r.is_success:
                    b.estado = "pausada"
                    results["ok"] += 1
                else:
                    err = f"ML {r.status_code}: {r.text[:120]}"
                    results["error"] += 1
                    results["detalles"].append({"id": bid, "item_id": b.item_id, "error": err})
            except Exception as ex:
                results["error"] += 1
                results["detalles"].append({"id": bid, "error": str(ex)[:120]})
    if results["ok"]:
        db.commit()
    return results


@router.post("/api/ml/publicaciones/activar")
async def activar_publicaciones(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Reactiva publicaciones pausadas en MercadoLibre (status → active)."""
    _auth(x_api_key, current_user)
    data = await request.json()
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids requerido")

    tok = await _ml_valid_token(db)
    if not tok:
        raise HTTPException(401, "Sin token ML válido")
    hdrs = _ml_headers(tok)

    results: Dict[str, Any] = {"ok": 0, "error": 0, "detalles": []}
    async with httpx.AsyncClient(timeout=30) as hc:
        for bid in ids:
            b = db.query(BorradorML).filter(BorradorML.id == bid).first()
            if not b or not b.item_id:
                results["error"] += 1
                results["detalles"].append({"id": bid, "error": "Sin item_id — no publicada en ML"})
                continue
            try:
                r = await hc.put(
                    f"{ML_BASE}/items/{b.item_id}",
                    json={"status": "active"},
                    headers=hdrs,
                )
                if r.is_success:
                    b.estado = "publicada"
                    results["ok"] += 1
                else:
                    err = f"ML {r.status_code}: {r.text[:120]}"
                    results["error"] += 1
                    results["detalles"].append({"id": bid, "item_id": b.item_id, "error": err})
            except Exception as ex:
                results["error"] += 1
                results["detalles"].append({"id": bid, "error": str(ex)[:120]})
    if results["ok"]:
        db.commit()
    return results


@router.post("/api/ml/publicaciones/cerrar-y-resetear")
async def cerrar_y_resetear(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Cierra publicaciones en ML (status → closed) y resetea el borrador CRM
    a estado 'borrador' con item_id/permalink limpios para poder republicar.
    Útil para classified listings donde ML no permite actualizar título/descripción
    via API — se cierra, se republicar desde el CRM con contenido nuevo.
    """
    _auth(x_api_key, current_user)
    data = await request.json()
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids requerido")

    tok = await _ml_valid_token(db)
    hdrs = _ml_headers(tok)

    results: Dict[str, Any] = {"ok": 0, "error": 0, "sin_ml": 0, "detalles": []}
    async with httpx.AsyncClient(timeout=30) as hc:
        for bid in ids:
            b = db.query(BorradorML).filter(BorradorML.id == bid).first()
            if not b:
                results["error"] += 1
                results["detalles"].append({"id": bid, "error": "No encontrado en CRM"})
                continue

            ml_cerrado = False
            ml_error = None

            if b.item_id:
                try:
                    r = await hc.put(
                        f"{ML_BASE}/items/{b.item_id}",
                        json={"status": "closed"},
                        headers=hdrs,
                    )
                    if r.is_success:
                        ml_cerrado = True
                    else:
                        ml_error = f"ML {r.status_code}: {r.text[:120]}"
                except Exception as ex:
                    ml_error = str(ex)[:120]
            else:
                results["sin_ml"] += 1  # ya era borrador, sin item_id

            # Resetear el borrador en CRM independientemente del resultado ML
            # (si ML falló el cierre, igual reseteamos localmente — el usuario
            # puede cerrar manualmente en ML si hace falta)
            b.item_id = None
            b.permalink = None
            b.estado = "borrador"
            b.error_msg = ""
            results["ok"] += 1
            if ml_error:
                results["detalles"].append({
                    "id": bid, "warn": f"Reseteado en CRM; ML no cerrado: {ml_error}"
                })

    db.commit()
    return results


@router.post("/api/ml/publicaciones/resincronizar")
async def resincronizar_desde_ml(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Re-importa desde MercadoLibre todas las publicaciones activas/pausadas que
    no existen en el CRM (útil para recuperar borradores eliminados accidentalmente).
    Crea un BorradorML mínimo por cada publicación encontrada en ML que no tenga
    un item_id correspondiente en la base local.
    """
    _auth(x_api_key, current_user)
    tok = await _ml_valid_token(db)
    hdrs = _ml_headers(tok)

    importados = 0
    ya_existentes = 0
    errores = 0
    detalles_error: list[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60) as hc:
        # Obtener user_id del token
        me_r = await hc.get(f"{ML_BASE}/users/me", headers=hdrs)
        if not me_r.is_success:
            raise HTTPException(502, f"No se pudo obtener usuario ML: {me_r.text[:200]}")
        user_id = me_r.json()["id"]

        # Recolectar todos los item_ids activos y pausados del vendedor
        all_items: list[tuple[str, str]] = []  # (item_id, status)
        for status in ("active", "paused"):
            offset = 0
            while True:
                r = await hc.get(
                    f"{ML_BASE}/users/{user_id}/items/search",
                    params={"status": status, "offset": offset, "limit": 100},
                    headers=hdrs,
                )
                if not r.is_success:
                    break
                data = r.json()
                batch = data.get("results", [])
                if not batch:
                    break
                all_items.extend((iid, status) for iid in batch)
                offset += len(batch)
                total = data.get("paging", {}).get("total", 0)
                if offset >= total:
                    break

        # Filtrar los que ya existen en el CRM
        known_ids = {
            b.item_id
            for b in db.query(BorradorML).filter(BorradorML.item_id.isnot(None)).all()
        }
        to_import = [(iid, st) for iid, st in all_items if iid not in known_ids]
        ya_existentes = len(all_items) - len(to_import)

        # Importar en lotes de 20 (límite de la API de items multi)
        status_map = {iid: st for iid, st in to_import}
        item_ids = [iid for iid, _ in to_import]
        for i in range(0, len(item_ids), 20):
            batch_ids = item_ids[i : i + 20]
            r = await hc.get(f"{ML_BASE}/items", params={"ids": ",".join(batch_ids)}, headers=hdrs)
            if not r.is_success:
                errores += len(batch_ids)
                detalles_error.append({"batch": batch_ids[:3], "error": f"ML {r.status_code}"})
                continue
            for entry in r.json():
                if entry.get("code") != 200:
                    errores += 1
                    detalles_error.append({"item_id": entry.get("body", {}).get("id"), "error": str(entry.get("code"))})
                    continue
                item = entry.get("body", {})
                iid = item.get("id", "")
                st = status_map.get(iid, "active")
                fotos = json.dumps([p["url"] for p in item.get("pictures", []) if p.get("url")])
                nuevo = BorradorML(
                    item_id=iid,
                    titulo=item.get("title", "")[:200],
                    precio=float(item.get("price") or 0),
                    descripcion="",
                    categoria=item.get("category_id", "")[:20],
                    estado="publicada" if st == "active" else "pausada",
                    producto=None,          # desconocido — el usuario puede asignarlo
                    fotos_json=fotos,
                    cantidad=int(item.get("available_quantity") or 1),
                    permalink=item.get("permalink", "")[:300],
                    origen="importado",
                )
                db.add(nuevo)
                importados += 1

        if importados:
            db.commit()

    return {
        "ok": True,
        "importados": importados,
        "ya_existentes": ya_existentes,
        "errores": errores,
        "detalles_error": detalles_error[:10],
    }


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
