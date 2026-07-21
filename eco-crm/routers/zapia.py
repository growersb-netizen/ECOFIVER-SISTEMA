"""
API Externa — Zapia / Agentes
==============================
Todos los endpoints usan autenticación por API key (header X-Api-Key).
Prefijo: /api/ext/

Áreas cubiertas:
  - Leads (CRUD + búsqueda + reasignación masiva por asesor)
  - Videollamadas
  - Ventas (contado + financiadas + pagos)
  - Cobranzas (vencidas + gestiones)
  - Fábrica (órdenes piscinas + módulos + stock)
  - Logística (entregas)
  - Reclamos
  - Asesores (listado con métricas)
  - Dashboard (resumen de métricas)
  - Mensajes de conversación (historial por lead)
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func as sqlfunc

from database.database import get_db
from database.models import (
    Lead, Usuario, Videollamada, VentaContado, VentaFinanciada,
    Pago, GestionCobranza, OrdenFabricaPiscina, OrdenFabricaModulo,
    StockPiscina, StockPanel, Entrega, Reclamo, MensajeConversacion,
    Notificacion, ConfiguracionSistema, Gasto, EnvioViaCargo,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ext", tags=["API Externa Zapia"])

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


# ─── AUTH ─────────────────────────────────────────────────────────────────────

def require_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(401, "API key inválida o ausente. Enviá el header X-Api-Key.")
    return True


def resolve_agente(x_agent_key: Optional[str], db: Session) -> Optional[Usuario]:
    """
    Resuelve el agente IA que hace la request a partir de su agente_key personal.
    Si no se provee, retorna None (acceso genérico de Zapia).
    """
    if not x_agent_key:
        return None
    return db.query(Usuario).filter(
        Usuario.agente_key == x_agent_key,
        Usuario.es_agente_ia == True,
        Usuario.activo == True,
    ).first()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _lead_dict(lead: Lead, db: Session) -> dict:
    return {
        "id": lead.id,
        "nombre": lead.nombre,
        "telefono": lead.telefono,
        "localidad": lead.localidad or "",
        "producto_interes": lead.producto_interes or "SIN_DEFINIR",
        "modelo_especifico": lead.modelo_especifico or "",
        "forma_pago": lead.forma_pago or "SIN_DEFINIR",
        "estado": lead.estado or "NUEVO",
        "origen": lead.origen or "WHATSAPP",
        "asesor_apertura_id": lead.asesor_apertura_id,
        "asesor_apertura_nombre": lead.asesor_apertura.nombre if lead.asesor_apertura else "",
        "supervisor_cierre_id": lead.supervisor_cierre_id,
        "supervisor_cierre_nombre": lead.supervisor_cierre.nombre if lead.supervisor_cierre else "",
        "notas": lead.notas or "",
        "session_id": lead.session_id or "",
        "agente_asignado": lead.agente_asignado or "",
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else "",
    }


def _venta_contado_dict(v: VentaContado) -> dict:
    return {
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "precio_final": v.precio_final or 0,
        "forma_pago": v.forma_pago or "",
        "estado": v.estado or "",
        "fecha_instalacion": v.fecha_instalacion.isoformat() if v.fecha_instalacion else "",
        "vendedor_id": v.vendedor_id,
        "vendedor_nombre": v.vendedor.nombre if v.vendedor else "",
        "notas": v.notas or "",
        "desde_stock": v.desde_stock,
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


def _venta_fin_dict(v: VentaFinanciada) -> dict:
    return {
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "forma_pago": v.forma_pago or "",
        "precio_total": v.precio_total or 0,
        "anticipo": v.anticipo or 0,
        "cantidad_cuotas": v.cantidad_cuotas or 0,
        "valor_cuota": v.valor_cuota or 0,
        "cuotas_pagas": v.cuotas_pagas or 0,
        "cuotas_pendientes": max(0, (v.cantidad_cuotas or 0) - (v.cuotas_pagas or 0)),
        "estado_plan": v.estado_plan or "",
        "estado_admision": v.estado_admision or "",
        "asesor_apertura_id": v.asesor_apertura_id,
        "asesor_apertura_nombre": v.asesor_apertura.nombre if v.asesor_apertura else "",
        "fecha_inicio_plan": v.fecha_inicio_plan.isoformat() if v.fecha_inicio_plan else "",
        "fecha_primer_vencimiento": v.fecha_primer_vencimiento.isoformat() if v.fecha_primer_vencimiento else "",
        "notas": v.notas or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


def _asignar_rr(db: Session) -> Optional[int]:
    """Round-robin respetando el pool configurado."""
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "leads_rr_asesores"
    ).first()
    pool_ids = None
    if cfg and cfg.valor:
        try:
            ids = json.loads(cfg.valor)
            pool_ids = set(ids) if ids else None
        except Exception:
            pass

    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    candidatos = []
    for u in asesores:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []
        tiene_rol = "ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles
        en_pool = (pool_ids is None) or (u.id in pool_ids)
        if tiene_rol and en_pool:
            candidatos.append(u)

    if not candidatos:
        return None

    conteos = {
        u.id: db.query(Lead).filter(
            Lead.asesor_apertura_id == u.id,
            Lead.estado.notin_(["CERRADO", "PERDIDO"])
        ).count()
        for u in candidatos
    }
    elegido = min(candidatos, key=lambda u: (conteos[u.id], u.id))
    return elegido.id


# ═══════════════════════════════════════════════════════════════════════════════
# INFO
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/info")
async def info(_: bool = Depends(require_api_key)):
    """Verifica conectividad y devuelve metadata del sistema."""
    return {
        "sistema": "Eco Módulos & Piscinas CRM",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "estado": "ok",
        "endpoints_disponibles": [
            "GET  /api/ext/info",
            "GET  /api/ext/dashboard",
            "--- LEADS ---",
            "GET  /api/ext/leads",
            "POST /api/ext/leads",
            "GET  /api/ext/leads/buscar?telefono=",
            "GET  /api/ext/leads/seguimientos-pendientes",
            "GET  /api/ext/leads/{id}",
            "PATCH /api/ext/leads/{id}",
            "POST /api/ext/leads/{id}/nota",
            "POST /api/ext/leads/{id}/mensaje",
            "GET  /api/ext/leads/{id}/mensajes",
            "POST /api/ext/leads/{id}/seguimiento",
            "POST /api/ext/leads/reasignar-asesor",
            "--- VIDEOLLAMADAS ---",
            "GET  /api/ext/videollamadas",
            "POST /api/ext/videollamadas",
            "PATCH /api/ext/videollamadas/{id}",
            "--- VENTAS ---",
            "GET  /api/ext/ventas",
            "GET  /api/ext/ventas/financiada/{id}",
            "POST /api/ext/ventas/contado",
            "POST /api/ext/ventas/financiada",
            "POST /api/ext/ventas/financiada/{id}/pago",
            "--- CATÁLOGO & COTIZACIÓN ---",
            "GET  /api/ext/catalogo",
            "GET  /api/ext/cotizar?producto=PISCINA&modelo=...&localidad=...",
            "GET  /api/ext/ranking?periodo=mes",
            "--- STOCK ---",
            "GET  /api/ext/stock/disponible",
            "GET  /api/ext/stock/piscinas",
            "GET  /api/ext/stock/paneles",
            "PATCH /api/ext/stock/piscinas/{id}",
            "--- ENVÍOS VÍA CARGO ---",
            "GET  /api/ext/envios",
            "POST /api/ext/envios",
            "PATCH /api/ext/envios/{id}",
            "GET  /api/ext/envios/buscar?telefono=",
            "--- COBRANZAS ---",
            "GET  /api/ext/cobranzas/vencidas",
            "GET  /api/ext/cobranzas/buscar?telefono=",
            "POST /api/ext/cobranzas/{id}/gestion",
            "--- FABRICA ---",
            "GET  /api/ext/fabrica/ordenes",
            "PATCH /api/ext/fabrica/ordenes/{id}",
            "--- LOGISTICA ---",
            "GET  /api/ext/logistica/entregas",
            "PATCH /api/ext/logistica/entregas/{id}",
            "--- RECLAMOS ---",
            "GET  /api/ext/reclamos",
            "POST /api/ext/reclamos",
            "PATCH /api/ext/reclamos/{id}",
            "--- ASESORES ---",
            "GET  /api/ext/asesores",
            "--- GASTOS ---",
            "POST /api/ext/gastos",
            "GET  /api/ext/gastos",
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def dashboard(db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    """Resumen ejecutivo del CRM: métricas clave de hoy y totales."""
    hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    hace_24h = datetime.now() - timedelta(hours=24)

    leads_hoy = db.query(Lead).filter(Lead.created_at >= hoy_inicio).count()
    leads_nuevos_total = db.query(Lead).filter(Lead.estado == "NUEVO").count()
    leads_sin_contactar = db.query(Lead).filter(
        Lead.estado == "NUEVO",
        or_(
            and_(Lead.updated_at.isnot(None), Lead.updated_at <= hace_24h),
            and_(Lead.updated_at.is_(None), Lead.created_at <= hace_24h),
        )
    ).count()

    vl_hoy = db.query(Videollamada).filter(
        Videollamada.fecha_hora >= hoy_inicio,
        Videollamada.estado == "AGENDADA",
    ).count()

    ventas_contado_mes = db.query(VentaContado).filter(
        VentaContado.created_at >= datetime.now().replace(day=1, hour=0, minute=0, second=0)
    ).count()
    ventas_fin_atrasadas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan == "ATRASADO"
    ).count()

    ordenes_fabrica_activas = db.query(OrdenFabricaPiscina).filter(
        OrdenFabricaPiscina.estado.in_(["EN_ESPERA", "EN_PROCESO"])
    ).count() + db.query(OrdenFabricaModulo).filter(
        OrdenFabricaModulo.estado.in_(["EN_ESPERA", "EN_PROCESO"])
    ).count()

    entregas_pendientes = db.query(Entrega).filter(
        Entrega.estado.in_(["COORDINADA", "EN_CAMINO"])
    ).count()

    reclamos_abiertos = db.query(Reclamo).filter(
        Reclamo.estado.in_(["NUEVO", "EN_GESTION"])
    ).count()

    return {
        "timestamp": datetime.now().isoformat(),
        "leads": {
            "creados_hoy": leads_hoy,
            "en_estado_nuevo": leads_nuevos_total,
            "sin_contactar_24h": leads_sin_contactar,
        },
        "videollamadas": {
            "agendadas_hoy": vl_hoy,
        },
        "ventas": {
            "contado_este_mes": ventas_contado_mes,
            "financiadas_atrasadas": ventas_fin_atrasadas,
        },
        "fabrica": {
            "ordenes_activas": ordenes_fabrica_activas,
        },
        "logistica": {
            "entregas_pendientes": entregas_pendientes,
        },
        "reclamos": {
            "abiertos": reclamos_abiertos,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/leads/buscar")
async def buscar_lead_por_telefono(
    telefono: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Busca un lead por número de teléfono (coincidencia parcial). Ideal para Zapia."""
    leads = db.query(Lead).filter(
        Lead.telefono.ilike(f"%{telefono.strip()}%")
    ).order_by(Lead.created_at.desc()).limit(5).all()
    return {"encontrados": len(leads), "leads": [_lead_dict(l, db) for l in leads]}


@router.get("/leads/reasignar-asesor")
async def preview_reasignacion_asesor(
    asesor_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Preview: cuántos leads tiene un asesor antes de reasignar."""
    u = db.query(Usuario).filter(Usuario.id == asesor_id).first()
    if not u:
        raise HTTPException(404, "Asesor no encontrado")
    total = db.query(Lead).filter(Lead.asesor_apertura_id == asesor_id).count()
    activos = db.query(Lead).filter(
        Lead.asesor_apertura_id == asesor_id,
        Lead.estado.notin_(["CERRADO", "PERDIDO"])
    ).count()
    return {"asesor_id": asesor_id, "asesor_nombre": u.nombre, "total": total, "activos": activos}


@router.post("/leads/reasignar-asesor")
async def reasignar_masivo_por_asesor(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Reasigna TODOS los leads de un asesor a otro (o a round-robin).

    Body:
      desde_id      int       — asesor origen (obligatorio)
      hacia_id      int|null  — asesor destino; null = round-robin automático
      solo_activos  bool      — default true (excluye CERRADO y PERDIDO)
      estados       list|null — filtra por estados específicos ej. ["NUEVO","CONTACTADO"]
    """
    data = await request.json()
    desde_id = data.get("desde_id")
    hacia_id = data.get("hacia_id")          # None = round-robin
    solo_activos = data.get("solo_activos", True)
    estados_filtro = data.get("estados")     # lista opcional

    if not desde_id:
        raise HTTPException(400, "desde_id es obligatorio")
    if hacia_id and int(desde_id) == int(hacia_id):
        raise HTTPException(400, "desde_id y hacia_id deben ser distintos")

    q = db.query(Lead).filter(Lead.asesor_apertura_id == int(desde_id))
    if solo_activos:
        q = q.filter(Lead.estado.notin_(["CERRADO", "PERDIDO"]))
    if estados_filtro:
        q = q.filter(Lead.estado.in_(estados_filtro))

    leads = q.all()
    ts = datetime.now().strftime("%d/%m %H:%M")
    reasignados = 0

    hacia_u = db.query(Usuario).filter(Usuario.id == int(hacia_id)).first() if hacia_id else None

    for lead in leads:
        nuevo_id = int(hacia_id) if hacia_id else _asignar_rr(db)
        if not nuevo_id:
            continue
        destino = hacia_u or db.query(Usuario).filter(Usuario.id == nuevo_id).first()
        lead.asesor_apertura_id = nuevo_id
        lead.notas = (lead.notas or "") + f"\n[{ts}] 🔀 Reasignado a {destino.nombre if destino else nuevo_id} vía API"
        reasignados += 1

    db.commit()
    return {"ok": True, "reasignados": reasignados, "total_encontrados": len(leads)}


@router.get("/leads")
async def list_leads_ext(
    estado: Optional[str] = None,
    producto: Optional[str] = None,
    asesor_id: Optional[int] = None,
    origen: Optional[str] = None,
    telefono: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista leads con filtros opcionales."""
    q = db.query(Lead)
    if estado:
        q = q.filter(Lead.estado == estado.upper())
    if producto:
        q = q.filter(Lead.producto_interes == producto.upper())
    if asesor_id:
        q = q.filter(Lead.asesor_apertura_id == asesor_id)
    if origen:
        q = q.filter(Lead.origen == origen.upper())
    if telefono:
        q = q.filter(Lead.telefono.ilike(f"%{telefono}%"))
    if search:
        q = q.filter(or_(
            Lead.nombre.ilike(f"%{search}%"),
            Lead.telefono.ilike(f"%{search}%"),
            Lead.localidad.ilike(f"%{search}%"),
        ))
    total = q.count()
    leads = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "leads": [_lead_dict(l, db) for l in leads]}


@router.post("/leads")
async def create_lead_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea un nuevo lead. Si no viene asesor_apertura_id, asigna automáticamente por round-robin.

    Body (todos opcionales salvo nombre+telefono):
      nombre, telefono, localidad, producto_interes, modelo_especifico,
      forma_pago, estado, origen, notas, asesor_apertura_id, session_id, agente_asignado
    """
    data = await request.json()
    if not data.get("nombre") or not data.get("telefono"):
        raise HTTPException(400, "nombre y telefono son obligatorios")

    asesor_id = data.get("asesor_apertura_id") or _asignar_rr(db)

    lead = Lead(
        nombre=data["nombre"],
        telefono=data["telefono"],
        localidad=data.get("localidad", ""),
        producto_interes=data.get("producto_interes", "SIN_DEFINIR"),
        modelo_especifico=data.get("modelo_especifico", ""),
        forma_pago=data.get("forma_pago", "SIN_DEFINIR"),
        estado=data.get("estado", "NUEVO"),
        origen=data.get("origen", "WHATSAPP"),
        notas=data.get("notas", ""),
        asesor_apertura_id=asesor_id,
        session_id=data.get("session_id"),
        agente_asignado=data.get("agente_asignado", ""),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    asesor_nombre = ""
    if asesor_id:
        u = db.query(Usuario).filter(Usuario.id == asesor_id).first()
        asesor_nombre = u.nombre if u else ""

    return {"ok": True, "id": lead.id, "asesor_asignado": asesor_nombre, "lead": _lead_dict(lead, db)}


@router.get("/leads/{lead_id}")
async def get_lead_ext(
    lead_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Devuelve el detalle completo de un lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    return _lead_dict(lead, db)


@router.patch("/leads/{lead_id}")
async def update_lead_ext(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Actualiza campos de un lead. Solo enviar los campos que se quieren modificar.

    Campos actualizables:
      nombre, telefono, localidad, producto_interes, modelo_especifico,
      forma_pago, estado, origen, notas, asesor_apertura_id,
      supervisor_cierre_id, session_id, agente_asignado
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    campos = [
        "nombre", "telefono", "localidad", "producto_interes", "modelo_especifico",
        "forma_pago", "estado", "origen", "notas", "asesor_apertura_id",
        "supervisor_cierre_id", "session_id", "agente_asignado",
    ]
    for campo in campos:
        if campo in data:
            setattr(lead, campo, data[campo])

    # Si cambia a VIDEOLLAMADA_AGENDADA, crear registro automáticamente
    if data.get("estado") == "VIDEOLLAMADA_AGENDADA":
        existe = db.query(Videollamada).filter(
            Videollamada.lead_id == lead_id,
            Videollamada.estado == "AGENDADA"
        ).first()
        if not existe:
            vl = Videollamada(
                lead_id=lead.id,
                cliente_nombre=lead.nombre,
                cliente_telefono=lead.telefono,
                producto_interes=lead.producto_interes,
                forma_pago=lead.forma_pago,
                asesor_apertura_id=lead.asesor_apertura_id,
                estado="AGENDADA",
            )
            db.add(vl)

    db.commit()
    db.refresh(lead)
    return {"ok": True, "lead": _lead_dict(lead, db)}


@router.post("/leads/{lead_id}/nota")
async def agregar_nota_lead(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Agrega una nota al lead (se concatena con timestamp)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    data = await request.json()
    texto = data.get("nota", "").strip()
    if not texto:
        raise HTTPException(400, "nota no puede estar vacía")
    autor = data.get("autor", "Zapia")
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    lead.notas = (lead.notas or "") + f"\n[{ts}] {autor}: {texto}"
    db.commit()
    return {"ok": True, "notas": lead.notas}


@router.post("/leads/{lead_id}/mensaje")
async def guardar_mensaje(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Guarda un intercambio de mensajes del agente en el historial del lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    data = await request.json()
    msg = MensajeConversacion(
        lead_id=lead_id,
        user_msg=data.get("user_msg", ""),
        agent_reply=data.get("agent_reply", ""),
        agent_name=data.get("agent_name", "zapia"),
        msg_type=data.get("msg_type", "text"),
    )
    db.add(msg)
    db.commit()
    return {"ok": True, "id": msg.id}


@router.get("/leads/{lead_id}/mensajes")
async def historial_mensajes(
    lead_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Devuelve el historial de conversación de un lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    msgs = db.query(MensajeConversacion).filter(
        MensajeConversacion.lead_id == lead_id
    ).order_by(MensajeConversacion.created_at.desc()).limit(limit).all()
    return {
        "lead_id": lead_id,
        "mensajes": [
            {
                "id": m.id,
                "user_msg": m.user_msg,
                "agent_reply": m.agent_reply,
                "agent_name": m.agent_name,
                "msg_type": m.msg_type,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in reversed(msgs)
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEOLLAMADAS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/videollamadas")
async def list_videollamadas_ext(
    estado: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    asesor_id: Optional[int] = None,
    solo_hoy: bool = False,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista videollamadas. Filtros: estado, rango de fechas, asesor, solo_hoy."""
    q = db.query(Videollamada)
    if estado:
        q = q.filter(Videollamada.estado == estado.upper())
    if asesor_id:
        q = q.filter(Videollamada.asesor_apertura_id == asesor_id)
    if solo_hoy:
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(Videollamada.fecha_hora >= hoy)
    if fecha_desde:
        q = q.filter(Videollamada.fecha_hora >= datetime.fromisoformat(fecha_desde))
    if fecha_hasta:
        q = q.filter(Videollamada.fecha_hora <= datetime.fromisoformat(fecha_hasta))

    total = q.count()
    vls = q.order_by(Videollamada.fecha_hora.asc()).offset(skip).limit(limit).all()

    def _vl_dict(v):
        return {
            "id": v.id,
            "lead_id": v.lead_id,
            "cliente_nombre": v.cliente_nombre,
            "cliente_telefono": v.cliente_telefono or "",
            "producto_interes": v.producto_interes or "",
            "forma_pago": v.forma_pago or "",
            "fecha_hora": v.fecha_hora.isoformat() if v.fecha_hora else "",
            "estado": v.estado or "",
            "resultado": v.resultado or "",
            "estado_admision": v.estado_admision or "",
            "asesor_apertura_id": v.asesor_apertura_id,
            "asesor_apertura_nombre": v.asesor_apertura.nombre if v.asesor_apertura else "",
            "supervisor_cierre_id": v.supervisor_cierre_id,
            "supervisor_cierre_nombre": v.supervisor_cierre.nombre if v.supervisor_cierre else "",
            "notas": v.notas or "",
            "created_at": v.created_at.isoformat() if v.created_at else "",
        }

    return {"total": total, "videollamadas": [_vl_dict(v) for v in vls]}


@router.post("/videollamadas")
async def create_videollamada_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea una videollamada.

    Body:
      cliente_nombre*, cliente_telefono, producto_interes, forma_pago,
      fecha_hora (ISO), estado, asesor_apertura_id, supervisor_cierre_id,
      lead_id, notas
    """
    data = await request.json()
    if not data.get("cliente_nombre"):
        raise HTTPException(400, "cliente_nombre es obligatorio")

    fecha = None
    if data.get("fecha_hora"):
        try:
            fecha = datetime.fromisoformat(data["fecha_hora"])
        except Exception:
            raise HTTPException(400, "fecha_hora inválida, usar formato ISO: 2025-06-15T10:00:00")

    vl = Videollamada(
        lead_id=data.get("lead_id"),
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        producto_interes=data.get("producto_interes", ""),
        forma_pago=data.get("forma_pago", ""),
        fecha_hora=fecha,
        estado=data.get("estado", "AGENDADA"),
        resultado=data.get("resultado", "PENDIENTE"),
        asesor_apertura_id=data.get("asesor_apertura_id"),
        supervisor_cierre_id=data.get("supervisor_cierre_id"),
        notas=data.get("notas", ""),
    )
    db.add(vl)

    # Actualizar estado del lead si viene lead_id
    if data.get("lead_id"):
        lead = db.query(Lead).filter(Lead.id == data["lead_id"]).first()
        if lead and lead.estado not in ["CERRADO", "PERDIDO"]:
            lead.estado = "VIDEOLLAMADA_AGENDADA"

    db.commit()
    db.refresh(vl)
    return {"ok": True, "id": vl.id}


@router.patch("/videollamadas/{vl_id}")
async def update_videollamada_ext(
    vl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Actualiza estado, resultado, fecha_hora, notas de una videollamada."""
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    data = await request.json()

    for campo in ["estado", "resultado", "notas", "estado_admision",
                  "asesor_apertura_id", "supervisor_cierre_id"]:
        if campo in data:
            setattr(vl, campo, data[campo])

    if "fecha_hora" in data:
        try:
            vl.fecha_hora = datetime.fromisoformat(data["fecha_hora"])
        except Exception:
            raise HTTPException(400, "fecha_hora inválida")

    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# VENTAS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/ventas")
async def list_ventas_ext(
    tipo: Optional[str] = None,   # "contado" | "financiada"
    estado: Optional[str] = None,
    cliente: Optional[str] = None,
    telefono: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista ventas (contado y/o financiadas). tipo='contado' o 'financiada' para filtrar."""
    result = {"ventas_contado": [], "ventas_financiadas": []}

    if not tipo or tipo == "contado":
        q = db.query(VentaContado)
        if estado:
            q = q.filter(VentaContado.estado == estado.upper())
        if cliente:
            q = q.filter(VentaContado.cliente_nombre.ilike(f"%{cliente}%"))
        if telefono:
            q = q.filter(VentaContado.cliente_telefono.ilike(f"%{telefono}%"))
        result["ventas_contado"] = [_venta_contado_dict(v) for v in
                                    q.order_by(VentaContado.created_at.desc()).offset(skip).limit(limit).all()]

    if not tipo or tipo == "financiada":
        q = db.query(VentaFinanciada)
        if estado:
            q = q.filter(VentaFinanciada.estado_plan == estado.upper())
        if cliente:
            q = q.filter(VentaFinanciada.cliente_nombre.ilike(f"%{cliente}%"))
        if telefono:
            q = q.filter(VentaFinanciada.cliente_telefono.ilike(f"%{telefono}%"))
        result["ventas_financiadas"] = [_venta_fin_dict(v) for v in
                                        q.order_by(VentaFinanciada.created_at.desc()).offset(skip).limit(limit).all()]

    return result


@router.get("/ventas/financiada/{venta_id}")
async def get_venta_financiada_ext(
    venta_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Detalle de una venta financiada con historial de pagos."""
    v = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    data = _venta_fin_dict(v)
    data["pagos"] = [
        {"id": p.id, "monto": p.monto, "fecha": p.fecha_pago.isoformat() if p.fecha_pago else "", "notas": p.notas}
        for p in v.pagos
    ]
    return data


@router.post("/ventas/contado")
async def create_venta_contado_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea una venta al contado.

    Body:
      cliente_nombre*, cliente_telefono, cliente_localidad,
      producto (PISCINA|MODULO|COMBO), modelo_especifico, color,
      precio_final*, forma_pago, fecha_instalacion (ISO),
      vendedor_id, distancia_km, notas, desde_stock (bool)
    """
    data = await request.json()
    if not data.get("cliente_nombre") or not data.get("precio_final"):
        raise HTTPException(400, "cliente_nombre y precio_final son obligatorios")

    fecha_inst = None
    if data.get("fecha_instalacion"):
        try:
            fecha_inst = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            raise HTTPException(400, "fecha_instalacion inválida")

    v = VentaContado(
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color", ""),
        precio_final=float(data["precio_final"]),
        forma_pago=data.get("forma_pago", "CONTADO"),
        fecha_instalacion=fecha_inst,
        vendedor_id=data.get("vendedor_id"),
        distancia_km=data.get("distancia_km"),
        estado=data.get("estado", "COORDINADO"),
        notas=data.get("notas", ""),
        desde_stock=data.get("desde_stock", False),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"ok": True, "id": v.id}


@router.post("/ventas/financiada")
async def create_venta_financiada_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea una venta financiada.

    Body:
      cliente_nombre*, cliente_telefono, cliente_localidad,
      producto, modelo_especifico, color, forma_pago*,
      precio_total*, anticipo, cantidad_cuotas*, valor_cuota*,
      fecha_inicio_plan (ISO), fecha_primer_vencimiento (ISO),
      asesor_apertura_id, supervisor_cierre_id, notas
    """
    data = await request.json()
    reqs = ["cliente_nombre", "forma_pago", "precio_total", "cantidad_cuotas", "valor_cuota"]
    for r in reqs:
        if not data.get(r):
            raise HTTPException(400, f"{r} es obligatorio")

    def parse_dt(key):
        val = data.get(key)
        if val:
            try:
                return datetime.fromisoformat(val)
            except Exception:
                raise HTTPException(400, f"{key} inválido, usar ISO format")
        return None

    v = VentaFinanciada(
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color", ""),
        forma_pago=data["forma_pago"],
        precio_total=float(data["precio_total"]),
        anticipo=float(data.get("anticipo", 0)),
        cantidad_cuotas=int(data["cantidad_cuotas"]),
        valor_cuota=float(data["valor_cuota"]),
        fecha_inicio_plan=parse_dt("fecha_inicio_plan"),
        fecha_primer_vencimiento=parse_dt("fecha_primer_vencimiento"),
        asesor_apertura_id=data.get("asesor_apertura_id"),
        supervisor_cierre_id=data.get("supervisor_cierre_id"),
        estado_plan=data.get("estado_plan", "ACTIVO"),
        estado_admision=data.get("estado_admision"),
        notas=data.get("notas", ""),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"ok": True, "id": v.id}


@router.post("/ventas/financiada/{venta_id}/pago")
async def registrar_pago_ext(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Registra un pago de cuota en una venta financiada.

    Body: monto*, notas, fecha_pago (ISO, default=ahora)
    """
    v = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    data = await request.json()
    if not data.get("monto"):
        raise HTTPException(400, "monto es obligatorio")

    fecha_pago = datetime.now()
    if data.get("fecha_pago"):
        try:
            fecha_pago = datetime.fromisoformat(data["fecha_pago"])
        except Exception:
            raise HTTPException(400, "fecha_pago inválida")

    pago = Pago(
        venta_financiada_id=venta_id,
        monto=float(data["monto"]),
        fecha_pago=fecha_pago,
        notas=data.get("notas", ""),
    )
    db.add(pago)
    v.cuotas_pagas = (v.cuotas_pagas or 0) + 1
    if v.cuotas_pagas >= v.cantidad_cuotas:
        v.estado_plan = "FINALIZADO"
    elif v.estado_plan == "ATRASADO":
        v.estado_plan = "ACTIVO"
    db.commit()
    return {"ok": True, "cuotas_pagas": v.cuotas_pagas, "estado_plan": v.estado_plan}


# ═══════════════════════════════════════════════════════════════════════════════
# COBRANZAS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/cobranzas/vencidas")
async def cobranzas_vencidas_ext(
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista planes financiados en estado ATRASADO con detalle de cuotas."""
    vencidas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan == "ATRASADO"
    ).order_by(VentaFinanciada.fecha_primer_vencimiento.asc()).all()

    return {
        "total": len(vencidas),
        "ventas": [_venta_fin_dict(v) for v in vencidas],
    }


@router.get("/cobranzas/buscar")
async def buscar_cliente_cobranza(
    telefono: Optional[str] = None,
    nombre: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Busca un cliente en ventas financiadas por teléfono o nombre."""
    q = db.query(VentaFinanciada)
    if telefono:
        q = q.filter(VentaFinanciada.cliente_telefono.ilike(f"%{telefono}%"))
    if nombre:
        q = q.filter(VentaFinanciada.cliente_nombre.ilike(f"%{nombre}%"))
    ventas = q.order_by(VentaFinanciada.created_at.desc()).limit(10).all()
    return {"total": len(ventas), "ventas": [_venta_fin_dict(v) for v in ventas]}


@router.post("/cobranzas/{venta_id}/gestion")
async def registrar_gestion_cobranza_ext(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Registra una gestión de cobranza.

    Body:
      canal*  (WHATSAPP|LLAMADA|PRESENCIAL)
      resultado*  (PROMETIO_PAGAR|PAGO|NO_CONTESTO|RECLAMA|ACUERDO_ESPECIAL)
      notas
    """
    v = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not v:
        raise HTTPException(404, "Venta no encontrada")
    data = await request.json()
    if not data.get("canal") or not data.get("resultado"):
        raise HTTPException(400, "canal y resultado son obligatorios")

    g = GestionCobranza(
        venta_financiada_id=venta_id,
        canal=data["canal"].upper(),
        resultado=data["resultado"].upper(),
        notas=data.get("notas", ""),
    )
    db.add(g)
    db.commit()
    return {"ok": True, "id": g.id}


# ═══════════════════════════════════════════════════════════════════════════════
# FÁBRICA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/fabrica/ordenes")
async def list_ordenes_ext(
    tipo: Optional[str] = None,   # "piscina" | "modulo"
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista órdenes de fábrica de piscinas y/o módulos."""
    result = {"piscinas": [], "modulos": []}

    if not tipo or tipo == "piscina":
        q = db.query(OrdenFabricaPiscina)
        if estado:
            q = q.filter(OrdenFabricaPiscina.estado == estado.upper())
        result["piscinas"] = [
            {
                "id": o.id, "cliente": o.cliente_nombre, "modelo": o.modelo, "color": o.color,
                "estado": o.estado, "fecha_inicio": o.fecha_inicio.isoformat() if o.fecha_inicio else "",
                "fecha_estimada_fin": o.fecha_estimada_fin.isoformat() if o.fecha_estimada_fin else "",
                "notas": o.notas or "",
            }
            for o in q.order_by(OrdenFabricaPiscina.created_at.desc()).all()
        ]

    if not tipo or tipo == "modulo":
        q = db.query(OrdenFabricaModulo)
        if estado:
            q = q.filter(OrdenFabricaModulo.estado == estado.upper())
        result["modulos"] = [
            {
                "id": o.id, "cliente": o.cliente_nombre, "superficie_m2": o.superficie_m2,
                "estado": o.estado, "configuracion": o.configuracion or "",
                "fecha_inicio": o.fecha_inicio.isoformat() if o.fecha_inicio else "",
                "fecha_estimada_fin": o.fecha_estimada_fin.isoformat() if o.fecha_estimada_fin else "",
                "notas": o.notas or "",
            }
            for o in q.order_by(OrdenFabricaModulo.created_at.desc()).all()
        ]

    return result


@router.patch("/fabrica/ordenes/{orden_id}")
async def update_orden_fabrica_ext(
    orden_id: int,
    request: Request,
    tipo: str = "piscina",   # query param: piscina | modulo
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Actualiza estado/notas de una orden de fábrica.
    tipo=piscina (default) | modulo
    Estados válidos: EN_ESPERA, EN_PROCESO, TERMINADA, ENTREGADA
    """
    if tipo == "modulo":
        orden = db.query(OrdenFabricaModulo).filter(OrdenFabricaModulo.id == orden_id).first()
    else:
        orden = db.query(OrdenFabricaPiscina).filter(OrdenFabricaPiscina.id == orden_id).first()

    if not orden:
        raise HTTPException(404, "Orden no encontrada")

    data = await request.json()
    for campo in ["estado", "notas"]:
        if campo in data:
            setattr(orden, campo, data[campo])
    if "fecha_estimada_fin" in data:
        try:
            orden.fecha_estimada_fin = datetime.fromisoformat(data["fecha_estimada_fin"])
        except Exception:
            raise HTTPException(400, "fecha_estimada_fin inválida")

    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/stock/piscinas")
async def stock_piscinas_ext(
    modelo: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Consulta stock de piscinas. Filtro opcional por modelo."""
    q = db.query(StockPiscina)
    if modelo:
        q = q.filter(StockPiscina.modelo.ilike(f"%{modelo}%"))
    items = q.order_by(StockPiscina.modelo).all()
    return {
        "total_items": len(items),
        "stock": [
            {"id": s.id, "modelo": s.modelo, "color": s.color, "cantidad": s.cantidad,
             "disponible": s.cantidad > 0}
            for s in items
        ],
    }


@router.get("/stock/paneles")
async def stock_paneles_ext(
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Consulta stock de paneles NCE con alertas de mínimo."""
    items = db.query(StockPanel).order_by(StockPanel.tipo_panel).all()
    return {
        "total_items": len(items),
        "stock": [
            {
                "id": s.id, "tipo_panel": s.tipo_panel, "cantidad": s.cantidad,
                "stock_minimo": s.stock_minimo,
                "bajo_minimo": s.cantidad < s.stock_minimo,
            }
            for s in items
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LOGÍSTICA / ENTREGAS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/logistica/entregas")
async def list_entregas_ext(
    estado: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista entregas/instalaciones coordinadas."""
    q = db.query(Entrega)
    if estado:
        q = q.filter(Entrega.estado == estado.upper())
    if fecha_desde:
        q = q.filter(Entrega.fecha_instalacion >= datetime.fromisoformat(fecha_desde))
    if fecha_hasta:
        q = q.filter(Entrega.fecha_instalacion <= datetime.fromisoformat(fecha_hasta))

    total = q.count()
    entregas = q.order_by(Entrega.fecha_instalacion.asc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "entregas": [
            {
                "id": e.id, "cliente_nombre": e.cliente_nombre,
                "cliente_localidad": e.cliente_localidad or "",
                "producto": e.producto or "", "estado": e.estado or "",
                "fecha_instalacion": e.fecha_instalacion.isoformat() if e.fecha_instalacion else "",
                "rango_horario": e.rango_horario or "",
                "equipo_asignado": e.equipo_asignado or "",
                "confirmada": e.confirmada,
                "notas": e.notas or "",
            }
            for e in entregas
        ],
    }


@router.patch("/logistica/entregas/{entrega_id}")
async def update_entrega_ext(
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Actualiza estado/notas de una entrega.
    Estados: COORDINADA, EN_CAMINO, INSTALADA, CON_PROBLEMA
    """
    e = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if not e:
        raise HTTPException(404, "Entrega no encontrada")
    data = await request.json()
    for campo in ["estado", "notas", "equipo_asignado", "rango_horario", "confirmada"]:
        if campo in data:
            setattr(e, campo, data[campo])
    if "fecha_instalacion" in data:
        try:
            e.fecha_instalacion = datetime.fromisoformat(data["fecha_instalacion"])
        except Exception:
            raise HTTPException(400, "fecha_instalacion inválida")
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# RECLAMOS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/reclamos")
async def list_reclamos_ext(
    estado: Optional[str] = None,
    telefono: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista reclamos activos o filtrados por estado/teléfono."""
    q = db.query(Reclamo)
    if estado:
        q = q.filter(Reclamo.estado == estado.upper())
    if telefono:
        q = q.filter(Reclamo.cliente_telefono.ilike(f"%{telefono}%"))

    total = q.count()
    reclamos = q.order_by(Reclamo.fecha_reclamo.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "reclamos": [
            {
                "id": r.id, "cliente_nombre": r.cliente_nombre,
                "cliente_telefono": r.cliente_telefono or "",
                "descripcion": r.descripcion or "", "estado": r.estado or "",
                "solucion": r.solucion or "",
                "fecha_reclamo": r.fecha_reclamo.isoformat() if r.fecha_reclamo else "",
                "fecha_resolucion": r.fecha_resolucion.isoformat() if r.fecha_resolucion else "",
                "venta_contado_id": r.venta_contado_id,
                "venta_financiada_id": r.venta_financiada_id,
            }
            for r in reclamos
        ],
    }


@router.post("/reclamos")
async def create_reclamo_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea un reclamo de cliente.

    Body:
      cliente_nombre*, cliente_telefono, descripcion*,
      venta_contado_id, venta_financiada_id, responsable_id
    """
    data = await request.json()
    if not data.get("cliente_nombre") or not data.get("descripcion"):
        raise HTTPException(400, "cliente_nombre y descripcion son obligatorios")

    r = Reclamo(
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        descripcion=data["descripcion"],
        estado="NUEVO",
        venta_contado_id=data.get("venta_contado_id"),
        venta_financiada_id=data.get("venta_financiada_id"),
        responsable_id=data.get("responsable_id"),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": r.id}


@router.patch("/reclamos/{reclamo_id}")
async def update_reclamo_ext(
    reclamo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Actualiza estado/solución de un reclamo.
    Estados: NUEVO, EN_GESTION, RESUELTO
    """
    r = db.query(Reclamo).filter(Reclamo.id == reclamo_id).first()
    if not r:
        raise HTTPException(404, "Reclamo no encontrado")
    data = await request.json()
    for campo in ["estado", "solucion", "responsable_id"]:
        if campo in data:
            setattr(r, campo, data[campo])
    if data.get("estado") == "RESUELTO" and not r.fecha_resolucion:
        r.fecha_resolucion = datetime.now()
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# ASESORES
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# GASTOS (registro rápido desde Zapia/WhatsApp)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/gastos")
async def registrar_gasto_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Registra un gasto operativo desde Zapia / WhatsApp.
    Vincula automáticamente a ventas/entregas/órdenes si se indica cliente_nombre.

    Body:
      monto*         float   — importe del gasto
      descripcion*   str     — qué se compró / para qué
      categoria      str     — MATERIALES|COMBUSTIBLE|COMIDA|HERRAMIENTAS|FLETE|
                               INSTALACION|PRODUCCION|ADMINISTRATIVO|VEHICULO|SUELDO|OTRO
      sector         str     — FABRICA|OPERACIONES|VENTAS|ADMINISTRACION|GENERAL
      proveedor      str     — nombre del proveedor / negocio
      cliente_nombre str     — activa auto-vinculación a venta/entrega/orden
      imagen_url     str     — URL de la foto/comprobante (si ya fue subida)
      notas          str     — notas adicionales
      fecha          str     — ISO date, default hoy
    """
    data = await request.json()

    if not data.get("monto") or float(data.get("monto", 0)) <= 0:
        raise HTTPException(400, "monto debe ser mayor a 0")
    if not data.get("descripcion", "").strip():
        raise HTTPException(400, "descripcion es obligatoria")

    from datetime import date as _date
    fecha = _date.today()
    if data.get("fecha"):
        try:
            fecha = datetime.fromisoformat(data["fecha"]).date()
        except Exception:
            pass

    gasto = Gasto(
        fecha=fecha,
        monto=float(data["monto"]),
        descripcion=data["descripcion"].strip(),
        categoria=data.get("categoria", "OTRO"),
        sector=data.get("sector", "GENERAL"),
        proveedor=data.get("proveedor", ""),
        imagen_url=data.get("imagen_url", ""),
        notas=data.get("notas", ""),
        cliente_nombre=data.get("cliente_nombre", ""),
        estado="REGISTRADO",
        origen="ZAPIA",
    )

    from routers.gastos import _autolink as _autolink_gasto
    _autolink_gasto(db, gasto, gasto.cliente_nombre)

    db.add(gasto)
    db.commit()
    db.refresh(gasto)

    vinculo = ""
    if gasto.entrega_id:
        vinculo = f"entrega #{gasto.entrega_id}"
    elif gasto.orden_piscina_id:
        vinculo = f"orden piscina #{gasto.orden_piscina_id}"
    elif gasto.orden_modulo_id:
        vinculo = f"orden módulo #{gasto.orden_modulo_id}"
    elif gasto.venta_contado_id:
        vinculo = f"venta contado #{gasto.venta_contado_id}"
    elif gasto.venta_financiada_id:
        vinculo = f"venta financiada #{gasto.venta_financiada_id}"

    return {
        "ok": True,
        "id": gasto.id,
        "monto": gasto.monto,
        "descripcion": gasto.descripcion,
        "sector": gasto.sector,
        "categoria": gasto.categoria,
        "vinculado_a": vinculo or None,
        "fecha": gasto.fecha.isoformat(),
    }


@router.get("/gastos")
async def list_gastos_ext(
    sector: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Lista gastos operativos. Filtros opcionales: sector, desde (fecha ISO), hasta (fecha ISO).
    """
    q = db.query(Gasto)
    if sector:
        q = q.filter(Gasto.sector == sector.upper())
    if desde:
        try:
            q = q.filter(Gasto.fecha >= datetime.fromisoformat(desde).date())
        except Exception:
            pass
    if hasta:
        try:
            q = q.filter(Gasto.fecha <= datetime.fromisoformat(hasta).date())
        except Exception:
            pass

    total = q.count()
    gastos = q.order_by(Gasto.fecha.desc(), Gasto.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "gastos": [
            {
                "id": g.id,
                "fecha": g.fecha.isoformat() if g.fecha else "",
                "monto": g.monto,
                "descripcion": g.descripcion or "",
                "categoria": g.categoria or "",
                "sector": g.sector or "",
                "proveedor": g.proveedor or "",
                "cliente_nombre": g.cliente_nombre or "",
                "imagen_url": g.imagen_url or "",
                "estado": g.estado or "",
                "origen": g.origen or "",
            }
            for g in gastos
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO & COTIZACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/catalogo")
async def catalogo_ext(_: bool = Depends(require_api_key)):
    """
    Devuelve el catálogo completo de productos con modelos, colores y precios.
    Útil para que Zapia responda consultas de precio sin intervención humana.
    """
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    piscinas = cat.get("piscinas", {})
    modulos = cat.get("modulos", {})

    precios_piscinas = piscinas.get("precios", {})
    precios_modulos = modulos.get("precios", {})
    superficies = modulos.get("superficies_m2", [])

    piscinas_out = []
    for modelo in piscinas.get("modelos", []):
        colores = piscinas.get("colores", [])
        precio = precios_piscinas.get(modelo)
        piscinas_out.append({
            "modelo": modelo,
            "colores_disponibles": colores,
            "precio": precio,
            "tiene_precio": precio is not None,
        })

    modulos_out = []
    for m2 in superficies:
        nombre = f"Módulo {m2}m²"
        precio = precios_modulos.get(str(m2)) or precios_modulos.get(m2)
        modulos_out.append({
            "nombre": nombre,
            "superficie_m2": m2,
            "precio": precio,
            "tiene_precio": precio is not None,
            "apto_via_cargo": m2 <= 24,  # módulos hasta 24m² aptos para transporte
        })

    return {
        "piscinas": piscinas_out,
        "modulos": modulos_out,
        "colores_piscinas": piscinas.get("colores", []),
        "tecnologia_modulos": modulos.get("tecnologia", "NCE"),
        "nota": "Los módulos de hasta 24m² son aptos para envío por Vía Cargo u otras empresas de transporte terrestre.",
    }


@router.get("/cotizar")
async def cotizar_ext(
    producto: str,
    modelo: Optional[str] = None,
    localidad: Optional[str] = None,
    forma_pago: Optional[str] = None,
    _: bool = Depends(require_api_key),
):
    """
    Cotización rápida de un producto.
    producto: PISCINA | MODULO
    modelo: nombre del modelo o 'Módulo 24m²'
    localidad: ciudad del cliente (para info de envío)
    forma_pago: CONTADO | FINANCIADO | VIA_CARGO
    """
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    producto = producto.upper()
    precio = None
    info_producto = {}

    if producto == "PISCINA":
        precios = cat.get("piscinas", {}).get("precios", {})
        modelos = cat.get("piscinas", {}).get("modelos", [])
        colores = cat.get("piscinas", {}).get("colores", [])
        if modelo:
            precio = precios.get(modelo)
        info_producto = {
            "tipo": "Piscina",
            "modelos_disponibles": modelos,
            "colores_disponibles": colores,
        }

    elif producto == "MODULO":
        precios = cat.get("modulos", {}).get("precios", {})
        superficies = cat.get("modulos", {}).get("superficies_m2", [])
        if modelo:
            # Extraer m2 del nombre: "Módulo 24m²" → 24
            import re
            m = re.search(r"(\d+)", modelo)
            if m:
                m2 = int(m.group(1))
                precio = precios.get(str(m2)) or precios.get(m2)
                apto_cargo = m2 <= 24
            else:
                apto_cargo = None
        else:
            apto_cargo = None
        info_producto = {
            "tipo": "Módulo habitable NCE",
            "superficies_disponibles_m2": superficies,
            "apto_via_cargo": apto_cargo,
            "tecnologia": "NCE — estructura modular liviana, armado en destino",
        }
    else:
        return {"error": f"producto '{producto}' no reconocido. Usar PISCINA o MODULO"}

    respuesta = {
        "producto": producto,
        "modelo": modelo,
        **info_producto,
        "precio_base": precio,
        "tiene_precio": precio is not None,
        "forma_pago_solicitada": forma_pago,
        "info_envio": {
            "via_cargo": "Despachamos por Vía Cargo u otras empresas de transporte terrestre a todo el país.",
            "instalacion_propia": "También realizamos instalación con nuestro equipo en zonas de cobertura.",
            "consulta_localidad": localidad or "No especificada",
        },
        "proximos_pasos": [
            "Confirmar modelo y color",
            "Informar localidad y sucursal Vía Cargo más cercana",
            "Acordar fecha de despacho",
            "Transferir anticipo o pago total",
        ] if precio else [
            "Consultar precio actualizado con el equipo de ventas",
        ],
    }

    if not precio:
        respuesta["aviso"] = f"No hay precio cargado para '{modelo}'. El asesor te cotizará personalmente."

    return respuesta


@router.get("/ranking")
async def ranking_ext(
    periodo: str = "mes",
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Ranking de ventas por asesor (contado + financiadas).
    periodo: dia | semana | mes
    """
    hoy = datetime.now()
    if periodo == "dia":
        inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "semana":
        inicio = (hoy - timedelta(days=hoy.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        inicio = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    vc_rows = (
        db.query(VentaContado.vendedor_id, sqlfunc.count(VentaContado.id).label("cnt"),
                 sqlfunc.coalesce(sqlfunc.sum(VentaContado.precio_final), 0).label("monto"))
        .filter(VentaContado.created_at >= inicio, VentaContado.vendedor_id.isnot(None))
        .group_by(VentaContado.vendedor_id).all()
    )
    vf_rows = (
        db.query(VentaFinanciada.asesor_apertura_id, sqlfunc.count(VentaFinanciada.id).label("cnt"),
                 sqlfunc.coalesce(sqlfunc.sum(VentaFinanciada.precio_total), 0).label("monto"))
        .filter(VentaFinanciada.created_at >= inicio, VentaFinanciada.asesor_apertura_id.isnot(None))
        .group_by(VentaFinanciada.asesor_apertura_id).all()
    )
    totales: dict = {}
    for r in vc_rows:
        t = totales.setdefault(r.vendedor_id, {"vc": 0, "vf": 0, "monto": 0.0})
        t["vc"] += r.cnt; t["monto"] += float(r.monto)
    for r in vf_rows:
        t = totales.setdefault(r.asesor_apertura_id, {"vc": 0, "vf": 0, "monto": 0.0})
        t["vf"] += r.cnt; t["monto"] += float(r.monto)

    if not totales:
        return {"periodo": periodo, "ranking": [], "mensaje": "Sin ventas en este período"}

    nombres = {u.id: u.nombre for u in db.query(Usuario).filter(Usuario.id.in_(list(totales.keys()))).all()}
    ranking = sorted([
        {"posicion": 0, "nombre": nombres.get(uid, f"#{uid}"), "total_ventas": t["vc"] + t["vf"],
         "ventas_contado": t["vc"], "ventas_financiadas": t["vf"], "monto_total": round(t["monto"], 2)}
        for uid, t in totales.items()
    ], key=lambda x: x["monto_total"], reverse=True)
    for i, r in enumerate(ranking):
        r["posicion"] = i + 1
    return {"periodo": periodo, "ranking": ranking[:10]}


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK EXTENDIDO
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/stock/disponible")
async def stock_disponible_ext(
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Vista unificada del stock disponible: piscinas + paneles NCE.
    Incluye precio si está en el catálogo y si el producto es apto para Vía Cargo.
    Ideal para que Zapia informe qué hay disponible para entrega inmediata.
    """
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    precios_piscinas = cat.get("piscinas", {}).get("precios", {})

    piscinas = db.query(StockPiscina).filter(StockPiscina.cantidad > 0).order_by(StockPiscina.modelo).all()
    paneles  = db.query(StockPanel).filter(StockPanel.cantidad > 0).order_by(StockPanel.tipo_panel).all()

    piscinas_out = []
    for p in piscinas:
        precio = precios_piscinas.get(p.modelo)
        piscinas_out.append({
            "id": p.id,
            "producto": "PISCINA",
            "modelo": p.modelo,
            "color": p.color or "",
            "cantidad": p.cantidad,
            "precio": precio,
            "apto_via_cargo": True,
            "descripcion_corta": f"Piscina {p.modelo}" + (f" color {p.color}" if p.color else ""),
        })

    paneles_out = []
    for p in paneles:
        paneles_out.append({
            "id": p.id,
            "producto": "PANEL_NCE",
            "tipo": p.tipo_panel,
            "cantidad": p.cantidad,
            "stock_minimo": p.stock_minimo,
            "descripcion_corta": f"Panel NCE {p.tipo_panel}",
        })

    resumen_texto = ""
    if piscinas_out:
        items = [f"{p['cantidad']}x {p['descripcion_corta']}" for p in piscinas_out]
        resumen_texto += "🏊 PISCINAS DISPONIBLES: " + " | ".join(items)
    if paneles_out:
        items2 = [f"{p['cantidad']}x {p['tipo']}" for p in paneles_out]
        resumen_texto += ("\n" if resumen_texto else "") + "🏗 PANELES NCE: " + " | ".join(items2)
    if not resumen_texto:
        resumen_texto = "Sin stock disponible actualmente."

    return {
        "piscinas": piscinas_out,
        "paneles_nce": paneles_out,
        "total_piscinas": sum(p["cantidad"] for p in piscinas_out),
        "total_paneles": sum(p["cantidad"] for p in paneles_out),
        "resumen_texto": resumen_texto,
        "nota_via_cargo": "Todas las piscinas en stock pueden despacharse por Vía Cargo u otras empresas de transporte.",
    }


@router.patch("/stock/piscinas/{stock_id}")
async def ajustar_stock_piscina_ext(
    stock_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Ajusta el stock de una piscina.
    Body: cantidad (nuevo valor absoluto) o ajuste (delta, puede ser negativo).
    Uno de los dos es obligatorio.
    """
    s = db.query(StockPiscina).filter(StockPiscina.id == stock_id).first()
    if not s:
        raise HTTPException(404, "Item de stock no encontrado")
    data = await request.json()
    if "cantidad" in data:
        s.cantidad = int(data["cantidad"])
    elif "ajuste" in data:
        s.cantidad = max(0, s.cantidad + int(data["ajuste"]))
    else:
        raise HTTPException(400, "Enviar 'cantidad' (valor absoluto) o 'ajuste' (delta)")
    db.commit()
    return {"ok": True, "id": s.id, "modelo": s.modelo, "color": s.color, "cantidad_nueva": s.cantidad}


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS — SEGUIMIENTOS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/leads/seguimientos-pendientes")
async def seguimientos_pendientes_ext(
    asesor_id: Optional[int] = None,
    horas: int = 0,   # 0 = vencidos ahora, N = vencen en las próximas N horas
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Leads con proximo_seguimiento vencido o próximo a vencer.
    horas=0 → ya vencidos | horas=24 → vencen en las próximas 24hs
    """
    ahora = datetime.now()
    hasta = ahora + timedelta(hours=horas) if horas else ahora
    q = db.query(Lead).filter(
        Lead.proximo_seguimiento.isnot(None),
        Lead.proximo_seguimiento <= hasta,
        Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]),
    )
    if asesor_id:
        q = q.filter(Lead.asesor_apertura_id == asesor_id)
    leads = q.order_by(Lead.proximo_seguimiento.asc()).limit(50).all()
    return {
        "total": len(leads),
        "leads": [
            {**_lead_dict(l, db), "minutos_vencido": int((ahora - l.proximo_seguimiento).total_seconds() / 60)}
            for l in leads
        ],
    }


@router.post("/leads/{lead_id}/seguimiento")
async def programar_seguimiento_ext(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Programa (o reprograma) el próximo seguimiento de un lead.
    Body:
      fecha_hora*  str  — ISO datetime, ej: "2026-05-22T10:00:00"
      nota         str  — Nota opcional sobre el motivo del seguimiento
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    data = await request.json()
    if not data.get("fecha_hora"):
        raise HTTPException(400, "fecha_hora es obligatorio (ISO format)")
    try:
        lead.proximo_seguimiento = datetime.fromisoformat(data["fecha_hora"])
    except Exception:
        raise HTTPException(400, "fecha_hora inválida. Usar ISO: 2026-05-22T10:00:00")
    if data.get("nota"):
        ts = datetime.now().strftime("%d/%m %H:%M")
        lead.notas = (lead.notas or "") + f"\n[{ts}] 📅 Seguimiento programado: {data['nota']}"
    db.commit()
    return {"ok": True, "lead_id": lead_id, "proximo_seguimiento": lead.proximo_seguimiento.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════════
# ENVÍOS VÍA CARGO
# ═══════════════════════════════════════════════════════════════════════════════

def _envio_dict(e: EnvioViaCargo) -> dict:
    return {
        "id": e.id,
        "producto": e.producto,
        "modelo_especifico": e.modelo_especifico or "",
        "color": e.color or "",
        "cantidad": e.cantidad,
        "desde_stock": e.desde_stock,
        "cliente_nombre": e.cliente_nombre,
        "cliente_telefono": e.cliente_telefono or "",
        "cliente_localidad": e.cliente_localidad or "",
        "provincia": e.provincia or "",
        "sucursal_cargo": e.sucursal_cargo or "",
        "precio_producto": e.precio_producto or 0,
        "costo_flete": e.costo_flete,
        "total": e.total or 0,
        "forma_pago": e.forma_pago or "",
        "estado": e.estado or "PENDIENTE",
        "numero_remito": e.numero_remito or "",
        "empresa_transporte": e.empresa_transporte or "VIA_CARGO",
        "fecha_despacho": e.fecha_despacho.isoformat() if e.fecha_despacho else "",
        "fecha_entrega_est": e.fecha_entrega_est.isoformat() if e.fecha_entrega_est else "",
        "fecha_entrega_real": e.fecha_entrega_real.isoformat() if e.fecha_entrega_real else "",
        "vendedor_nombre": e.vendedor.nombre if e.vendedor else "",
        "notas": e.notas or "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


@router.get("/envios")
async def list_envios_ext(
    estado: Optional[str] = None,
    cliente: Optional[str] = None,
    telefono: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista envíos por Vía Cargo u otras empresas de transporte."""
    q = db.query(EnvioViaCargo)
    if estado:
        q = q.filter(EnvioViaCargo.estado == estado.upper())
    if cliente:
        q = q.filter(EnvioViaCargo.cliente_nombre.ilike(f"%{cliente}%"))
    if telefono:
        q = q.filter(EnvioViaCargo.cliente_telefono.ilike(f"%{telefono}%"))
    total = q.count()
    envios = q.order_by(EnvioViaCargo.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "envios": [_envio_dict(e) for e in envios]}


@router.get("/envios/buscar")
async def buscar_envio_ext(
    telefono: Optional[str] = None,
    numero_remito: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Busca un envío por teléfono del cliente o número de remito."""
    q = db.query(EnvioViaCargo)
    if telefono:
        q = q.filter(EnvioViaCargo.cliente_telefono.ilike(f"%{telefono}%"))
    if numero_remito:
        q = q.filter(EnvioViaCargo.numero_remito.ilike(f"%{numero_remito}%"))
    envios = q.order_by(EnvioViaCargo.created_at.desc()).limit(10).all()
    return {"total": len(envios), "envios": [_envio_dict(e) for e in envios]}


@router.post("/envios")
async def create_envio_ext(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Crea un nuevo envío por Vía Cargo u otra empresa de transporte terrestre.
    Ideal para ventas remotas de módulos (estilo IKEA) o piscinas portables.

    Body:
      cliente_nombre*    str   — nombre del comprador
      cliente_telefono   str
      cliente_localidad  str   — ciudad destino
      provincia          str   — provincia destino
      sucursal_cargo     str   — "Via Cargo Córdoba - Av. Colón 123"
      producto*          str   — PISCINA | MODULO
      modelo_especifico  str   — "Minimalista Chica" | "Módulo 24m²"
      color              str
      cantidad           int   — default 1
      desde_stock        bool  — True si sale de stock existente (entrega rápida)
      precio_producto    float — precio acordado
      costo_flete        float — costo de envío si ya se acordó
      total              float — precio_producto + costo_flete
      forma_pago         str   — TRANSFERENCIA | CONTADO | FINANCIADO
      vendedor_id        int   — ID del asesor que cerró la venta
      notas              str
      empresa_transporte str   — default "VIA_CARGO"
    """
    data = await request.json()
    for req_campo in ["cliente_nombre", "producto"]:
        if not data.get(req_campo):
            raise HTTPException(400, f"{req_campo} es obligatorio")

    total = data.get("total") or (
        (data.get("precio_producto") or 0) + (data.get("costo_flete") or 0)
    )

    envio = EnvioViaCargo(
        cliente_nombre=data["cliente_nombre"],
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        provincia=data.get("provincia", ""),
        sucursal_cargo=data.get("sucursal_cargo", ""),
        producto=data["producto"].upper(),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color", ""),
        cantidad=int(data.get("cantidad", 1)),
        desde_stock=bool(data.get("desde_stock", False)),
        precio_producto=float(data.get("precio_producto") or 0),
        costo_flete=float(data["costo_flete"]) if data.get("costo_flete") is not None else None,
        total=float(total),
        forma_pago=data.get("forma_pago", "TRANSFERENCIA"),
        vendedor_id=data.get("vendedor_id"),
        empresa_transporte=data.get("empresa_transporte", "VIA_CARGO"),
        estado="PENDIENTE",
        notas=data.get("notas", ""),
    )
    db.add(envio)

    # Si sale de stock, decrementar automáticamente
    if envio.desde_stock and envio.producto == "PISCINA" and envio.modelo_especifico:
        stock = db.query(StockPiscina).filter(
            StockPiscina.modelo.ilike(f"%{envio.modelo_especifico}%"),
        ).first()
        if stock and stock.cantidad >= envio.cantidad:
            stock.cantidad -= envio.cantidad

    db.commit()
    db.refresh(envio)

    # Crear venta contado asociada automáticamente si tiene precio
    if envio.precio_producto > 0:
        v = VentaContado(
            cliente_nombre=envio.cliente_nombre,
            cliente_telefono=envio.cliente_telefono,
            cliente_localidad=f"{envio.cliente_localidad} ({envio.provincia})",
            producto=envio.producto,
            modelo_especifico=envio.modelo_especifico,
            color=envio.color,
            precio_final=envio.total,
            forma_pago=envio.forma_pago,
            vendedor_id=envio.vendedor_id,
            estado="COORDINADO",
            notas=f"Envío por {envio.empresa_transporte} a {envio.sucursal_cargo or envio.cliente_localidad}. Envío ID #{envio.id}",
            desde_stock=envio.desde_stock,
        )
        db.add(v)
        db.commit()
        envio.venta_contado_id = v.id
        db.commit()

    return {
        "ok": True,
        "id": envio.id,
        "venta_contado_id": envio.venta_contado_id,
        "estado": envio.estado,
        "mensaje": f"Envío creado. Cliente: {envio.cliente_nombre} | {envio.producto} {envio.modelo_especifico} → {envio.cliente_localidad}",
    }


@router.patch("/envios/{envio_id}")
async def update_envio_ext(
    envio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Actualiza el estado/tracking de un envío.
    Campos actualizables: estado, numero_remito, empresa_transporte,
    fecha_despacho, fecha_entrega_est, fecha_entrega_real, notas,
    costo_flete, sucursal_cargo.

    Estados: PENDIENTE | EMPACADO | DESPACHADO | EN_TRANSITO | ENTREGADO | PROBLEMA
    """
    e = db.query(EnvioViaCargo).filter(EnvioViaCargo.id == envio_id).first()
    if not e:
        raise HTTPException(404, "Envío no encontrado")
    data = await request.json()

    for campo in ["estado", "numero_remito", "empresa_transporte", "notas", "sucursal_cargo"]:
        if campo in data:
            setattr(e, campo, data[campo])

    for campo_dt in ["fecha_despacho", "fecha_entrega_est", "fecha_entrega_real"]:
        if campo_dt in data and data[campo_dt]:
            try:
                setattr(e, campo_dt, datetime.fromisoformat(data[campo_dt]))
            except Exception:
                raise HTTPException(400, f"{campo_dt} inválido, usar ISO format")

    if "costo_flete" in data:
        e.costo_flete = float(data["costo_flete"])
        e.total = (e.precio_producto or 0) + (e.costo_flete or 0)

    db.commit()
    return {"ok": True, "envio": _envio_dict(e)}


@router.get("/asesores")
async def list_asesores_ext(
    con_metricas: bool = True,
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Lista asesores activos con sus roles.
    con_metricas=true (default): incluye conteo de leads activos y videollamadas.
    """
    usuarios = db.query(Usuario).filter(Usuario.activo == True).order_by(Usuario.nombre).all()
    result = []
    for u in usuarios:
        try:
            roles = json.loads(u.roles_json or "[]")
        except Exception:
            roles = []

        item = {
            "id": u.id,
            "nombre": u.nombre,
            "email": u.email,
            "roles": roles,
            "es_asesor": "ASESOR_APERTURA" in roles or "SUPERVISOR_CIERRE" in roles,
        }

        if con_metricas:
            item["leads_activos"] = db.query(Lead).filter(
                Lead.asesor_apertura_id == u.id,
                Lead.estado.notin_(["CERRADO", "PERDIDO"])
            ).count()
            item["leads_total"] = db.query(Lead).filter(
                Lead.asesor_apertura_id == u.id
            ).count()
            item["vl_pendientes"] = db.query(Videollamada).filter(
                Videollamada.asesor_apertura_id == u.id,
                Videollamada.estado == "AGENDADA",
            ).count()

        result.append(item)

    return {"total": len(result), "asesores": result}


# ─── ENDPOINTS ESPECÍFICOS PARA AGENTES IA ────────────────────────────────────
# Cada agente se identifica con su agente_key personal (header X-Agent-Key).
# Estos endpoints limitan los datos al scope del agente (solo sus leads, etc.)

@router.get("/agente/perfil")
async def agente_perfil(
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Retorna el perfil del agente que hace la request."""
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")
    try:
        roles = json.loads(agente.roles_json or "[]")
    except Exception:
        roles = []
    leads_asignados = db.query(Lead).filter(
        Lead.asesor_apertura_id == agente.id,
        Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]),
    ).count()
    return {
        "id": agente.id,
        "nombre": agente.nombre,
        "email": agente.email,
        "roles": roles,
        "es_agente_ia": agente.es_agente_ia,
        "leads_activos": leads_asignados,
    }


@router.get("/agente/mis-leads")
async def agente_mis_leads(
    estado: Optional[str] = None,
    limit: int = 50,
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Retorna los leads asignados al agente que hace la request.
    Filtrable por estado. Ordenados por prioridad (NUEVO primero, luego por fecha).
    """
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")

    q = db.query(Lead).filter(Lead.asesor_apertura_id == agente.id)
    if estado:
        q = q.filter(Lead.estado == estado.upper())
    else:
        # Por defecto: solo leads activos (no cerrados)
        q = q.filter(Lead.estado.notin_(["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]))

    leads = q.order_by(Lead.created_at.asc()).limit(limit).all()
    return {
        "agente": agente.nombre,
        "total": len(leads),
        "leads": [_lead_dict(l, db) for l in leads],
    }


@router.get("/agente/mis-leads/siguiente")
async def agente_siguiente_lead(
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Retorna el siguiente lead a contactar del agente (NUEVO o INTENTADO, más antiguo).
    Ideal para el loop de trabajo del agente.
    """
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")

    lead = db.query(Lead).filter(
        Lead.asesor_apertura_id == agente.id,
        Lead.estado.in_(["NUEVO", "INTENTADO", "NO_CONTACTADO"]),
    ).order_by(Lead.created_at.asc()).first()

    if not lead:
        # Chequear si hay seguimientos vencidos
        lead = db.query(Lead).filter(
            Lead.asesor_apertura_id == agente.id,
            Lead.estado.in_(["CONTACTADO", "EN_SEGUIMIENTO"]),
            Lead.proximo_seguimiento <= datetime.utcnow(),
        ).order_by(Lead.proximo_seguimiento.asc()).first()

    if not lead:
        return {"lead": None, "mensaje": "Sin leads pendientes. Buen trabajo 🎉"}

    return {"lead": _lead_dict(lead, db)}


@router.post("/agente/leads/{lead_id}/contactar")
async def agente_registrar_contacto(
    lead_id: int,
    request: Request,
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Registra un intento de contacto del agente sobre un lead.
    Actualiza estado, agrega nota y programa próximo seguimiento si se indica.
    """
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    resultado = data.get("resultado", "INTENTADO")  # CONTACTADO | INTENTADO | NO_CONTESTO | VL_AGENDADA
    nota = data.get("nota", "")
    proximo_seg = data.get("proximo_seguimiento")  # ISO datetime

    ts = datetime.now().strftime("%d/%m %H:%M")
    nota_log = f"[{ts}] 🤖 {agente.nombre}: {nota or resultado}"

    # Actualizar estado según resultado
    if resultado == "CONTACTADO":
        lead.estado = "CONTACTADO"
    elif resultado == "VL_AGENDADA":
        lead.estado = "VIDEOLLAMADA_AGENDADA"
    elif resultado == "INTENTADO" or resultado == "NO_CONTESTO":
        if lead.estado == "NUEVO":
            lead.estado = "INTENTADO"

    lead.notas = (lead.notas or "") + "\n" + nota_log

    if proximo_seg:
        try:
            lead.proximo_seguimiento = datetime.fromisoformat(proximo_seg)
        except Exception:
            pass

    db.commit()
    return {"ok": True, "lead_id": lead_id, "nuevo_estado": lead.estado}


@router.get("/agente/mis-vls")
async def agente_mis_vls(
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """Lista las videollamadas agendadas del agente."""
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")

    vls = db.query(Videollamada).filter(
        Videollamada.asesor_apertura_id == agente.id,
        Videollamada.estado == "AGENDADA",
    ).order_by(Videollamada.fecha_hora.asc()).all()

    return {
        "total": len(vls),
        "videollamadas": [
            {
                "id": vl.id,
                "cliente_nombre": vl.cliente_nombre,
                "cliente_telefono": vl.cliente_telefono or "",
                "producto_interes": vl.producto_interes or "",
                "fecha_hora": vl.fecha_hora.isoformat() if vl.fecha_hora else "",
                "estado": vl.estado,
                "resultado": vl.resultado,
                "notas": vl.notas or "",
            }
            for vl in vls
        ],
    }


@router.post("/agente/leads/{lead_id}/agendar-vl")
async def agente_agendar_vl(
    lead_id: int,
    request: Request,
    x_agent_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_api_key),
):
    """
    Agenda una videollamada desde el agente.
    Crea el registro de VL y actualiza el estado del lead automáticamente.
    """
    agente = resolve_agente(x_agent_key, db)
    if not agente:
        raise HTTPException(401, "X-Agent-Key inválida o no es agente IA")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    fecha_str = data.get("fecha_hora")
    if not fecha_str:
        raise HTTPException(400, "fecha_hora es obligatorio (ISO format)")

    try:
        fecha_dt = datetime.fromisoformat(fecha_str)
    except Exception:
        raise HTTPException(400, "formato de fecha inválido, usar ISO 8601")

    vl = Videollamada(
        lead_id=lead.id,
        cliente_nombre=lead.nombre,
        cliente_telefono=lead.telefono,
        producto_interes=lead.producto_interes or "SIN_DEFINIR",
        forma_pago=lead.forma_pago or "SIN_DEFINIR",
        asesor_apertura_id=agente.id,
        fecha_hora=fecha_dt,
        estado="AGENDADA",
        resultado="PENDIENTE",
        notas=data.get("notas", ""),
    )
    db.add(vl)
    lead.estado = "VIDEOLLAMADA_AGENDADA"
    ts = datetime.now().strftime("%d/%m %H:%M")
    lead.notas = (lead.notas or "") + f"\n[{ts}] 🤖 {agente.nombre}: VL agendada para {fecha_dt.strftime('%d/%m %H:%M')}"
    db.commit()
    db.refresh(vl)
    return {"ok": True, "vl_id": vl.id, "lead_estado": lead.estado}
