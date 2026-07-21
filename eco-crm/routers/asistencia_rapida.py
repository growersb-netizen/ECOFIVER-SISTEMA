"""
Panel de Asistencia Rápida — registro ágil de asistencia del personal.
Diseñado para uso móvil: tap por empleado, "todos presentes" en un clic.
Acceso: ADMIN | COORDINADOR_OPERATIVO | FABRICA | ADMINISTRACION
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Empleado, Asistencia, Usuario
from routers.auth import require_auth, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_ASISTENCIA = ["ADMIN", "COORDINADOR_OPERATIVO", "FABRICA", "ADMINISTRACION"]


def _check(current_user: Usuario):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_ASISTENCIA):
        raise HTTPException(403, "Sin permisos para registrar asistencia")
    return roles


def _asistencias_del_dia(db: Session, fecha_dia: datetime) -> dict:
    """Devuelve {empleado_id: Asistencia} para un día dado."""
    siguiente = fecha_dia + timedelta(days=1)
    asistencias = db.query(Asistencia).filter(
        Asistencia.fecha >= fecha_dia,
        Asistencia.fecha < siguiente,
    ).all()
    return {a.empleado_id: a for a in asistencias}


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/asistencia-rapida", response_class=HTMLResponse)
async def asistencia_rapida_page(
    request: Request,
    fecha: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = _check(current_user)

    # Resolver fecha
    if fecha:
        try:
            dia = datetime.fromisoformat(fecha).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    asistencias_hoy = _asistencias_del_dia(db, dia)

    empleados_data = []
    for e in empleados:
        a = asistencias_hoy.get(e.id)
        empleados_data.append({
            "id": e.id,
            "nombre": e.nombre,
            "rol": e.rol_empresa or "",
            "tipo_tarifa": e.tipo_tarifa or "POR_DIA",
            "asistencia_id": a.id if a else None,
            "tipo_hoy": a.tipo if a else None,
            "horas_hoy": a.horas if a else None,
        })

    DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    fecha_display = f"{DIAS_ES[dia.weekday()]} {dia.day} de {MESES_ES[dia.month-1]} de {dia.year}"

    return templates.TemplateResponse("asistencia_rapida.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "empleados": empleados_data,
        "fecha_display": fecha_display,
        "fecha_iso": dia.date().isoformat(),
        "es_hoy": dia.date() == datetime.now().date(),
    })


# ─── API ──────────────────────────────────────────────────────────────────────

@router.get("/api/asistencia-rapida/hoy")
async def get_asistencia_hoy(
    fecha: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)

    if fecha:
        try:
            dia = datetime.fromisoformat(fecha).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()
    asistencias = _asistencias_del_dia(db, dia)

    result = []
    for e in empleados:
        a = asistencias.get(e.id)
        result.append({
            "id": e.id,
            "nombre": e.nombre,
            "rol": e.rol_empresa or "",
            "asistencia_id": a.id if a else None,
            "tipo_hoy": a.tipo if a else None,
            "horas_hoy": a.horas if a else None,
        })

    presentes   = sum(1 for x in result if x["tipo_hoy"] == "PRESENTE")
    ausentes    = sum(1 for x in result if x["tipo_hoy"] == "AUSENTE")
    medio_dia   = sum(1 for x in result if x["tipo_hoy"] == "MEDIO_DIA")
    otros       = sum(1 for x in result if x["tipo_hoy"] not in (None, "PRESENTE", "AUSENTE", "MEDIO_DIA"))
    sin_marcar  = sum(1 for x in result if x["tipo_hoy"] is None)

    return {
        "fecha": dia.date().isoformat(),
        "empleados": result,
        "total": len(result),
        "presentes": presentes,
        "ausentes": ausentes,
        "medio_dia": medio_dia,
        "otros": otros,
        "sin_marcar": sin_marcar,
    }


@router.post("/api/asistencia-rapida/marcar")
async def marcar_asistencia(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Marca o actualiza la asistencia de un empleado para una fecha."""
    _check(current_user)
    data = await request.json()

    empleado_id = data.get("empleado_id")
    tipo = data.get("tipo", "PRESENTE").upper()
    horas = data.get("horas")
    fecha_str = data.get("fecha")

    if not empleado_id:
        raise HTTPException(400, "empleado_id requerido")

    if fecha_str:
        try:
            dia = datetime.fromisoformat(fecha_str).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    fecha_registro = dia.replace(hour=8, minute=0, second=0)
    siguiente = dia + timedelta(days=1)

    existente = db.query(Asistencia).filter(
        Asistencia.empleado_id == empleado_id,
        Asistencia.fecha >= dia,
        Asistencia.fecha < siguiente,
    ).first()

    if existente:
        existente.tipo = tipo
        if horas is not None:
            existente.horas = float(horas)
        db.commit()
        return {"ok": True, "accion": "actualizado", "asistencia_id": existente.id, "tipo": tipo}
    else:
        nueva = Asistencia(
            empleado_id=empleado_id,
            fecha=fecha_registro,
            tipo=tipo,
            horas=float(horas) if horas is not None else None,
        )
        db.add(nueva)
        db.commit()
        db.refresh(nueva)
        return {"ok": True, "accion": "creado", "asistencia_id": nueva.id, "tipo": tipo}


@router.post("/api/asistencia-rapida/marcar-todos")
async def marcar_todos_presentes(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Marca como PRESENTE a todos los empleados sin asistencia registrada en la fecha."""
    _check(current_user)
    data = await request.json()
    fecha_str = data.get("fecha")
    tipo = data.get("tipo", "PRESENTE").upper()

    if fecha_str:
        try:
            dia = datetime.fromisoformat(fecha_str).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    fecha_registro = dia.replace(hour=8, minute=0, second=0)
    siguiente = dia + timedelta(days=1)

    empleados = db.query(Empleado).filter(Empleado.activo == True).all()
    ya_marcados = {
        a.empleado_id
        for a in db.query(Asistencia).filter(
            Asistencia.fecha >= dia,
            Asistencia.fecha < siguiente,
        ).all()
    }

    nuevos = 0
    for e in empleados:
        if e.id not in ya_marcados:
            db.add(Asistencia(
                empleado_id=e.id,
                fecha=fecha_registro,
                tipo=tipo,
            ))
            nuevos += 1

    db.commit()
    return {"ok": True, "marcados": nuevos, "ya_tenian": len(ya_marcados), "total": len(empleados)}


@router.get("/api/asistencia-rapida/semana")
async def get_resumen_semana(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Resumen de asistencia de los últimos 7 días."""
    _check(current_user)
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    hace7 = hoy - timedelta(days=6)

    asistencias = db.query(Asistencia).filter(
        Asistencia.fecha >= hace7,
        Asistencia.fecha < hoy + timedelta(days=1),
    ).all()

    por_dia = {}
    for a in asistencias:
        dia_key = a.fecha.date().isoformat()
        if dia_key not in por_dia:
            por_dia[dia_key] = {"presentes": 0, "ausentes": 0, "otros": 0, "total": 0}
        por_dia[dia_key]["total"] += 1
        if a.tipo == "PRESENTE":
            por_dia[dia_key]["presentes"] += 1
        elif a.tipo == "AUSENTE":
            por_dia[dia_key]["ausentes"] += 1
        else:
            por_dia[dia_key]["otros"] += 1

    return {"dias": por_dia}
