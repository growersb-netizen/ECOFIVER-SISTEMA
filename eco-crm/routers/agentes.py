"""
Endpoints exclusivos para el sistema de agentes IA.
Autenticación: Bearer token (API key estática, no JWT).
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database.database import get_db
from database.models import (
    Lead, MensajeConversacion, VentaFinanciada, VentaContado,
    StockPiscina, StockPanel, Videollamada,
)
from routers.ventas_financiadas import dias_atraso

router = APIRouter()

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


# ─── AUTH ─────────────────────────────────────────────────────────────────────

def _require_api_key(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:].strip() == API_KEY:
        return True
    raise HTTPException(status_code=401, detail="API key inválida")


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _find_lead(session_id: str, db: Session) -> Optional[Lead]:
    """Busca por session_id, luego por teléfono."""
    lead = db.query(Lead).filter(Lead.session_id == session_id).first()
    if not lead:
        lead = db.query(Lead).filter(Lead.telefono == session_id).first()
    return lead


def _lead_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "session_id": lead.session_id or lead.telefono or "",
        "nombre": lead.nombre,
        "telefono": lead.telefono or "",
        "localidad": lead.localidad or "",
        "producto_interes": lead.producto_interes or "SIN_DEFINIR",
        "modelo_especifico": lead.modelo_especifico or "",
        "forma_pago": lead.forma_pago or "SIN_DEFINIR",
        "estado": lead.estado or "NUEVO",
        "origen": lead.origen or "WHATSAPP",
        "notas": lead.notas or "",
        "agente_asignado": lead.agente_asignado or "valentina",
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else "",
    }


# ─── LEADS (by session) ───────────────────────────────────────────────────────

@router.get("/api/leads/by-session/{session_id}")
async def get_lead_by_session(
    session_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Devuelve un lead por session_id o teléfono. Retorna {} si no existe."""
    lead = _find_lead(session_id, db)
    if not lead:
        return {}
    return _lead_dict(lead)


@router.post("/api/leads/agent")
async def create_lead_agent(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Crea un lead desde el sistema de agentes. Idempotente: retorna el existente si ya está."""
    data = await request.json()
    session_id = data.get("session_id", "")

    existing = _find_lead(session_id, db)
    if existing:
        return _lead_dict(existing)

    canal = data.get("canal_origen", "whatsapp").upper()
    origen_map = {"WHATSAPP": "WHATSAPP", "WEB": "WEB", "TELEGRAM": "WHATSAPP"}
    origen = origen_map.get(canal, "WHATSAPP")
    is_phone = session_id.lstrip("+").isdigit() and len(session_id) >= 8

    # Para teléfonos usamos el número COMPLETO en el nombre por defecto
    # (antes se cortaba a 12 caracteres y perdía el último dígito).
    nombre_default = f"Lead {session_id}" if is_phone else f"Lead {session_id[:12]}"

    lead = Lead(
        session_id=session_id,
        nombre=data.get("nombre") or nombre_default,
        telefono=session_id if is_phone else data.get("telefono", ""),
        localidad=data.get("localidad", ""),
        producto_interes=data.get("producto_interes", "SIN_DEFINIR"),
        forma_pago=data.get("forma_pago", "SIN_DEFINIR"),
        estado="NUEVO",
        origen=origen,
        agente_asignado=data.get("agente_asignado", "valentina"),
        notas="",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


@router.patch("/api/leads/by-session/{session_id}")
async def update_lead_by_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    lead = _find_lead(session_id, db)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    updatable = [
        "nombre", "telefono", "localidad", "producto_interes",
        "modelo_especifico", "forma_pago", "estado", "notas", "agente_asignado",
    ]
    for field in updatable:
        if field in data:
            setattr(lead, field, data[field])

    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ─── MENSAJES DE CONVERSACIÓN ─────────────────────────────────────────────────

@router.get("/api/leads/by-session/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    lead = _find_lead(session_id, db)
    if not lead:
        return []
    msgs = (
        db.query(MensajeConversacion)
        .filter(MensajeConversacion.lead_id == lead.id)
        .order_by(MensajeConversacion.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "user_msg": m.user_msg,
            "agent_reply": m.agent_reply,
            "agent_name": m.agent_name,
            "msg_type": m.msg_type,
            "created_at": m.created_at.isoformat() if m.created_at else "",
        }
        for m in reversed(msgs)
    ]


@router.post("/api/leads/by-session/{session_id}/messages")
async def save_message(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    lead = _find_lead(session_id, db)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    msg = MensajeConversacion(
        lead_id=lead.id,
        user_msg=data.get("user_msg", ""),
        agent_reply=data.get("agent_reply", ""),
        agent_name=data.get("agent_name", ""),
        msg_type=data.get("msg_type", "text"),
    )
    db.add(msg)
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ─── LEADS SIN RESPUESTA ──────────────────────────────────────────────────────

@router.get("/api/leads/sin-respuesta")
async def leads_sin_respuesta(
    horas: int = 2,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    cutoff = datetime.utcnow() - timedelta(hours=horas)
    leads = (
        db.query(Lead)
        .filter(Lead.estado.in_(["NUEVO", "CONTACTADO", "CALIFICADO"]))
        .filter(
            or_(Lead.updated_at < cutoff, Lead.updated_at == None)  # noqa: E711
        )
        .filter(Lead.created_at < cutoff)
        .order_by(Lead.created_at.asc())
        .limit(20)
        .all()
    )
    return [_lead_dict(l) for l in leads]


# ─── CUOTAS VENCIDAS ──────────────────────────────────────────────────────────

@router.get("/api/cuotas/vencidas")
async def cuotas_vencidas(
    dias: int = 0,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    ventas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
    ).all()

    result = []
    for v in ventas:
        atraso = dias_atraso(v)
        if atraso >= dias:
            result.append({
                "id": v.id,
                "cliente_nombre": v.cliente_nombre,
                "cliente_telefono": v.cliente_telefono,
                "producto": v.producto,
                "modelo_especifico": v.modelo_especifico or "",
                "valor_cuota": v.valor_cuota,
                "dias_atraso": atraso,
                "estado_plan": v.estado_plan,
            })

    return sorted(result, key=lambda x: x["dias_atraso"], reverse=True)


# ─── PIPELINE STATS ───────────────────────────────────────────────────────────

@router.get("/api/stats/pipeline")
async def stats_pipeline(
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    hoy = datetime.utcnow()
    inicio_hoy = hoy.replace(hour=0, minute=0, second=0, microsecond=0)

    leads_total = db.query(Lead).count()
    leads_hoy = db.query(Lead).filter(Lead.created_at >= inicio_hoy).count()
    leads_calificados = db.query(Lead).filter(Lead.estado == "CALIFICADO").count()

    vc_hoy = db.query(VentaContado).filter(
        VentaContado.created_at >= inicio_hoy, VentaContado.estado != "CANCELADO",
    ).all()
    monto_contado = sum(v.precio_final or 0 for v in vc_hoy)

    vls = db.query(Videollamada).filter(Videollamada.created_at >= inicio_hoy).count()

    ventas_fin = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
    ).all()
    cuotas_venc = sum(1 for v in ventas_fin if dias_atraso(v) > 0)

    return {
        "leads_recibidos": leads_total,
        "leads_hoy": leads_hoy,
        "leads_calificados": leads_calificados,
        "cierres_contado": len(vc_hoy),
        "monto_contado": monto_contado,
        "videollamadas": vls,
        "cuotas_cobradas": 0,
        "monto_cuotas": 0,
        "cuotas_vencidas": cuotas_venc,
        "leads_web": db.query(Lead).filter(Lead.origen == "WEB").count(),
        "publicaciones": 0,
    }


# ─── STOCK ────────────────────────────────────────────────────────────────────

@router.get("/api/stock")
async def get_stock(
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    piscinas = db.query(StockPiscina).all()
    paneles = db.query(StockPanel).all()
    return {
        "piscinas": [
            {
                "modelo": s.modelo,
                "color": s.color,
                "cantidad": s.cantidad,
                "disponible": s.cantidad > 0,
            }
            for s in piscinas
        ],
        "paneles": [
            {
                "tipo": s.tipo_panel,
                "cantidad": s.cantidad,
                "stock_minimo": s.stock_minimo,
                "bajo_minimo": s.cantidad < s.stock_minimo,
            }
            for s in paneles
        ],
    }


# ─── LEADS NUEVOS SIN CONTACTAR ──────────────────────────────────────────────

@router.get("/api/leads/nuevos-sin-contactar")
async def leads_nuevos_sin_contactar(
    minutos: int = 30,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Leads creados en los últimos N minutos sin ningún mensaje de respuesta."""
    cutoff = datetime.utcnow() - timedelta(minutes=minutos)
    leads = (
        db.query(Lead)
        .filter(Lead.estado == "NUEVO")
        .filter(Lead.created_at >= cutoff)
        .filter(
            ~db.query(MensajeConversacion)
            .filter(MensajeConversacion.lead_id == Lead.id)
            .exists()
        )
        .order_by(Lead.created_at.asc())
        .limit(20)
        .all()
    )
    return [_lead_dict(l) for l in leads]


# ─── LEADS PARA NUTRIR (20-30hs) ─────────────────────────────────────────────

@router.get("/api/leads/para-nutrir")
async def leads_para_nutrir(
    horas_desde: int = 20,
    horas_hasta: int = 30,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Leads creados entre horas_desde y horas_hasta horas atrás, sin respuesta reciente."""
    ahora = datetime.utcnow()
    desde = ahora - timedelta(hours=horas_hasta)
    hasta = ahora - timedelta(hours=horas_desde)
    leads = (
        db.query(Lead)
        .filter(Lead.estado.in_(["NUEVO", "CONTACTADO"]))
        .filter(Lead.created_at >= desde)
        .filter(Lead.created_at <= hasta)
        .order_by(Lead.created_at.asc())
        .limit(15)
        .all()
    )
    return [_lead_dict(l) for l in leads]


# ─── LEADS FRÍOS ─────────────────────────────────────────────────────────────

@router.get("/api/leads/frios-reactivar")
async def leads_frios(
    dias_inactivo: int = 30,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Leads sin actividad hace más de dias_inactivo días (para reactivar)."""
    cutoff = datetime.utcnow() - timedelta(days=dias_inactivo)
    leads = (
        db.query(Lead)
        .filter(Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO"]))
        .filter(
            or_(Lead.updated_at < cutoff, Lead.updated_at == None)  # noqa: E711
        )
        .filter(Lead.created_at < cutoff)
        .order_by(Lead.created_at.desc())
        .limit(30)
        .all()
    )
    return [_lead_dict(l) for l in leads]


# ─── REGISTRAR LEAD META ADS ──────────────────────────────────────────────────

@router.post("/api/leads/meta")
async def registrar_lead_meta(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Registra un lead proveniente de Meta Lead Ads. Idempotente por meta_lead_id."""
    data = await request.json()
    session_id = data.get("session_id") or data.get("telefono", "")
    meta_id    = data.get("meta_lead_id", "")

    # Buscar existente por session_id o meta_lead_id en notas
    existing = _find_lead(session_id, db)
    if existing:
        return _lead_dict(existing)

    telefono = data.get("telefono", session_id)
    nombre   = data.get("nombre", "") or f"Lead Meta {meta_id[:8]}"

    lead = Lead(
        session_id=session_id,
        nombre=nombre,
        telefono=telefono,
        localidad=data.get("ciudad", ""),
        producto_interes=data.get("producto_interes", "SIN_DEFINIR").upper(),
        forma_pago="SIN_DEFINIR",
        estado="NUEVO",
        origen="WHATSAPP",
        agente_asignado="valentina",
        notas=f"Meta Ads | ID:{meta_id} | Email:{data.get('email','')} | Anuncio:{data.get('ad_name','')}",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _lead_dict(lead)


# ─── VIDEOLLAMADAS PRÓXIMAS ───────────────────────────────────────────────────

@router.get("/api/videollamadas/proximas")
async def videollamadas_proximas(
    horas: int = 2,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Videollamadas agendadas en las próximas N horas."""
    ahora  = datetime.utcnow()
    limite = ahora + timedelta(hours=horas)
    vls = (
        db.query(Videollamada)
        .filter(Videollamada.estado == "AGENDADA")
        .filter(Videollamada.fecha_hora >= ahora)
        .filter(Videollamada.fecha_hora <= limite)
        .filter(Videollamada.recordatorio_enviado == False)  # noqa: E712
        .order_by(Videollamada.fecha_hora.asc())
        .all()
    )
    result = []
    for vl in vls:
        lead = db.query(Lead).filter(Lead.id == vl.lead_id).first() if vl.lead_id else None
        result.append({
            "id":       vl.id,
            "lead_id":  vl.lead_id,
            "nombre":   vl.cliente_nombre,
            "telefono": vl.cliente_telefono or (lead.telefono if lead else ""),
            "hora":     vl.fecha_hora.strftime("%H:%M") if vl.fecha_hora else "",
            "fecha":    vl.fecha_hora.strftime("%d/%m/%Y") if vl.fecha_hora else "",
            "tipo":     "videollamada",
        })
        # Marcar recordatorio enviado
        vl.recordatorio_enviado = True
    db.commit()
    return result


# ─── AGENDAR VIDEOLLAMADA / LLAMADA SUPERVISORA ───────────────────────────────

@router.post("/api/videollamadas")
async def agendar_videollamada(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """
    Crea una videollamada de admisión o llamada supervisora desde el sistema de agentes.
    Body: {lead_id, fecha_hora, tipo, agente}
    """
    data = await request.json()
    lead_id   = data.get("lead_id")
    tipo      = data.get("tipo", "videollamada")
    agente    = data.get("agente", "")
    fecha_str = data.get("fecha_hora", "")

    # Obtener datos del lead
    lead = None
    if lead_id:
        lead = db.query(Lead).filter(
            or_(Lead.id == lead_id, Lead.session_id == str(lead_id), Lead.telefono == str(lead_id))
        ).first()

    nombre    = lead.nombre if lead else f"Lead {lead_id}"
    telefono  = lead.telefono if lead else ""
    producto  = lead.producto_interes if lead else "SIN_DEFINIR"
    forma_pago = "FINANCIADO" if tipo == "videollamada" else "CONTADO"

    # Parsear fecha (texto como "martes 15:00" → timestamp aproximado)
    fecha_hora = None
    try:
        fecha_hora = datetime.fromisoformat(fecha_str)
    except Exception:
        fecha_hora = datetime.utcnow() + timedelta(days=1)  # fallback: mañana

    vl = Videollamada(
        lead_id=lead.id if lead else None,
        cliente_nombre=nombre,
        cliente_telefono=telefono,
        producto_interes=producto,
        forma_pago=forma_pago,
        fecha_hora=fecha_hora,
        estado="AGENDADA",
        resultado="PENDIENTE",
        notas=f"Tipo: {tipo} | Agente: {agente} | Texto original: {fecha_str}",
    )
    db.add(vl)
    if lead:
        lead.estado = "CALIFICADO"
        lead.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(vl)

    return {
        "ok":      True,
        "vl_id":   vl.id,
        "tipo":    tipo,
        "nombre":  nombre,
        "fecha":   fecha_hora.isoformat(),
    }


# ─── LLAMADAS SUPERVISORA PENDIENTES ─────────────────────────────────────────

@router.get("/api/videollamadas/supervisora-pendientes")
async def llamadas_supervisora_pendientes(
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    """Videollamadas de tipo llamada_supervisora (contado) con resultado PENDIENTE."""
    vls = (
        db.query(Videollamada)
        .filter(Videollamada.estado == "AGENDADA")
        .filter(Videollamada.resultado == "PENDIENTE")
        .filter(Videollamada.forma_pago == "CONTADO")
        .filter(Videollamada.fecha_hora < datetime.utcnow())  # ya pasó la hora pactada
        .order_by(Videollamada.fecha_hora.asc())
        .limit(20)
        .all()
    )
    result = []
    for vl in vls:
        result.append({
            "id":          vl.id,
            "nombre":      vl.cliente_nombre,
            "telefono":    vl.cliente_telefono or "",
            "hora_pactada": vl.fecha_hora.strftime("%H:%M") if vl.fecha_hora else "",
            "tipo":        "llamada_supervisora",
        })
    return result


# ─── VENTAS HOY ───────────────────────────────────────────────────────────────

@router.get("/api/stats/ventas-hoy")
async def ventas_hoy(
    db: Session = Depends(get_db),
    _: bool = Depends(_require_api_key),
):
    hoy = datetime.utcnow()
    inicio_hoy = hoy.replace(hour=0, minute=0, second=0, microsecond=0)

    # Excluye CANCELADO — si no, una venta de prueba dada de baja (ej. datos de
    # testeo técnico) se cuenta igual como cierre real del día.
    vc = db.query(VentaContado).filter(
        VentaContado.created_at >= inicio_hoy, VentaContado.estado != "CANCELADO",
    ).all()
    vf = db.query(VentaFinanciada).filter(
        VentaFinanciada.created_at >= inicio_hoy, VentaFinanciada.estado_plan != "CANCELADO",
    ).all()
    leads_nuevos = db.query(Lead).filter(Lead.created_at >= inicio_hoy).count()

    monto_total = sum(v.precio_final or 0 for v in vc)
    monto_total += sum(v.anticipo or 0 for v in vf)

    return {
        "cierres": len(vc) + len(vf),
        "monto_total": monto_total,
        "leads_nuevos": leads_nuevos,
    }
