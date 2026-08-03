"""
Módulo — Integraciones IA
Recibe webhooks de agentes externos (Melanie, futuros) y los procesa de forma
transaccional: crea/actualiza Lead, genera TareaLlamadaConfirmacion y notifica asesores.
Sin modificar ningún módulo ni lógica existente del CRM.
"""
import os
import random
import logging
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Lead, SolicitudMelanie, TareaLlamadaConfirmacion, Usuario
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

# Chars para código de validación — sin O, I, 0, 1 (ambiguos)
_CODIGO_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_PROD_MAP = {
    "piscina": "PISCINA",
    "piscinas": "PISCINA",
    "módulo": "MODULO",
    "modulo": "MODULO",
    "módulos": "MODULO",
    "modulos": "MODULO",
    "vivienda": "MODULO",
    "combo": "COMBO",
}


# ─── AUTENTICACIÓN MELANIE ────────────────────────────────────────────────────

def _get_melanie_key(db: Session) -> str:
    try:
        from routers.configuracion import get_config_value
        key = get_config_value("melanie_api_key", db)
        if key:
            return key
    except Exception:
        pass
    return os.getenv("MELANIE_API_KEY", "melanie-webhook-key-2024")


def _require_melanie_auth(authorization: Optional[str], db: Session) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization Bearer requerida")
    token = authorization.split(" ", 1)[1].strip()
    expected = _get_melanie_key(db)
    if token != expected:
        raise HTTPException(401, "API Key inválida")


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _generar_codigo(db: Session) -> str:
    for _ in range(200):
        codigo = "".join(random.choices(_CODIGO_CHARS, k=4))
        if not db.query(TareaLlamadaConfirmacion).filter_by(
            codigo_validacion=codigo
        ).first():
            return codigo
    raise RuntimeError("No se pudo generar código único — espacio de códigos agotado")


def _tarea_dict(t: TareaLlamadaConfirmacion, s: SolicitudMelanie = None, lead: Lead = None) -> dict:
    nombre_cliente = ""
    if lead:
        nombre_cliente = lead.nombre
    elif s:
        nombre_cliente = f"{s.nombre} {s.apellido}".strip()

    return {
        "id": t.id,
        "codigo_validacion": t.codigo_validacion,
        "estado": t.estado,
        "prioridad": t.prioridad,
        "fecha_preferida": t.fecha_preferida,
        "horario_preferido": t.horario_preferido,
        "notas_asesor": t.notas_asesor,
        "lead_id": t.lead_id,
        "solicitud_id": t.solicitud_id,
        "nombre_cliente": nombre_cliente,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _solicitud_dict(s: SolicitudMelanie) -> dict:
    tarea = s.tarea
    return {
        "id": s.id,
        "nombre": f"{s.nombre} {s.apellido}".strip(),
        "telefono": s.telefono,
        "provincia": s.provincia,
        "localidad": s.localidad,
        "producto": s.producto,
        "modelo": s.modelo,
        "plan": s.plan,
        "estado_terreno": s.estado_terreno,
        "fecha_preferida": s.fecha_preferida,
        "horario_preferido": s.horario_preferido,
        "resumen": s.resumen_melanie or "",
        "agente_origen": s.agente_origen,
        "estado_procesamiento": s.estado_procesamiento,
        "lead_id": s.lead_id,
        "lead_nombre": s.lead.nombre if s.lead else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        # tarea vinculada
        "tarea_id": tarea.id if tarea else None,
        "codigo_validacion": tarea.codigo_validacion if tarea else None,
        "tarea_estado": tarea.estado if tarea else "SIN_TAREA",
        "tarea_prioridad": tarea.prioridad if tarea else None,
        "tarea_notas": tarea.notas_asesor if tarea else "",
    }


# ─── HTML PANEL ───────────────────────────────────────────────────────────────

@router.get("/integraciones", response_class=HTMLResponse)
async def integraciones_page(
    request: Request,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(user)
    return templates.TemplateResponse("integraciones.html", {
        "request": request,
        "user": user,
        "roles": roles,
    })


# ─── API LISTA SOLICITUDES ───────────────────────────────────────────────────

@router.get("/api/integraciones/melanie/solicitudes")
async def api_solicitudes(
    estado: Optional[str] = None,
    limit: int = 200,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    q = db.query(SolicitudMelanie).order_by(SolicitudMelanie.created_at.desc())
    if estado:
        # filtrar por estado de tarea
        q = q.join(TareaLlamadaConfirmacion,
                   TareaLlamadaConfirmacion.solicitud_id == SolicitudMelanie.id,
                   isouter=True)
        if estado == "SIN_TAREA":
            q = q.filter(TareaLlamadaConfirmacion.id == None)
        else:
            q = q.filter(TareaLlamadaConfirmacion.estado == estado)
    return [_solicitud_dict(s) for s in q.limit(limit).all()]


@router.get("/api/integraciones/melanie/stats")
async def api_stats(
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    total = db.query(SolicitudMelanie).count()
    pendientes = db.query(TareaLlamadaConfirmacion).filter_by(estado="PENDIENTE").count()
    en_curso   = db.query(TareaLlamadaConfirmacion).filter_by(estado="EN_CURSO").count()
    completadas= db.query(TareaLlamadaConfirmacion).filter_by(estado="COMPLETADA").count()
    canceladas = db.query(TareaLlamadaConfirmacion).filter_by(estado="CANCELADA").count()
    return {
        "total_solicitudes": total,
        "pendientes": pendientes,
        "en_curso": en_curso,
        "completadas": completadas,
        "canceladas": canceladas,
    }


# ─── API DETALLE SOLICITUD ───────────────────────────────────────────────────

@router.get("/api/integraciones/melanie/solicitudes/{sol_id}")
async def api_solicitud_detail(
    sol_id: int,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    s = db.query(SolicitudMelanie).filter(SolicitudMelanie.id == sol_id).first()
    if not s:
        raise HTTPException(404, "Solicitud no encontrada")
    result = _solicitud_dict(s)
    result["historial_chat"] = s.historial_chat or []
    result["datos_extra"] = s.datos_extra or {}
    return result


# ─── API ACTUALIZAR TAREA ────────────────────────────────────────────────────

class UpdateTareaReq(BaseModel):
    estado: Optional[str] = None        # PENDIENTE | EN_CURSO | COMPLETADA | CANCELADA
    prioridad: Optional[str] = None     # NORMAL | ALTA | URGENTE
    notas_asesor: Optional[str] = None


@router.patch("/api/integraciones/melanie/tareas/{tarea_id}")
async def api_update_tarea(
    tarea_id: int,
    body: UpdateTareaReq,
    user: Usuario = Depends(require_auth),
    db: Session = Depends(get_db),
):
    estados_validos = {"PENDIENTE", "EN_CURSO", "COMPLETADA", "CANCELADA"}
    prioridades_validas = {"NORMAL", "ALTA", "URGENTE"}

    t = db.query(TareaLlamadaConfirmacion).filter(
        TareaLlamadaConfirmacion.id == tarea_id
    ).first()
    if not t:
        raise HTTPException(404, "Tarea no encontrada")

    if body.estado is not None:
        if body.estado not in estados_validos:
            raise HTTPException(400, f"Estado inválido. Válidos: {estados_validos}")
        t.estado = body.estado
        if body.estado == "EN_CURSO":
            t.asesor_id = user.id

    if body.prioridad is not None:
        if body.prioridad not in prioridades_validas:
            raise HTTPException(400, f"Prioridad inválida. Válidas: {prioridades_validas}")
        t.prioridad = body.prioridad

    if body.notas_asesor is not None:
        t.notas_asesor = body.notas_asesor

    db.commit()
    return {"ok": True, "tarea": _tarea_dict(t, t.solicitud, t.lead)}


# ─── WEBHOOK MELANIE ─────────────────────────────────────────────────────────

class WebhookMelanieReq(BaseModel):
    nombre: str
    apellido: Optional[str] = ""
    telefono: str
    provincia: Optional[str] = ""
    localidad: Optional[str] = ""
    producto: Optional[str] = ""
    modelo: Optional[str] = ""
    plan: Optional[str] = ""
    estado_terreno: Optional[str] = ""
    fecha_preferida: Optional[str] = ""
    horario_preferido: Optional[str] = ""
    resumen: Optional[str] = ""
    historial_chat: Optional[List[Any]] = []
    datos_extra: Optional[dict] = {}


@router.post("/api/integraciones/melanie/confirmacion")
async def webhook_melanie(
    body: WebhookMelanieReq,
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Recibe solicitud de Llamada de Confirmación de Melanie.
    Autentica via Bearer token, crea/actualiza Lead, registra la solicitud,
    genera tarea y código de validación, notifica asesores.
    Idempotente: si ya existe tarea PENDIENTE para ese teléfono, devuelve la existente.
    """
    _require_melanie_auth(authorization, db)
    ip_origen = request.client.host if request.client else "unknown"
    nombre_completo = f"{body.nombre} {body.apellido}".strip()

    logger.info(
        f"[MELANIE] Webhook — tel={body.telefono} "
        f"prod={body.producto} fecha={body.fecha_preferida}"
    )

    try:
        # 1. Buscar lead por teléfono
        lead = db.query(Lead).filter(Lead.telefono == body.telefono).first()
        lead_es_nuevo = lead is None

        if lead_es_nuevo:
            prod_crm = _PROD_MAP.get((body.producto or "").lower(), "SIN_DEFINIR")
            nota_base = "\n".join(filter(None, [
                f"Provincia: {body.provincia}" if body.provincia else "",
                f"Plan: {body.plan}" if body.plan else "",
                f"Estado terreno: {body.estado_terreno}" if body.estado_terreno else "",
                f"Resumen Melanie: {(body.resumen or '')[:300]}" if body.resumen else "",
            ]))
            lead = Lead(
                nombre=nombre_completo,
                telefono=body.telefono,
                localidad=body.localidad or "",
                producto_interes=prod_crm,
                modelo_especifico=body.modelo or "",
                origen="WHATSAPP",
                agente_asignado="melanie",
                estado="NUEVO",
                notas=nota_base,
                modo_atencion="humano",
            )
            db.add(lead)
            db.flush()
        else:
            # Completar campos vacíos sin pisar datos existentes
            if body.localidad and not lead.localidad:
                lead.localidad = body.localidad
            if body.modelo and not lead.modelo_especifico:
                lead.modelo_especifico = body.modelo

        # 2. Idempotencia — ¿ya hay tarea PENDIENTE para este lead?
        tarea_existente = (
            db.query(TareaLlamadaConfirmacion)
            .filter(
                TareaLlamadaConfirmacion.lead_id == lead.id,
                TareaLlamadaConfirmacion.estado == "PENDIENTE",
            )
            .first()
        )
        if tarea_existente:
            logger.info(
                f"[MELANIE] Idempotente — lead={lead.id} "
                f"tarea={tarea_existente.id} código={tarea_existente.codigo_validacion}"
            )
            db.commit()
            return {
                "ok": True,
                "idempotente": True,
                "codigo_validacion": tarea_existente.codigo_validacion,
                "tarea_id": tarea_existente.id,
                "lead_id": lead.id,
                "mensaje": "Ya existe una solicitud pendiente para este cliente",
            }

        # 3. Registrar solicitud
        solicitud = SolicitudMelanie(
            nombre=body.nombre,
            apellido=body.apellido or "",
            telefono=body.telefono,
            provincia=body.provincia or "",
            localidad=body.localidad or "",
            producto=body.producto or "",
            modelo=body.modelo or "",
            plan=body.plan or "",
            estado_terreno=body.estado_terreno or "",
            fecha_preferida=body.fecha_preferida or "",
            horario_preferido=body.horario_preferido or "",
            resumen_melanie=body.resumen or "",
            historial_chat=body.historial_chat or [],
            agente_origen="melanie",
            datos_extra=body.datos_extra or {},
            lead_id=lead.id,
            ip_origen=ip_origen,
            estado_procesamiento="procesando",
        )
        db.add(solicitud)
        db.flush()

        # 4. Código de validación único
        codigo = _generar_codigo(db)

        # 5. Tarea de Llamada de Confirmación
        tarea = TareaLlamadaConfirmacion(
            lead_id=lead.id,
            solicitud_id=solicitud.id,
            codigo_validacion=codigo,
            estado="PENDIENTE",
            prioridad="NORMAL",
            fecha_preferida=body.fecha_preferida or "",
            horario_preferido=body.horario_preferido or "",
        )
        db.add(tarea)
        db.flush()

        solicitud.estado_procesamiento = "procesado"
        db.commit()

        logger.info(
            f"[MELANIE] ✅ lead={lead.id} ({'nuevo' if lead_es_nuevo else 'existente'}) "
            f"solicitud={solicitud.id} tarea={tarea.id} código={codigo}"
        )

        # 6. Notificación interna (no bloquea la respuesta si falla)
        try:
            from routers.notificaciones import notificar_todos
            prod_disp = body.producto or "Consulta"
            mod_disp  = f" · {body.modelo}" if body.modelo else ""
            horario   = f" {body.horario_preferido}" if body.horario_preferido else ""
            fecha_str = body.fecha_preferida or "a confirmar"
            notificar_todos(
                db=db,
                titulo=f"📞 Llamada de Confirmación — {nombre_completo}",
                mensaje=(
                    f"{prod_disp}{mod_disp} · "
                    f"{fecha_str}{horario} · "
                    f"Código: {codigo}"
                ),
                tipo="LEAD",
                referencia_id=lead.id,
                referencia_tipo="lead",
                url=f"/integraciones?solicitud={solicitud.id}",
            )
        except Exception as exc:
            logger.warning(f"[MELANIE] Notificación falló (no crítico): {exc}")

        return {
            "ok": True,
            "idempotente": False,
            "codigo_validacion": codigo,
            "tarea_id": tarea.id,
            "lead_id": lead.id,
            "lead_nuevo": lead_es_nuevo,
            "mensaje": "Solicitud registrada correctamente",
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(f"[MELANIE] Error crítico: {exc}", exc_info=True)
        raise HTTPException(500, f"Error procesando solicitud: {str(exc)[:120]}")


# ─── WEBHOOK META DIRECTO (WABA de Melanie) ──────────────────────────────────

def _get_melanie_verify_token(db: Session) -> str:
    try:
        from routers.configuracion import get_config_value
        t = get_config_value("melanie_wa_verify_token", db)
        if t:
            return t
    except Exception:
        pass
    return os.getenv("MELANIE_WA_VERIFY_TOKEN", "melanie_verify_2026")


@router.get("/webhook/melanie")
async def melanie_meta_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    """Verificación del webhook de Meta para la WABA de Melanie."""
    expected = _get_melanie_verify_token(db)
    if hub_mode == "subscribe" and hub_verify_token == expected:
        logger.info("[WA/Melanie] Webhook verificado correctamente por Meta")
        return PlainTextResponse(hub_challenge)
    logger.warning("[WA/Melanie] Verificación fallida — token incorrecto")
    raise HTTPException(403, "Token de verificación inválido")


@router.post("/webhook/melanie")
async def melanie_meta_webhook_receive(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Recibe eventos de WhatsApp de la WABA de Melanie directamente desde Meta.
    Por cada mensaje nuevo registra (o reutiliza) un Lead + SolicitudMelanie
    en el módulo de integraciones. Idempotente por teléfono.
    Meta AI responde al usuario — este endpoint solo captura el contacto.
    """
    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    try:
        entry   = body["entry"][0]
        change  = entry["changes"][0]["value"]
        if "messages" not in change:
            return {"status": "no_messages"}

        message  = change["messages"][0]
        phone    = message["from"]
        msg_type = message.get("type", "")

        if msg_type == "text":
            texto = message["text"]["body"]
        elif msg_type == "audio":
            texto = "[Mensaje de voz]"
        elif msg_type == "image":
            caption = (message.get("image") or {}).get("caption", "")
            texto = f"[Imagen] {caption}".strip() if caption else "[Imagen recibida]"
        else:
            texto = f"[Mensaje tipo {msg_type}]"

    except (KeyError, IndexError):
        return {"status": "ignored"}

    logger.info(f"[WA/Melanie] Webhook — tel={phone} tipo={msg_type}")

    try:
        # Buscar lead por teléfono
        lead = db.query(Lead).filter(Lead.telefono == phone).first()
        lead_es_nuevo = lead is None

        if lead_es_nuevo:
            lead = Lead(
                nombre="Contacto Melanie",
                telefono=phone,
                origen="WHATSAPP",
                agente_asignado="melanie",
                estado="NUEVO",
                notas=f"Primer mensaje: {texto[:300]}",
                modo_atencion="humano",
            )
            db.add(lead)
            db.flush()

        # Idempotencia — no crear nueva tarea si ya hay una PENDIENTE
        tarea_existente = (
            db.query(TareaLlamadaConfirmacion)
            .filter(
                TareaLlamadaConfirmacion.lead_id == lead.id,
                TareaLlamadaConfirmacion.estado == "PENDIENTE",
            )
            .first()
        )
        if tarea_existente:
            db.commit()
            logger.info(f"[WA/Melanie] Idempotente — lead={lead.id} tarea={tarea_existente.id}")
            return {"status": "ok"}

        solicitud = SolicitudMelanie(
            nombre="Contacto Melanie",
            apellido="",
            telefono=phone,
            resumen_melanie=texto[:300],
            agente_origen="melanie",
            lead_id=lead.id,
            estado_procesamiento="procesado",
        )
        db.add(solicitud)
        db.flush()

        codigo = _generar_codigo(db)
        tarea = TareaLlamadaConfirmacion(
            lead_id=lead.id,
            solicitud_id=solicitud.id,
            codigo_validacion=codigo,
            estado="PENDIENTE",
            prioridad="NORMAL",
        )
        db.add(tarea)
        db.commit()

        logger.info(
            f"[WA/Melanie] ✅ lead={lead.id} ({'nuevo' if lead_es_nuevo else 'existente'}) "
            f"solicitud={solicitud.id} código={codigo}"
        )

        try:
            from routers.notificaciones import notificar_todos
            notificar_todos(
                db=db,
                titulo="📞 Nuevo contacto vía Melanie",
                mensaje=f"Tel: {phone} · Código: {codigo}",
                tipo="LEAD",
                referencia_id=lead.id,
                referencia_tipo="lead",
                url=f"/integraciones?solicitud={solicitud.id}",
            )
        except Exception as exc:
            logger.warning(f"[WA/Melanie] Notificación falló (no crítico): {exc}")

    except Exception as exc:
        db.rollback()
        logger.error(f"[WA/Melanie] Error en webhook: {exc}", exc_info=True)

    return {"status": "ok"}
