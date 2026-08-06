"""
MercadoLibre — Biblioteca de imágenes, sets de fotos con reemplazo masivo,
renovación automática de publicaciones y auto-responder de preguntas con IA.
"""
import json
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import FotoML, SetFotosML, PublicacionML, Usuario, ConfiguracionSistema
from routers.configuracion import _require_config_access
from routers.mercadolibre import _ml_valid_token, _ml_headers, ML_BASE
from utils.ai_client import ai_complete
from utils.contexto_ecofiver import ctx_preguntas_ml

log = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory job tracker para tareas de aplicación masiva ───────────────────
_APPLY_JOBS: Dict[str, Dict[str, Any]] = {}


# ── Helpers de configuración ─────────────────────────────────────────────────

def _get_cfg(clave: str, db: Session, default: str = "") -> str:
    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    return row.valor if row and row.valor else default


def _set_cfg(clave: str, valor: str, db: Session):
    row = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    if row:
        row.valor = valor
    else:
        db.add(ConfiguracionSistema(clave=clave, valor=valor))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# BIBLIOTECA DE FOTOS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/ml/fotos/biblioteca")
async def subir_foto_biblioteca(
    file: UploadFile = File(...),
    nombre: str = Form(""),
    tipo_producto: str = Form(""),
    modelo: str = Form(""),
    tag: str = Form(""),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Sube una foto a los servidores de ML y la registra en la biblioteca central."""
    token = await _ml_valid_token(db)
    content = await file.read()
    content_type = file.content_type or "image/jpeg"

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{ML_BASE}/pictures/items/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (file.filename, content, content_type)},
        )

    if r.status_code not in (200, 201):
        raise HTTPException(r.status_code, f"Error ML al subir foto: {r.text[:300]}")

    data = r.json()
    # ML devuelve variaciones; tomamos la URL de mayor resolución
    variations = data.get("variations", [])
    if variations:
        url = max(variations, key=lambda v: v.get("width", 0) * v.get("height", 0)).get("url", "")
    else:
        url = data.get("url", "")

    if not url:
        raise HTTPException(502, "ML no devolvió URL de imagen")

    foto = FotoML(
        nombre=nombre.strip() or file.filename,
        url=url,
        tipo_producto=tipo_producto.strip() or None,
        modelo=modelo.strip() or None,
        tag=tag.strip() or None,
        orden=0,
    )
    db.add(foto)
    db.commit()
    db.refresh(foto)

    return {"ok": True, "id": foto.id, "url": foto.url, "nombre": foto.nombre}


@router.get("/api/ml/fotos/biblioteca")
async def listar_fotos_biblioteca(
    tipo_producto: Optional[str] = None,
    modelo: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lista fotos de la biblioteca con filtros opcionales."""
    q = db.query(FotoML)
    if tipo_producto:
        q = q.filter(FotoML.tipo_producto == tipo_producto)
    if modelo:
        q = q.filter(FotoML.modelo.ilike(f"%{modelo}%"))
    if tag:
        q = q.filter(FotoML.tag.ilike(f"%{tag}%"))

    fotos = q.order_by(FotoML.tipo_producto.asc(), FotoML.orden.asc(), FotoML.created_at.desc()).all()
    return [
        {
            "id": f.id,
            "nombre": f.nombre,
            "url": f.url,
            "tipo_producto": f.tipo_producto,
            "modelo": f.modelo,
            "tag": f.tag,
            "orden": f.orden,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in fotos
    ]


@router.patch("/api/ml/fotos/biblioteca/{foto_id}")
async def editar_foto_biblioteca(
    foto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Edita los metadatos de una foto (nombre, tipo, modelo, tag, orden)."""
    foto = db.query(FotoML).filter(FotoML.id == foto_id).first()
    if not foto:
        raise HTTPException(404, "Foto no encontrada")

    data = await request.json()
    for campo in ("nombre", "tipo_producto", "modelo", "tag", "orden"):
        if campo in data:
            val = data[campo]
            setattr(foto, campo, val if val != "" else None)
    db.commit()
    return {"ok": True}


@router.delete("/api/ml/fotos/biblioteca/{foto_id}")
async def eliminar_foto_biblioteca(
    foto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Elimina una foto de la biblioteca (y la quita de todos los sets que la incluyan)."""
    foto = db.query(FotoML).filter(FotoML.id == foto_id).first()
    if not foto:
        raise HTTPException(404, "Foto no encontrada")

    # Quitar de sets que la incluyan
    sets_con_foto = db.query(SetFotosML).all()
    for s in sets_con_foto:
        ids = json.loads(s.foto_ids_json or "[]")
        if foto_id in ids:
            ids = [i for i in ids if i != foto_id]
            s.foto_ids_json = json.dumps(ids)

    db.delete(foto)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# SETS DE FOTOS
# ─────────────────────────────────────────────────────────────────────────────

def _set_to_dict(s: SetFotosML, db: Session) -> dict:
    ids = json.loads(s.foto_ids_json or "[]")
    fotos_raw = db.query(FotoML).filter(FotoML.id.in_(ids)).all() if ids else []
    foto_map = {f.id: f for f in fotos_raw}
    fotos_ord = [foto_map[i] for i in ids if i in foto_map]
    return {
        "id": s.id,
        "nombre": s.nombre,
        "tipo_producto": s.tipo_producto,
        "modelo": s.modelo,
        "foto_ids": ids,
        "fotos": [
            {"id": f.id, "url": f.url, "nombre": f.nombre}
            for f in fotos_ord
        ],
        "preview_url": fotos_ord[0].url if fotos_ord else None,
        "total_fotos": len(fotos_ord),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/api/ml/fotos/sets")
async def listar_sets(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Lista todos los sets de fotos con sus imágenes y preview."""
    sets = db.query(SetFotosML).order_by(SetFotosML.created_at.desc()).all()
    return [_set_to_dict(s, db) for s in sets]


@router.post("/api/ml/fotos/sets")
async def crear_set(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Crea un nuevo set de fotos."""
    data = await request.json()
    s = SetFotosML(
        nombre=(data.get("nombre") or "").strip() or "Set sin nombre",
        tipo_producto=data.get("tipo_producto") or None,
        modelo=data.get("modelo") or None,
        foto_ids_json=json.dumps(data.get("foto_ids", [])),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"ok": True, "id": s.id}


@router.put("/api/ml/fotos/sets/{set_id}")
async def editar_set(
    set_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Edita un set existente (nombre, tipo, modelo, foto_ids)."""
    s = db.query(SetFotosML).filter(SetFotosML.id == set_id).first()
    if not s:
        raise HTTPException(404, "Set no encontrado")

    data = await request.json()
    if "nombre" in data:
        s.nombre = (data["nombre"] or "").strip() or s.nombre
    if "tipo_producto" in data:
        s.tipo_producto = data["tipo_producto"] or None
    if "modelo" in data:
        s.modelo = data["modelo"] or None
    if "foto_ids" in data:
        s.foto_ids_json = json.dumps(data["foto_ids"])
    db.commit()
    return {"ok": True}


@router.delete("/api/ml/fotos/sets/{set_id}")
async def eliminar_set(
    set_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Elimina un set de fotos (no afecta las fotos individuales de la biblioteca)."""
    s = db.query(SetFotosML).filter(SetFotosML.id == set_id).first()
    if not s:
        raise HTTPException(404, "Set no encontrado")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# APLICAR SET A PUBLICACIONES (tarea de fondo)
# ─────────────────────────────────────────────────────────────────────────────

async def _aplicar_set_bg(
    job_id: str,
    token: str,
    urls: List[str],
    item_ids: List[str],
    modo: str,
):
    """
    Worker de fondo: aplica el set de fotos a cada publicación.
    Modos:
      - reemplazar    → reemplaza TODAS las fotos con las del set
      - agregar_inicio → antepone las fotos del set a las existentes
      - agregar_fin   → agrega las fotos del set al final de las existentes
    """
    job = _APPLY_JOBS[job_id]
    job["total"] = len(item_ids)
    job["procesados"] = 0
    job["ok"] = 0
    job["errores"] = []
    job["actual"] = ""

    for item_id in item_ids:
        job["actual"] = item_id
        try:
            if modo in ("agregar_inicio", "agregar_fin"):
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(
                        f"{ML_BASE}/items/{item_id}",
                        headers=_ml_headers(token),
                        params={"attributes": "pictures"},
                    )
                existing_urls = []
                if r.status_code == 200:
                    existing_urls = [
                        p.get("url") for p in r.json().get("pictures", []) if p.get("url")
                    ]

                if modo == "agregar_inicio":
                    combined = urls + existing_urls
                else:
                    combined = existing_urls + urls
            else:
                combined = list(urls)

            # Deduplicar preservando orden
            seen: set = set()
            final_urls: List[str] = []
            for u in combined:
                if u not in seen:
                    seen.add(u)
                    final_urls.append(u)

            pictures = [{"source": u} for u in final_urls[:12]]  # ML: máximo 12 fotos

            async with httpx.AsyncClient(timeout=15) as c:
                r2 = await c.put(
                    f"{ML_BASE}/items/{item_id}/pictures",
                    headers=_ml_headers(token),
                    json={"pictures": pictures},
                )

            if r2.status_code in (200, 201):
                job["ok"] += 1
            else:
                job["errores"].append(f"{item_id}: {r2.text[:100]}")

        except Exception as e:
            job["errores"].append(f"{item_id}: {e}")

        job["procesados"] += 1
        await asyncio.sleep(0.6)  # respetar rate limit de ML

    job["status"] = "done"
    log.info(f"[SET-APPLY {job_id}] {job['ok']}/{job['total']} OK, {len(job['errores'])} errores")


@router.post("/api/ml/fotos/sets/{set_id}/aplicar")
async def aplicar_set(
    set_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """
    Aplica masivamente el set de fotos a publicaciones activas de ML.

    Body JSON:
      - modo: 'reemplazar' | 'agregar_inicio' | 'agregar_fin'
      - filtro_producto: 'PISCINA' | 'MODULO' | … (vacío = todos)
      - item_ids: lista explícita de item_ids (vacío = todos activos del filtro)
    """
    s = db.query(SetFotosML).filter(SetFotosML.id == set_id).first()
    if not s:
        raise HTTPException(404, "Set no encontrado")

    ids = json.loads(s.foto_ids_json or "[]")
    if not ids:
        raise HTTPException(400, "El set no tiene fotos — agregá fotos primero")

    fotos = db.query(FotoML).filter(FotoML.id.in_(ids)).all()
    foto_map = {f.id: f for f in fotos}
    urls = [foto_map[i].url for i in ids if i in foto_map]

    if not urls:
        raise HTTPException(400, "No se encontraron URLs de fotos en este set")

    data = await request.json()
    modo = data.get("modo", "reemplazar")
    if modo not in ("reemplazar", "agregar_inicio", "agregar_fin"):
        raise HTTPException(400, f"Modo inválido: {modo}")

    filtro_producto = (data.get("filtro_producto") or "").strip()
    item_ids_manual = data.get("item_ids", [])

    token = await _ml_valid_token(db)

    if item_ids_manual:
        item_ids = [str(i) for i in item_ids_manual]
    else:
        q = db.query(PublicacionML).filter(PublicacionML.estado_ml == "active")
        if filtro_producto:
            q = q.filter(PublicacionML.producto == filtro_producto)
        item_ids = [p.item_id for p in q.all()]

    if not item_ids:
        raise HTTPException(400, "No hay publicaciones activas que coincidan con el filtro")

    job_id = str(uuid.uuid4())
    _APPLY_JOBS[job_id] = {
        "status": "running",
        "total": len(item_ids),
        "procesados": 0,
        "ok": 0,
        "errores": [],
        "actual": "",
    }

    background_tasks.add_task(_aplicar_set_bg, job_id, token, urls, item_ids, modo)
    return {"ok": True, "job_id": job_id, "total": len(item_ids)}


@router.get("/api/ml/fotos/sets/jobs/{job_id}")
async def estado_job_aplicar(job_id: str):
    """Consulta el estado de un job de aplicación masiva de fotos."""
    job = _APPLY_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


# ─────────────────────────────────────────────────────────────────────────────
# RENOVACIÓN AUTOMÁTICA DE PUBLICACIONES
# ─────────────────────────────────────────────────────────────────────────────

async def _renovar_vencimientos_core():
    """
    Revisa publicaciones con renovacion_auto=True en nuestra DB.
    - Si están 'paused' en ML → las activa (PUT status: active)
    - Si están 'closed' en ML → intenta relisting
    Se llama desde el endpoint manual Y desde el scheduler nocturno.
    """
    from database.database import SessionLocal
    db = SessionLocal()
    try:
        token = await _ml_valid_token(db)
        pubs = db.query(PublicacionML).filter(PublicacionML.renovacion_auto == True).all()

        if not pubs:
            return {"renovadas": 0, "errores": [], "sin_cambios": 0}

        renovadas = 0
        sin_cambios = 0
        errores: List[str] = []

        for pub in pubs:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(
                        f"{ML_BASE}/items/{pub.item_id}",
                        headers=_ml_headers(token),
                        params={"attributes": "id,status,price"},
                    )
                if r.status_code != 200:
                    errores.append(f"{pub.item_id}: fetch error {r.status_code}")
                    continue

                item = r.json()
                estado_ml = item.get("status", "")

                if estado_ml == "active":
                    sin_cambios += 1
                    continue

                elif estado_ml == "paused":
                    async with httpx.AsyncClient(timeout=10) as c:
                        r2 = await c.put(
                            f"{ML_BASE}/items/{pub.item_id}",
                            headers=_ml_headers(token),
                            json={"status": "active"},
                        )
                    if r2.status_code in (200, 201):
                        renovadas += 1
                        pub.estado_ml = "active"
                        db.commit()
                        log.info(f"[RENOVAR] Activada: {pub.item_id}")
                    else:
                        errores.append(f"{pub.item_id}(activate): {r2.text[:100]}")

                elif estado_ml == "closed":
                    precio = pub.precio or item.get("price", 0)
                    async with httpx.AsyncClient(timeout=10) as c:
                        r2 = await c.post(
                            f"{ML_BASE}/items/{pub.item_id}/relist",
                            headers=_ml_headers(token),
                            json={"listing_type_id": "gold_special", "quantity": 1, "price": precio},
                        )
                    if r2.status_code in (200, 201):
                        renovadas += 1
                        pub.estado_ml = "active"
                        db.commit()
                        log.info(f"[RENOVAR] Relisted: {pub.item_id}")
                    else:
                        errores.append(f"{pub.item_id}(relist): {r2.text[:100]}")

                await asyncio.sleep(0.4)

            except Exception as e:
                errores.append(f"{pub.item_id}: {e}")

        log.info(f"[RENOVAR] {renovadas} renovadas, {sin_cambios} ya activas, {len(errores)} errores")
        return {"renovadas": renovadas, "sin_cambios": sin_cambios, "errores": errores}

    finally:
        db.close()


@router.post("/api/ml/renovar-vencimientos")
async def renovar_vencimientos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Dispara manualmente la renovación de publicaciones con renovacion_auto=True."""
    resultado = await _renovar_vencimientos_core()
    return {"ok": True, **resultado}


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-RESPONDER DE PREGUNTAS CON IA
# ─────────────────────────────────────────────────────────────────────────────

async def _auto_responder_preguntas_job():
    """
    Job del scheduler: responde automáticamente preguntas sin responder en ML.
    Solo actúa si 'ml_auto_responder_activo' = 'true' en ConfiguracionSistema.
    Corre cada 20 minutos vía APScheduler.
    """
    from database.database import SessionLocal
    db = SessionLocal()
    try:
        activo = _get_cfg("ml_auto_responder_activo", db, "false")
        if activo != "true":
            return

        token = await _ml_valid_token(db)

        # Obtener user_id ML (cacheado en config)
        user_id = _get_cfg("ml_user_id", db)
        if not user_id:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{ML_BASE}/users/me", headers=_ml_headers(token))
            if r.status_code == 200:
                user_id = str(r.json().get("id", ""))
                _set_cfg("ml_user_id", user_id, db)
        if not user_id:
            log.warning("[AUTO-RESP] No hay ml_user_id configurado")
            return

        # Traer preguntas sin responder (máx 20 por ciclo)
        params = {"seller_id": user_id, "status": "UNANSWERED", "limit": 20, "sort_fields": "date_created"}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{ML_BASE}/questions/search", headers=_ml_headers(token), params=params)

        if r.status_code != 200:
            log.warning(f"[AUTO-RESP] Error fetching questions: {r.status_code} {r.text[:100]}")
            return

        preguntas = r.json().get("questions", [])
        if not preguntas:
            return

        # Enriquecer con títulos de item (batch)
        item_ids = list({p.get("item_id") for p in preguntas if p.get("item_id")})
        titulos: Dict[str, str] = {}
        if item_ids:
            async with httpx.AsyncClient(timeout=10) as c:
                r2 = await c.get(
                    f"{ML_BASE}/items",
                    headers=_ml_headers(token),
                    params={"ids": ",".join(item_ids[:20]), "attributes": "id,title"},
                )
            if r2.status_code == 200:
                for item in r2.json():
                    if isinstance(item, dict):
                        body = item.get("body", item)
                        titulos[body.get("id", "")] = body.get("title", "")

        respondidas = 0
        for p in preguntas:
            qid = p.get("id")
            texto = (p.get("text") or "").strip()
            item_titulo = titulos.get(p.get("item_id", ""), "")

            if not texto or not qid:
                continue

            prompt = ctx_preguntas_ml(
                item_titulo=item_titulo or "producto EcoFiver",
                pregunta=texto,
            )

            try:
                respuesta = await ai_complete(db, prompt, max_tokens=400, temperature=0.6)
                respuesta = " ".join(respuesta.split())
            except Exception as e:
                log.warning(f"[AUTO-RESP] Error IA para pregunta {qid}: {e}")
                continue

            body = {"question_id": qid, "text": respuesta[:2000]}
            async with httpx.AsyncClient(timeout=10) as c:
                r3 = await c.post(f"{ML_BASE}/answers", headers=_ml_headers(token), json=body)

            if r3.status_code in (200, 201):
                respondidas += 1
                log.info(f"[AUTO-RESP] Respondida pregunta {qid} para '{item_titulo[:40]}'")
            else:
                log.warning(f"[AUTO-RESP] Error al responder {qid}: {r3.text[:100]}")

            await asyncio.sleep(1.5)  # rate limiting

        log.info(f"[AUTO-RESP] Ciclo completado: {respondidas}/{len(preguntas)} respondidas")

    except Exception as e:
        log.error(f"[AUTO-RESP] Error en job: {e}")
    finally:
        db.close()


@router.get("/api/ml/auto-responder/config")
async def get_auto_responder_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Devuelve el estado actual del auto-responder de preguntas."""
    return {
        "activo": _get_cfg("ml_auto_responder_activo", db, "false") == "true",
    }


@router.put("/api/ml/auto-responder/config")
async def set_auto_responder_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_require_config_access),
):
    """Activa o desactiva el auto-responder de preguntas con IA."""
    data = await request.json()
    activo = bool(data.get("activo", False))
    _set_cfg("ml_auto_responder_activo", "true" if activo else "false", db)
    log.info(f"[AUTO-RESP] {'Activado' if activo else 'Desactivado'} por usuario")
    return {"ok": True, "activo": activo}
