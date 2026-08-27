"""
Módulo Aliados Comerciales — canal de venta por referidos.

Extensión sobre el CRM existente: no reemplaza nada. Agrega el alta y gestión de
aliados, el devengamiento de comisiones, la auditoría de paquetes 🟡 enviados por
Franco y la numeración correlativa de solicitudes.

Autenticación dual en todos los endpoints:
  - sesión del CRM (usuarios internos), o
  - header X-API-Key (para Franco / integraciones externas)
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from database.database import get_db
from database.models import (
    Aliado, Comision, AuditoriaPaquete, SolicitudContador,
    Lead, Usuario, VentaContado,
)
from routers.auth import get_current_user, get_user_roles, require_auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ─── PÁGINA (panel de gestión) ────────────────────────────────────────────────

@router.get("/aliados", response_class=HTMLResponse)
async def aliados_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_GESTION):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("aliados.html", {
        "request": request, "user": current_user, "roles": roles,
    })

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")

ESTADOS_ALIADO = ("postulante", "en_evaluacion", "activo", "inactivo", "suspendido", "rechazado")
ESTADOS_VERIFICACION = ("pendiente", "verificado", "rechazado")
TIPOS_COMISION = ("entrada", "cuota_3", "contado")
RESULTADOS_PAQUETE = ("OK", "FALTA", "RECHAZO", "sin_respuesta")

ROLES_GESTION = ("ADMIN", "SUPERVISOR_CIERRE", "ADMINISTRACION")


# ─── AUTENTICACIÓN ────────────────────────────────────────────────────────────

def _auth(x_api_key: Optional[str], current_user: Optional[Usuario]) -> Optional[Usuario]:
    """Permite sesión CRM o API key (Franco). Devuelve el usuario si es sesión."""
    if x_api_key and x_api_key == API_KEY:
        return current_user
    if current_user:
        return current_user
    raise HTTPException(401, "No autorizado")


def _solo_gestion(current_user: Optional[Usuario], x_api_key: Optional[str]):
    """Acciones sensibles: sólo roles de gestión o API key de Franco."""
    if x_api_key and x_api_key == API_KEY:
        return
    if current_user and any(r in get_user_roles(current_user) for r in ROLES_GESTION):
        return
    raise HTTPException(403, "Sin permisos para esta operación")


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _aliado_dict(a: Aliado) -> dict:
    return {
        "id": a.id,
        "codigo": a.codigo,
        "nombre": a.nombre,
        "dni": a.dni or "",
        "cuit_monotributo": a.cuit_monotributo or "",
        "telefono": a.telefono or "",
        "cbu_alias": a.cbu_alias or "",
        "zona": a.zona or "",
        "estado": a.estado or "postulante",
        "fecha_alta": a.fecha_alta.isoformat() if a.fecha_alta else None,
        "contrato_firmado": bool(a.contrato_firmado),
        "operativo": (a.estado == "activo" and bool(a.contrato_firmado)),
        "tiene_pin": bool(a.pin),
        "notas": a.notas or "",
    }


def _comision_dict(c: Comision) -> dict:
    return {
        "id": c.id,
        "aliado_codigo": c.aliado_codigo,
        "solicitud_numero": c.solicitud_numero or "",
        "tipo": c.tipo,
        "monto": c.monto or 0,
        "estado": c.estado,
        "fecha_liquidacion": c.fecha_liquidacion.isoformat() if c.fecha_liquidacion else None,
        "ajuste_manual": bool(c.ajuste_manual),
        "ajuste_motivo": c.ajuste_motivo or "",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _generar_codigo_aliado(db: Session) -> str:
    """Próximo código correlativo AL-XXX."""
    ultimo = db.query(Aliado).order_by(Aliado.id.desc()).first()
    n = 1
    if ultimo and ultimo.codigo and ultimo.codigo.upper().startswith("AL-"):
        try:
            n = int(ultimo.codigo.split("-")[-1]) + 1
        except Exception:
            n = (ultimo.id or 0) + 1
    elif ultimo:
        n = (ultimo.id or 0) + 1
    return f"AL-{n:03d}"


def siguiente_numero_solicitud(db: Session) -> str:
    """
    Asigna el próximo número de solicitud de forma atómica e irrepetible.
    Continuidad garantizada: la semilla deja el contador en 13860152, por lo que
    el primer número emitido por este flujo es 000-13860153.
    No editable a mano: es la única vía de asignación.
    """
    contador = db.query(SolicitudContador).filter(SolicitudContador.id == 1).first()
    if not contador:
        # Semilla defensiva por si la migración no llegó a correr
        contador = SolicitudContador(id=1, prefijo="000", ultimo_numero=13860152)
        db.add(contador)
        db.flush()
    contador.ultimo_numero = (contador.ultimo_numero or 13860152) + 1
    db.commit()
    db.refresh(contador)
    return f"{contador.prefijo}-{contador.ultimo_numero}"


# ═══════════════════════════════════════════════════════════════════════════════
# ALIADOS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/aliados")
async def crear_aliado(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Alta de aliado (post-aprobación de postulación). Genera el código AL-XXX."""
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    data = await request.json()

    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre es obligatorio")

    estado = (data.get("estado") or "postulante").lower()
    if estado not in ESTADOS_ALIADO:
        raise HTTPException(400, f"Estado inválido. Válidos: {', '.join(ESTADOS_ALIADO)}")

    codigo = (data.get("codigo") or "").strip().upper() or _generar_codigo_aliado(db)
    if db.query(Aliado).filter(Aliado.codigo == codigo).first():
        raise HTTPException(409, f"Ya existe un aliado con código {codigo}")

    dni = (data.get("dni") or "").strip()
    if dni and db.query(Aliado).filter(Aliado.dni == dni, Aliado.dni != "").first():
        raise HTTPException(409, f"Ya existe un aliado con DNI {dni}")

    aliado = Aliado(
        codigo=codigo,
        nombre=nombre,
        dni=dni,
        cuit_monotributo=(data.get("cuit_monotributo") or "").strip(),
        telefono=(data.get("telefono") or "").strip(),
        cbu_alias=(data.get("cbu_alias") or "").strip(),
        zona=(data.get("zona") or "").strip(),
        estado=estado,
        contrato_firmado=bool(data.get("contrato_firmado", False)),
        pin=(data.get("pin") or "").strip() or None,
        notas=data.get("notas", ""),
    )
    db.add(aliado)
    db.commit()
    db.refresh(aliado)
    return {"ok": True, **_aliado_dict(aliado)}


@router.get("/api/aliados")
async def listar_aliados(
    estado: Optional[str] = None,
    zona: Optional[str] = None,
    search: Optional[str] = None,
    telefono: Optional[str] = Query(None, description="Busca por sufijo de teléfono (WhatsApp del aliado)"),
    inactivos_dias: Optional[int] = Query(None, description="Aliados sin actividad en los últimos N días"),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Listado de aliados con filtros (incluye postulantes de la landing)."""
    _auth(x_api_key, current_user)
    q = db.query(Aliado)
    if estado:
        q = q.filter(Aliado.estado == estado.lower())
    if zona:
        q = q.filter(Aliado.zona.ilike(f"%{zona}%"))
    if telefono:
        solo_digitos = "".join(c for c in telefono if c.isdigit())
        if solo_digitos:
            q = q.filter(Aliado.telefono.ilike(f"%{solo_digitos[-8:]}%"))
    if search:
        q = q.filter(
            (Aliado.nombre.ilike(f"%{search}%"))
            | (Aliado.codigo.ilike(f"%{search}%"))
            | (Aliado.dni.ilike(f"%{search}%"))
        )
    if inactivos_dias is not None:
        # Aliados activos sin leads cargados en los últimos N días
        desde = datetime.now() - timedelta(days=inactivos_dias)
        codigos_con_actividad = {
            row[0]
            for row in db.query(Lead.aliado_codigo)
            .filter(Lead.aliado_codigo.isnot(None))
            .filter(Lead.created_at >= desde)
            .all()
        }
        q = q.filter(Aliado.estado == "activo")
        if codigos_con_actividad:
            q = q.filter(Aliado.codigo.notin_(codigos_con_actividad))
    aliados = q.order_by(Aliado.id.desc()).all()
    return {"total": len(aliados), "aliados": [_aliado_dict(a) for a in aliados]}


@router.get("/api/aliados/ranking")
async def ranking_aliados(
    periodo: str = Query("semana", pattern="^(semana|mes|trimestre|año|anio|total)$"),
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Ranking de aliados por período — usado para el reporte de los viernes."""
    _auth(x_api_key, current_user)

    dias = {"semana": 7, "mes": 30, "trimestre": 90, "año": 365, "anio": 365}.get(periodo)
    desde = datetime.now() - timedelta(days=dias) if dias else None

    filas = []
    for a in db.query(Aliado).filter(Aliado.estado == "activo").all():
        q_leads = db.query(Lead).filter(Lead.aliado_codigo == a.codigo)
        if desde is not None:
            q_leads = q_leads.filter(Lead.created_at >= desde)
        leads = q_leads.all()

        q_com = db.query(Comision).filter(Comision.aliado_codigo == a.codigo)
        if desde is not None:
            q_com = q_com.filter(Comision.created_at >= desde)
        comisiones = q_com.all()

        filas.append({
            "codigo": a.codigo,
            "nombre": a.nombre,
            "zona": a.zona or "",
            "leads_cargados": len(leads),
            "leads_verificados": sum(1 for l in leads if (l.estado_verificacion or "") == "verificado"),
            "comisiones_generadas": len(comisiones),
            "monto_total": round(sum(c.monto or 0 for c in comisiones), 2),
            "monto_pendiente": round(sum(c.monto or 0 for c in comisiones if c.estado == "pendiente"), 2),
        })

    filas.sort(key=lambda x: (x["leads_verificados"], x["monto_total"]), reverse=True)
    for i, f in enumerate(filas, 1):
        f["puesto"] = i
    return {"periodo": periodo, "desde": desde.isoformat() if desde else None, "ranking": filas}


@router.get("/api/aliados/{codigo}")
async def get_aliado(
    codigo: str,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Datos + estado del aliado."""
    _auth(x_api_key, current_user)
    a = db.query(Aliado).filter(Aliado.codigo == codigo.upper()).first()
    if not a:
        raise HTTPException(404, "Aliado no encontrado")
    return _aliado_dict(a)


@router.put("/api/aliados/{codigo}")
async def actualizar_aliado(
    codigo: str,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Actualiza datos/estado del aliado (ej. aprobar postulante → activo)."""
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    a = db.query(Aliado).filter(Aliado.codigo == codigo.upper()).first()
    if not a:
        raise HTTPException(404, "Aliado no encontrado")
    data = await request.json()

    if "estado" in data:
        nuevo = (data["estado"] or "").lower()
        if nuevo not in ESTADOS_ALIADO:
            raise HTTPException(400, f"Estado inválido. Válidos: {', '.join(ESTADOS_ALIADO)}")
        a.estado = nuevo

    for campo in ("nombre", "dni", "cuit_monotributo", "telefono", "cbu_alias", "zona", "notas"):
        if campo in data:
            setattr(a, campo, data[campo])
    if "contrato_firmado" in data:
        a.contrato_firmado = bool(data["contrato_firmado"])
    if "pin" in data:
        a.pin = (data["pin"] or "").strip() or None

    db.commit()
    db.refresh(a)
    return {"ok": True, **_aliado_dict(a)}


@router.get("/api/aliados/{codigo}/ventas")
async def ventas_del_aliado(
    codigo: str,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Historial de leads/ventas atribuidos al aliado."""
    _auth(x_api_key, current_user)
    cod = codigo.upper()
    if not db.query(Aliado).filter(Aliado.codigo == cod).first():
        raise HTTPException(404, "Aliado no encontrado")

    leads = db.query(Lead).filter(Lead.aliado_codigo == cod).order_by(Lead.created_at.desc()).all()
    items = []
    for l in leads:
        venta = None
        if l.telefono:
            v = db.query(VentaContado).filter(VentaContado.cliente_telefono == l.telefono).first()
            if v:
                venta = {"id": v.id, "precio_final": v.precio_final or 0, "estado": v.estado}
        items.append({
            "lead_id": l.id,
            "nombre": l.nombre,
            "telefono": l.telefono,
            "localidad": l.localidad or "",
            "estado": l.estado,
            "estado_verificacion": l.estado_verificacion or "pendiente",
            "timestamp_comprobante": l.timestamp_comprobante.isoformat() if l.timestamp_comprobante else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "venta": venta,
        })
    return {"aliado_codigo": cod, "total": len(items), "ventas": items}


@router.get("/api/aliados/{codigo}/comisiones")
async def comisiones_del_aliado(
    codigo: str,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Comisiones del aliado: pendientes / liquidadas."""
    _auth(x_api_key, current_user)
    cod = codigo.upper()
    if not db.query(Aliado).filter(Aliado.codigo == cod).first():
        raise HTTPException(404, "Aliado no encontrado")

    q = db.query(Comision).filter(Comision.aliado_codigo == cod)
    if estado:
        q = q.filter(Comision.estado == estado.lower())
    comisiones = q.order_by(Comision.id.desc()).all()

    return {
        "aliado_codigo": cod,
        "total": len(comisiones),
        "monto_pendiente": round(sum(c.monto or 0 for c in comisiones if c.estado == "pendiente"), 2),
        "monto_liquidado": round(sum(c.monto or 0 for c in comisiones if c.estado == "liquidada"), 2),
        "comisiones": [_comision_dict(c) for c in comisiones],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# COMISIONES
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/comisiones")
async def crear_comision(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Devenga una comisión. El monto se calcula fuera y se registra acá; si viene
    marcado como ajuste manual queda trazado con su motivo (excepción registrada).
    """
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    data = await request.json()

    cod = (data.get("aliado_codigo") or "").strip().upper()
    if not db.query(Aliado).filter(Aliado.codigo == cod).first():
        raise HTTPException(404, f"Aliado '{cod}' no encontrado")

    tipo = (data.get("tipo") or "entrada").lower()
    if tipo not in TIPOS_COMISION:
        raise HTTPException(400, f"Tipo inválido. Válidos: {', '.join(TIPOS_COMISION)}")

    ajuste = bool(data.get("ajuste_manual", False))
    motivo = (data.get("ajuste_motivo") or "").strip()
    if ajuste and not motivo:
        raise HTTPException(400, "Un ajuste manual requiere motivo (excepción registrada)")

    c = Comision(
        aliado_codigo=cod,
        solicitud_numero=(data.get("solicitud_numero") or "").strip(),
        tipo=tipo,
        monto=float(data.get("monto") or 0),
        estado="pendiente",
        ajuste_manual=ajuste,
        ajuste_motivo=motivo,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"ok": True, **_comision_dict(c)}


@router.post("/api/comisiones/{comision_id}/liquidar")
async def liquidar_comision(
    comision_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Marca la comisión como liquidada con fecha."""
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    c = db.query(Comision).filter(Comision.id == comision_id).first()
    if not c:
        raise HTTPException(404, "Comisión no encontrada")
    if c.estado == "liquidada":
        raise HTTPException(409, "La comisión ya está liquidada")
    c.estado = "liquidada"
    c.fecha_liquidacion = datetime.now()
    db.commit()
    db.refresh(c)

    socio = db.query(Aliado).filter(Aliado.codigo == c.aliado_codigo).first()
    if socio and socio.telefono:
        from utils.whatsapp import send_whatsapp_text
        send_whatsapp_text(db, socio.telefono, f"💸 Te transferimos tu comisión de ${c.monto:,.0f} (solicitud {c.solicitud_numero or '—'}). ¡Gracias por seguir sumando!".replace(",", "."))
    return {"ok": True, **_comision_dict(c)}


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS DEL CANAL — verificación y anti-duplicados
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/api/leads/check-dni/{dni}")
async def check_dni_duplicado(
    dni: str,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Chequea si un DNI ya fue cargado por otro aliado.
    Criterio de desempate ante disputas de atribución: el comprobante más antiguo.
    """
    _auth(x_api_key, current_user)
    dni = (dni or "").strip()
    if not dni:
        raise HTTPException(400, "DNI vacío")

    # Busca por el campo DNI dedicado; cae a notas por compatibilidad con datos viejos
    leads = (
        db.query(Lead)
        .filter(Lead.aliado_codigo.isnot(None))
        .filter((Lead.dni_cliente == dni) | (Lead.notas.ilike(f"%{dni}%")))
        .all()
    )
    if not leads:
        return {"dni": dni, "duplicado": False, "coincidencias": []}

    def _clave(l):
        return l.timestamp_comprobante or l.created_at or datetime.max

    ordenados = sorted(leads, key=_clave)
    ganador = ordenados[0]
    return {
        "dni": dni,
        "duplicado": len(ordenados) > 1,
        "aliado_con_prioridad": ganador.aliado_codigo,
        "criterio": "comprobante más antiguo",
        "coincidencias": [
            {
                "lead_id": l.id,
                "aliado_codigo": l.aliado_codigo,
                "nombre": l.nombre,
                "estado_verificacion": l.estado_verificacion or "pendiente",
                "timestamp_comprobante": l.timestamp_comprobante.isoformat() if l.timestamp_comprobante else None,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in ordenados
        ],
    }


@router.post("/api/leads/{lead_id}/marcar-verificacion")
async def marcar_verificacion(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Marca el estado de verificación del lead: pendiente / verificado / rechazado."""
    _auth(x_api_key, current_user)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead no encontrado")

    data = await request.json()
    estado = (data.get("estado") or data.get("estado_verificacion") or "").lower()
    if estado not in ESTADOS_VERIFICACION:
        raise HTTPException(400, f"Estado inválido. Válidos: {', '.join(ESTADOS_VERIFICACION)}")

    lead.estado_verificacion = estado
    if data.get("timestamp_comprobante"):
        try:
            lead.timestamp_comprobante = datetime.fromisoformat(
                str(data["timestamp_comprobante"]).replace("Z", "+00:00")
            )
        except Exception:
            pass

    quien = current_user.nombre if current_user else "Franco (bot)"
    ts = datetime.now().strftime("%d/%m %H:%M")
    nota = (data.get("motivo") or "").strip()
    lead.notas = (lead.notas or "") + f"\n[{ts}] 🔎 Verificación → {estado} por {quien}" + (f": {nota}" if nota else "")

    db.commit()
    return {
        "ok": True,
        "lead_id": lead.id,
        "estado_verificacion": lead.estado_verificacion,
        "aliado_codigo": lead.aliado_codigo,
    }


@router.get("/api/solicitudes/pendientes-verificacion")
async def solicitudes_pendientes_verificacion(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Cola de paquetes 🟡 activos: leads de canal esperando verificación."""
    _auth(x_api_key, current_user)
    leads = (
        db.query(Lead)
        .filter(Lead.aliado_codigo.isnot(None))
        .filter((Lead.estado_verificacion == "pendiente") | (Lead.estado_verificacion.is_(None)))
        .order_by(Lead.timestamp_comprobante.asc(), Lead.created_at.asc())
        .all()
    )
    items = []
    for l in leads:
        ultimo = (
            db.query(AuditoriaPaquete)
            .filter(AuditoriaPaquete.lead_id == l.id)
            .order_by(AuditoriaPaquete.id.desc())
            .first()
        )
        items.append({
            "lead_id": l.id,
            "aliado_codigo": l.aliado_codigo,
            "nombre": l.nombre,
            "telefono": l.telefono,
            "localidad": l.localidad or "",
            "timestamp_comprobante": l.timestamp_comprobante.isoformat() if l.timestamp_comprobante else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "ultimo_paquete": {
                "id": ultimo.id,
                "resultado": ultimo.resultado,
                "timestamp_envio": ultimo.timestamp_envio.isoformat() if ultimo.timestamp_envio else None,
            } if ultimo else None,
        })
    return {"total": len(items), "pendientes": items}


# ═══════════════════════════════════════════════════════════════════════════════
# AUDITORÍA DE PAQUETES 🟡
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/auditoria/paquete")
async def log_paquete(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Registra un paquete 🟡 enviado por Franco a Telegram.
    Se guarda siempre, aunque Franco no tenga permiso de escritura sobre contratos.
    """
    _auth(x_api_key, current_user)
    data = await request.json()

    resultado = (data.get("resultado") or "sin_respuesta")
    if resultado not in RESULTADOS_PAQUETE:
        raise HTTPException(400, f"Resultado inválido. Válidos: {', '.join(RESULTADOS_PAQUETE)}")

    contenido = data.get("contenido")
    if isinstance(contenido, (dict, list)):
        import json as _json
        contenido = _json.dumps(contenido, ensure_ascii=False)

    p = AuditoriaPaquete(
        aliado_codigo=(data.get("aliado_codigo") or "").strip().upper() or None,
        contenido=contenido or "",
        resultado=resultado,
        lead_id=data.get("lead_id"),
    )
    if data.get("timestamp_envio"):
        try:
            p.timestamp_envio = datetime.fromisoformat(str(data["timestamp_envio"]).replace("Z", "+00:00"))
        except Exception:
            pass
    if resultado != "sin_respuesta":
        p.timestamp_resultado = datetime.now()

    db.add(p)
    db.commit()
    db.refresh(p)
    return {"ok": True, "id": p.id, "resultado": p.resultado,
            "timestamp_envio": p.timestamp_envio.isoformat() if p.timestamp_envio else None}


@router.post("/api/auditoria/paquete/{paquete_id}/resultado")
async def actualizar_resultado_paquete(
    paquete_id: int,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Cierra el ciclo del paquete: OK / FALTA / RECHAZO."""
    _auth(x_api_key, current_user)
    p = db.query(AuditoriaPaquete).filter(AuditoriaPaquete.id == paquete_id).first()
    if not p:
        raise HTTPException(404, "Paquete no encontrado")
    data = await request.json()
    resultado = (data.get("resultado") or "")
    if resultado not in RESULTADOS_PAQUETE:
        raise HTTPException(400, f"Resultado inválido. Válidos: {', '.join(RESULTADOS_PAQUETE)}")
    p.resultado = resultado
    p.timestamp_resultado = datetime.now()
    db.commit()
    return {"ok": True, "id": p.id, "resultado": p.resultado,
            "timestamp_resultado": p.timestamp_resultado.isoformat()}


@router.get("/api/auditoria/paquetes")
async def listar_paquetes(
    aliado_codigo: Optional[str] = None,
    resultado: Optional[str] = None,
    limite: int = 100,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Historial de paquetes enviados (evidencia ante reclamos)."""
    _auth(x_api_key, current_user)
    q = db.query(AuditoriaPaquete)
    if aliado_codigo:
        q = q.filter(AuditoriaPaquete.aliado_codigo == aliado_codigo.upper())
    if resultado:
        q = q.filter(AuditoriaPaquete.resultado == resultado)
    paquetes = q.order_by(AuditoriaPaquete.id.desc()).limit(max(1, min(limite, 500))).all()
    return {
        "total": len(paquetes),
        "paquetes": [{
            "id": p.id,
            "aliado_codigo": p.aliado_codigo,
            "lead_id": p.lead_id,
            "contenido": p.contenido or "",
            "resultado": p.resultado,
            "timestamp_envio": p.timestamp_envio.isoformat() if p.timestamp_envio else None,
            "timestamp_resultado": p.timestamp_resultado.isoformat() if p.timestamp_resultado else None,
        } for p in paquetes],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NUMERACIÓN DE SOLICITUDES
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/solicitudes/numero")
async def emitir_numero_solicitud(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Emite el próximo número de solicitud al confirmar un pago.
    Única vía de asignación: correlativo, atómico y no editable a mano.
    """
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    numero = siguiente_numero_solicitud(db)

    # Si viene un aliado, se puede devengar la comisión en el mismo acto
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass

    comision = None
    cod = (data.get("aliado_codigo") or "").strip().upper()
    if cod and data.get("monto_comision") is not None:
        if db.query(Aliado).filter(Aliado.codigo == cod).first():
            c = Comision(
                aliado_codigo=cod,
                solicitud_numero=numero,
                tipo=(data.get("tipo_comision") or "entrada").lower(),
                monto=float(data.get("monto_comision") or 0),
                estado="pendiente",
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            comision = _comision_dict(c)

    return {"ok": True, "solicitud_numero": numero, "comision": comision}


@router.get("/api/solicitudes/numero-actual")
async def numero_actual(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """Estado del contador (sin consumir número)."""
    _auth(x_api_key, current_user)
    c = db.query(SolicitudContador).filter(SolicitudContador.id == 1).first()
    if not c:
        return {"sembrado": False, "ultimo_emitido": None, "proximo": "000-13860153"}
    return {
        "sembrado": True,
        "ultimo_emitido": f"{c.prefijo}-{c.ultimo_numero}",
        "proximo": f"{c.prefijo}-{(c.ultimo_numero or 0) + 1}",
    }


@router.post("/api/solicitudes/set-contador")
async def set_contador(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Ajusta la base del contador de solicitudes (operación de gestión).
    Uso: corregir continuidad o reajustar tras importar contratos históricos.
    Body: { ultimo_numero: int, prefijo?: str }
    El próximo número emitido será ultimo_numero + 1.
    """
    _auth(x_api_key, current_user)
    _solo_gestion(current_user, x_api_key)
    data = await request.json()

    if "ultimo_numero" not in data:
        raise HTTPException(400, "Falta 'ultimo_numero'")
    try:
        nuevo = int(data["ultimo_numero"])
    except Exception:
        raise HTTPException(400, "'ultimo_numero' debe ser un entero")

    c = db.query(SolicitudContador).filter(SolicitudContador.id == 1).first()
    if not c:
        c = SolicitudContador(id=1, prefijo=data.get("prefijo", "000"), ultimo_numero=nuevo)
        db.add(c)
    else:
        anterior = c.ultimo_numero
        c.ultimo_numero = nuevo
        if data.get("prefijo"):
            c.prefijo = data["prefijo"]
    db.commit()
    db.refresh(c)
    return {
        "ok": True,
        "ultimo_numero": c.ultimo_numero,
        "prefijo": c.prefijo,
        "proximo": f"{c.prefijo}-{c.ultimo_numero + 1}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PÚBLICO — postulación de aliados desde la landing (sin auth)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/public/aliado-postulacion")
async def postulacion_aliado(request: Request, db: Session = Depends(get_db)):
    """
    PÚBLICO (sin auth): capta un postulante desde la landing.
    Crea un Aliado en estado 'postulante' para que gestión lo evalúe/apruebe.
    Idempotente por teléfono/DNI: no duplica si ya se postuló.
    """
    data = await request.json()
    nombre = (data.get("nombre") or "").strip()
    telefono = (data.get("telefono") or "").strip()
    if not nombre or not telefono:
        raise HTTPException(400, "Nombre y teléfono son obligatorios")

    dni = (data.get("dni") or "").strip()
    existente = db.query(Aliado).filter(Aliado.telefono == telefono, Aliado.telefono != "").first()
    if not existente and dni:
        existente = db.query(Aliado).filter(Aliado.dni == dni, Aliado.dni != "").first()
    if existente:
        return {"ok": True, "codigo": existente.codigo, "estado": existente.estado, "duplicado": True}

    aliado = Aliado(
        codigo=_generar_codigo_aliado(db),
        nombre=nombre,
        telefono=telefono,
        dni=dni,
        cuit_monotributo=(data.get("cuit_monotributo") or "").strip(),
        zona=(data.get("zona") or "").strip(),
        cbu_alias=(data.get("cbu_alias") or "").strip(),
        estado="postulante",
        notas=((data.get("notas") or "").strip() + " · postulación landing").strip(" ·"),
    )
    db.add(aliado)
    db.commit()
    db.refresh(aliado)
    return {"ok": True, "codigo": aliado.codigo, "estado": "postulante"}


# ═══════════════════════════════════════════════════════════════════════════════
# PORTAL DEL ALIADO — solo lectura, login por código + PIN (público)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/portal-aliado", response_class=HTMLResponse)
async def portal_aliado_page(request: Request):
    """Página pública de login del portal del aliado."""
    return templates.TemplateResponse("portal_aliado.html", {"request": request})


@router.post("/api/public/aliado-portal")
async def aliado_portal_data(request: Request, db: Session = Depends(get_db)):
    """
    PÚBLICO: valida código + PIN del aliado y devuelve, en solo lectura,
    sus leads cargados (con estado) y el resumen de comisiones.
    """
    data = await request.json()
    cod = (data.get("codigo") or "").strip().upper()
    pin = (data.get("pin") or "").strip()
    if not cod or not pin:
        raise HTTPException(400, "Ingresá código y PIN")

    a = db.query(Aliado).filter(Aliado.codigo == cod).first()
    if not a or not a.pin or a.pin != pin:
        raise HTTPException(401, "Código o PIN incorrecto")

    leads = db.query(Lead).filter(Lead.aliado_codigo == cod).order_by(Lead.created_at.desc()).all()
    comisiones = db.query(Comision).filter(Comision.aliado_codigo == cod).order_by(Comision.id.desc()).all()

    return {
        "ok": True,
        "aliado": {
            "codigo": a.codigo,
            "nombre": a.nombre,
            "estado": a.estado,
            "operativo": (a.estado == "activo" and bool(a.contrato_firmado)),
        },
        "leads": [{
            "nombre": l.nombre,
            "localidad": l.localidad or "",
            "estado": l.estado,
            "estado_verificacion": l.estado_verificacion or "pendiente",
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in leads],
        "comisiones": {
            "pendiente": round(sum(c.monto or 0 for c in comisiones if c.estado == "pendiente"), 2),
            "liquidado": round(sum(c.monto or 0 for c in comisiones if c.estado == "liquidada"), 2),
            "items": [{
                "solicitud_numero": c.solicitud_numero or "",
                "tipo": c.tipo,
                "monto": c.monto or 0,
                "estado": c.estado,
            } for c in comisiones],
        },
    }
