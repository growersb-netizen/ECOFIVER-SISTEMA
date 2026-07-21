"""
Módulo de Flota Propia (F1-F7)
  F1: Registro de vehículos
  F2: Asignación diaria
  F3: Registro de km
  F4: Mantenimiento y reparaciones
  F5: Gastos de flota
  F6: Incidentes y daños
  F7: Dashboard
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Vehiculo, AsignacionVehiculo, MantenimientoVehiculo,
    GastoFlota, IncidenteVehiculo, Empleado, Usuario,
)
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_FLOTA = ["ADMIN", "COORDINADOR_OPERATIVO", "FABRICA", "ADMINISTRACION"]


def _check_flota(current_user: Usuario, db: Session):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FLOTA):
        raise HTTPException(403, "Sin permisos")
    return roles


# ─── PÁGINA HTML ──────────────────────────────────────────────────────────────

@router.get("/flota", response_class=HTMLResponse)
async def flota_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_FLOTA):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/", 302)
    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    return templates.TemplateResponse("flota.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": [{"id": e.id, "nombre": e.nombre} for e in empleados],
    })


# ─── F1: VEHÍCULOS ────────────────────────────────────────────────────────────

@router.get("/api/flota/vehiculos")
async def list_vehiculos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    vehiculos = db.query(Vehiculo).filter(Vehiculo.activo == True).order_by(Vehiculo.patente).all()
    ahora = datetime.now()
    result = []
    for v in vehiculos:
        asig_hoy = db.query(AsignacionVehiculo).filter(
            AsignacionVehiculo.vehiculo_id == v.id,
            AsignacionVehiculo.fecha >= ahora.replace(hour=0, minute=0, second=0),
            AsignacionVehiculo.fecha <= ahora.replace(hour=23, minute=59, second=59),
            AsignacionVehiculo.estado.in_(["PROGRAMADA", "EN_VIAJE"]),
        ).first()
        result.append(_vehiculo_to_dict(v, asig_hoy))
    return result


@router.post("/api/flota/vehiculos")
async def create_vehiculo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    data = await request.json()
    v = Vehiculo(
        patente=data.get("patente", "").upper(),
        tipo=data.get("tipo", "CAMIONETA"),
        marca=data.get("marca", ""),
        modelo=data.get("modelo", ""),
        anio=data.get("anio"),
        color=data.get("color", ""),
        estado=data.get("estado", "OPERATIVO"),
        observaciones=data.get("observaciones", ""),
    )
    if data.get("vencimiento_vtv"):
        try:
            v.vencimiento_vtv = datetime.fromisoformat(data["vencimiento_vtv"])
        except Exception:
            pass
    if data.get("vencimiento_seguro"):
        try:
            v.vencimiento_seguro = datetime.fromisoformat(data["vencimiento_seguro"])
        except Exception:
            pass
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"id": v.id, "ok": True}


@router.put("/api/flota/vehiculos/{v_id}")
async def update_vehiculo(
    v_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    v = db.query(Vehiculo).filter(Vehiculo.id == v_id).first()
    if not v:
        raise HTTPException(404, "Vehículo no encontrado")
    data = await request.json()
    for field in ["patente", "tipo", "marca", "modelo", "anio", "color", "estado", "observaciones", "activo"]:
        if field in data:
            setattr(v, field, data[field])
    for dt_field in ["vencimiento_vtv", "vencimiento_seguro"]:
        if dt_field in data and data[dt_field]:
            try:
                setattr(v, dt_field, datetime.fromisoformat(data[dt_field]))
            except Exception:
                pass
    db.commit()
    return {"ok": True}


# ─── F2: ASIGNACIONES ─────────────────────────────────────────────────────────

@router.get("/api/flota/asignaciones/hoy")
async def asignaciones_hoy(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    ahora = datetime.now()
    inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = ahora.replace(hour=23, minute=59, second=59)
    asigs = db.query(AsignacionVehiculo).filter(
        AsignacionVehiculo.fecha >= inicio,
        AsignacionVehiculo.fecha <= fin,
    ).order_by(AsignacionVehiculo.horario_salida_estimado.asc()).all()
    return [_asignacion_to_dict(a) for a in asigs]


@router.get("/api/flota/asignaciones")
async def list_asignaciones(
    fecha: Optional[str] = None,
    vehiculo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    q = db.query(AsignacionVehiculo)
    if fecha:
        try:
            dt = datetime.fromisoformat(fecha)
            q = q.filter(
                AsignacionVehiculo.fecha >= dt.replace(hour=0, minute=0, second=0),
                AsignacionVehiculo.fecha <= dt.replace(hour=23, minute=59, second=59),
            )
        except Exception:
            pass
    if vehiculo_id:
        q = q.filter(AsignacionVehiculo.vehiculo_id == vehiculo_id)
    asigs = q.order_by(AsignacionVehiculo.fecha.desc()).limit(100).all()
    return [_asignacion_to_dict(a) for a in asigs]


@router.post("/api/flota/asignaciones")
async def create_asignacion(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    data = await request.json()
    fecha = datetime.now()
    if data.get("fecha"):
        try:
            fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            pass
    a = AsignacionVehiculo(
        vehiculo_id=data.get("vehiculo_id"),
        conductor_nombre=data.get("conductor_nombre", ""),
        empleado_id=data.get("empleado_id"),
        destino=data.get("destino", ""),
        trabajo=data.get("trabajo", ""),
        fecha=fecha,
        horario_salida_estimado=data.get("horario_salida_estimado", ""),
        horario_regreso_estimado=data.get("horario_regreso_estimado", ""),
        km_salida=data.get("km_salida"),
        estado="PROGRAMADA",
        notas=data.get("notas", ""),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "ok": True}


@router.put("/api/flota/asignaciones/{a_id}")
async def update_asignacion(
    a_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    a = db.query(AsignacionVehiculo).filter(AsignacionVehiculo.id == a_id).first()
    if not a:
        raise HTTPException(404, "Asignación no encontrada")
    data = await request.json()
    for field in ["conductor_nombre", "destino", "trabajo", "estado", "notas",
                  "horario_salida_estimado", "horario_regreso_estimado", "km_salida", "km_regreso"]:
        if field in data:
            setattr(a, field, data[field])
    db.commit()
    return {"ok": True}


# ─── F4: MANTENIMIENTO ────────────────────────────────────────────────────────

@router.get("/api/flota/mantenimientos")
async def list_mantenimientos(
    vehiculo_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    q = db.query(MantenimientoVehiculo)
    if vehiculo_id:
        q = q.filter(MantenimientoVehiculo.vehiculo_id == vehiculo_id)
    if estado:
        q = q.filter(MantenimientoVehiculo.estado == estado)
    mantenimientos = q.order_by(MantenimientoVehiculo.created_at.desc()).all()
    return [_mantenimiento_to_dict(m) for m in mantenimientos]


@router.post("/api/flota/mantenimientos")
async def create_mantenimiento(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    data = await request.json()
    m = MantenimientoVehiculo(
        vehiculo_id=data.get("vehiculo_id"),
        tipo=data.get("tipo", "PREVENTIVO"),
        descripcion=data.get("descripcion", ""),
        km_al_momento=data.get("km_al_momento"),
        costo=data.get("costo"),
        taller=data.get("taller", ""),
        estado=data.get("estado", "PENDIENTE"),
        notas=data.get("notas", ""),
    )
    if data.get("fecha"):
        try:
            m.fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            pass
    if data.get("proximo_service_fecha"):
        try:
            m.proximo_service_fecha = datetime.fromisoformat(data["proximo_service_fecha"])
        except Exception:
            pass
    if data.get("proximo_service_km"):
        m.proximo_service_km = float(data["proximo_service_km"])
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "ok": True}


@router.put("/api/flota/mantenimientos/{m_id}")
async def update_mantenimiento(
    m_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    m = db.query(MantenimientoVehiculo).filter(MantenimientoVehiculo.id == m_id).first()
    if not m:
        raise HTTPException(404, "Mantenimiento no encontrado")
    data = await request.json()
    for field in ["tipo", "descripcion", "km_al_momento", "costo", "taller", "estado", "notas"]:
        if field in data:
            setattr(m, field, data[field])
    db.commit()
    return {"ok": True}


# ─── F5: GASTOS ───────────────────────────────────────────────────────────────

@router.get("/api/flota/gastos")
async def list_gastos(
    vehiculo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    q = db.query(GastoFlota)
    if vehiculo_id:
        q = q.filter(GastoFlota.vehiculo_id == vehiculo_id)
    gastos = q.order_by(GastoFlota.fecha.desc()).limit(200).all()
    return [{
        "id": g.id,
        "vehiculo_id": g.vehiculo_id,
        "vehiculo_patente": g.vehiculo.patente if g.vehiculo else "",
        "tipo": g.tipo,
        "monto": g.monto,
        "fecha": g.fecha.isoformat() if g.fecha else "",
        "descripcion": g.descripcion,
        "quien_pago": g.quien_pago,
    } for g in gastos]


@router.post("/api/flota/gastos")
async def create_gasto(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    data = await request.json()
    g = GastoFlota(
        vehiculo_id=data.get("vehiculo_id"),
        tipo=data.get("tipo", "NAFTA"),
        monto=data.get("monto", 0),
        descripcion=data.get("descripcion", ""),
        quien_pago=data.get("quien_pago", ""),
        registrado_por_id=current_user.id,
    )
    if data.get("fecha"):
        try:
            g.fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            pass
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id, "ok": True}


# ─── F6: INCIDENTES ───────────────────────────────────────────────────────────

@router.get("/api/flota/incidentes")
async def list_incidentes(
    vehiculo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    q = db.query(IncidenteVehiculo)
    if vehiculo_id:
        q = q.filter(IncidenteVehiculo.vehiculo_id == vehiculo_id)
    incidentes = q.order_by(IncidenteVehiculo.created_at.desc()).all()
    return [{
        "id": i.id,
        "vehiculo_id": i.vehiculo_id,
        "vehiculo_patente": i.vehiculo.patente if i.vehiculo else "",
        "fecha": i.fecha.isoformat() if i.fecha else "",
        "lugar": i.lugar,
        "descripcion": i.descripcion,
        "conductor_nombre": i.conductor_nombre,
        "seguro_involucrado": i.seguro_involucrado,
        "numero_siniestro": i.numero_siniestro,
        "estado_reclamo": i.estado_reclamo,
    } for i in incidentes]


@router.post("/api/flota/incidentes")
async def create_incidente(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    data = await request.json()
    i = IncidenteVehiculo(
        vehiculo_id=data.get("vehiculo_id"),
        lugar=data.get("lugar", ""),
        descripcion=data.get("descripcion", ""),
        conductor_nombre=data.get("conductor_nombre", ""),
        seguro_involucrado=data.get("seguro_involucrado", False),
        numero_siniestro=data.get("numero_siniestro", ""),
        estado_reclamo=data.get("estado_reclamo", ""),
    )
    if data.get("fecha"):
        try:
            i.fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            i.fecha = datetime.now()
    else:
        i.fecha = datetime.now()
    db.add(i)
    db.commit()
    db.refresh(i)
    return {"id": i.id, "ok": True}


# ─── F7: DASHBOARD ────────────────────────────────────────────────────────────

@router.get("/api/flota/dashboard")
async def dashboard_flota(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check_flota(current_user, db)
    ahora = datetime.now()
    vehiculos = db.query(Vehiculo).filter(Vehiculo.activo == True).all()
    inicio_semana = ahora - timedelta(days=ahora.weekday())
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0)

    # Gastos del mes
    gasto_mes = sum(
        g.monto for g in db.query(GastoFlota).filter(GastoFlota.fecha >= inicio_mes).all()
        if g.monto
    )

    # Vencimientos próximos (30 días)
    limite = ahora + timedelta(days=30)
    vencimientos = []
    for v in vehiculos:
        if v.vencimiento_vtv and ahora <= v.vencimiento_vtv <= limite:
            vencimientos.append({"vehiculo": v.patente, "tipo": "VTV", "fecha": v.vencimiento_vtv.isoformat()})
        if v.vencimiento_seguro and ahora <= v.vencimiento_seguro <= limite:
            vencimientos.append({"vehiculo": v.patente, "tipo": "SEGURO", "fecha": v.vencimiento_seguro.isoformat()})

    # Mantenimientos pendientes
    mant_pendientes = db.query(MantenimientoVehiculo).filter(
        MantenimientoVehiculo.estado.in_(["PENDIENTE", "EN_TALLER"])
    ).count()

    # Km semana (por asignaciones completadas)
    asigs_semana = db.query(AsignacionVehiculo).filter(
        AsignacionVehiculo.fecha >= inicio_semana,
        AsignacionVehiculo.estado == "COMPLETADA",
        AsignacionVehiculo.km_salida.isnot(None),
        AsignacionVehiculo.km_regreso.isnot(None),
    ).all()
    km_semana = sum((a.km_regreso - a.km_salida) for a in asigs_semana if a.km_regreso and a.km_salida)

    return {
        "vehiculos": [_vehiculo_to_dict(v) for v in vehiculos],
        "total_vehiculos": len(vehiculos),
        "operativos": len([v for v in vehiculos if v.estado == "OPERATIVO"]),
        "en_reparacion": len([v for v in vehiculos if v.estado == "EN_REPARACION"]),
        "vencimientos_proximos": vencimientos,
        "mantenimientos_pendientes": mant_pendientes,
        "km_semana": km_semana,
        "gasto_mes": gasto_mes,
    }


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _vehiculo_to_dict(v: Vehiculo, asig_hoy=None) -> dict:
    ahora = datetime.now()
    alertas = []
    if v.vencimiento_vtv and (v.vencimiento_vtv - ahora).days <= 30:
        alertas.append(f"VTV vence {v.vencimiento_vtv.strftime('%d/%m/%Y')}")
    if v.vencimiento_seguro and (v.vencimiento_seguro - ahora).days <= 30:
        alertas.append(f"Seguro vence {v.vencimiento_seguro.strftime('%d/%m/%Y')}")
    return {
        "id": v.id,
        "patente": v.patente,
        "tipo": v.tipo,
        "marca": v.marca,
        "modelo": v.modelo,
        "anio": v.anio,
        "color": v.color,
        "estado": v.estado,
        "vencimiento_vtv": v.vencimiento_vtv.isoformat() if v.vencimiento_vtv else None,
        "vencimiento_seguro": v.vencimiento_seguro.isoformat() if v.vencimiento_seguro else None,
        "observaciones": v.observaciones,
        "alertas": alertas,
        "asignado_hoy": asig_hoy is not None,
        "conductor_hoy": asig_hoy.conductor_nombre if asig_hoy else None,
        "destino_hoy": asig_hoy.destino if asig_hoy else None,
    }


def _asignacion_to_dict(a: AsignacionVehiculo) -> dict:
    return {
        "id": a.id,
        "vehiculo_id": a.vehiculo_id,
        "vehiculo_patente": a.vehiculo.patente if a.vehiculo else "",
        "vehiculo_tipo": a.vehiculo.tipo if a.vehiculo else "",
        "conductor_nombre": a.conductor_nombre,
        "destino": a.destino,
        "trabajo": a.trabajo,
        "fecha": a.fecha.isoformat() if a.fecha else "",
        "horario_salida_estimado": a.horario_salida_estimado,
        "horario_regreso_estimado": a.horario_regreso_estimado,
        "km_salida": a.km_salida,
        "km_regreso": a.km_regreso,
        "km_recorridos": (a.km_regreso - a.km_salida) if a.km_regreso and a.km_salida else None,
        "estado": a.estado,
        "notas": a.notas,
    }


def _mantenimiento_to_dict(m: MantenimientoVehiculo) -> dict:
    return {
        "id": m.id,
        "vehiculo_id": m.vehiculo_id,
        "vehiculo_patente": m.vehiculo.patente if m.vehiculo else "",
        "tipo": m.tipo,
        "descripcion": m.descripcion,
        "fecha": m.fecha.isoformat() if m.fecha else None,
        "km_al_momento": m.km_al_momento,
        "costo": m.costo,
        "taller": m.taller,
        "proximo_service_fecha": m.proximo_service_fecha.isoformat() if m.proximo_service_fecha else None,
        "proximo_service_km": m.proximo_service_km,
        "estado": m.estado,
        "notas": m.notas,
    }
