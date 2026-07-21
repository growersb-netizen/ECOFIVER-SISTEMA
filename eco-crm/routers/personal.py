from datetime import datetime, timedelta, date
from typing import Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.database import get_db
from database.models import Empleado, Asistencia, LiquidacionSemanal, Usuario, AdelantoSueldo
from routers.auth import require_auth, require_roles, get_user_roles

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/personal", response_class=HTMLResponse)
async def personal_page(
    request: Request,
    tab: Optional[str] = None,
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("personal.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "initial_tab": tab or "asistencia",
    })


# ─── EMPLEADOS ────────────────────────────────────────────────────────────────

@router.get("/api/personal/empleados")
async def list_empleados(
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(Empleado)
    if activo is not None:
        q = q.filter(Empleado.activo == activo)
    empleados = q.order_by(Empleado.nombre).all()
    return [{
        "id": e.id,
        "nombre": e.nombre,
        "rol_empresa": e.rol_empresa or "",
        "tipo_tarifa": e.tipo_tarifa,
        "monto_tarifa": e.monto_tarifa or 0,
        "sabado_recargo": e.sabado_recargo,
        "multiplicador_sabado": e.multiplicador_sabado or 1.5,
        "fecha_ingreso": e.fecha_ingreso.isoformat() if e.fecha_ingreso else "",
        "activo": e.activo,
    } for e in empleados]


@router.post("/api/personal/empleados")
async def create_empleado(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")
    data = await request.json()

    fecha_ingreso = None
    if data.get("fecha_ingreso"):
        try:
            fecha_ingreso = datetime.fromisoformat(data["fecha_ingreso"])
        except Exception:
            fecha_ingreso = datetime.now()

    emp = Empleado(
        nombre=data.get("nombre", ""),
        rol_empresa=data.get("rol_empresa", ""),
        tipo_tarifa=data.get("tipo_tarifa", "POR_DIA"),
        monto_tarifa=data.get("monto_tarifa", 0),
        sabado_recargo=data.get("sabado_recargo", False),
        multiplicador_sabado=data.get("multiplicador_sabado", 1.5),
        fecha_ingreso=fecha_ingreso or datetime.now(),
        activo=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return {"id": emp.id, "ok": True}


@router.put("/api/personal/empleados/{emp_id}")
async def update_empleado(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")
    emp = db.query(Empleado).filter(Empleado.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    data = await request.json()
    for field in ["nombre", "rol_empresa", "tipo_tarifa", "monto_tarifa",
                  "sabado_recargo", "multiplicador_sabado", "activo"]:
        if field in data:
            setattr(emp, field, data[field])
    db.commit()
    return {"ok": True}


# ─── ASISTENCIA ───────────────────────────────────────────────────────────────

@router.get("/api/personal/asistencia")
async def get_asistencia_dia(
    fecha: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    if fecha:
        try:
            dia = datetime.fromisoformat(fecha).date()
        except Exception:
            dia = datetime.now().date()
    else:
        dia = datetime.now().date()

    inicio = datetime.combine(dia, datetime.min.time())
    fin = datetime.combine(dia, datetime.max.time())

    empleados = db.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.nombre).all()

    result = []
    for emp in empleados:
        asistencia = db.query(Asistencia).filter(
            Asistencia.empleado_id == emp.id,
            Asistencia.fecha >= inicio,
            Asistencia.fecha <= fin
        ).first()

        result.append({
            "empleado_id": emp.id,
            "empleado_nombre": emp.nombre,
            "empleado_rol": emp.rol_empresa or "",
            "tipo_tarifa": emp.tipo_tarifa,
            "monto_tarifa": emp.monto_tarifa or 0,
            "asistencia_id": asistencia.id if asistencia else None,
            "tipo": asistencia.tipo if asistencia else None,
            "horas": asistencia.horas if asistencia else None,
            "registrado_en": asistencia.registrado_en.isoformat() if asistencia and asistencia.registrado_en else None,
        })

    return result


@router.post("/api/personal/asistencia")
async def registrar_asistencia(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    data = await request.json()
    emp_id = data.get("empleado_id")
    tipo = data.get("tipo", "PRESENTE")
    horas = data.get("horas")

    # Validación de campos requeridos
    if not emp_id:
        raise HTTPException(400, "empleado_id es requerido")
    TIPOS_VALIDOS = ["PRESENTE", "AUSENTE", "MEDIO_DIA", "FERIADO", "ENFERMO"]
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(400, f"tipo inválido. Válidos: {TIPOS_VALIDOS}")
    emp = db.query(Empleado).filter(Empleado.id == emp_id).first()
    if not emp:
        raise HTTPException(404, f"Empleado {emp_id} no encontrado")

    if data.get("fecha"):
        try:
            fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            fecha = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        fecha = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    inicio = fecha.replace(hour=0, minute=0, second=0)
    fin = fecha.replace(hour=23, minute=59, second=59)

    # Se permite editar asistencia de cualquier fecha (incluye retroactivo)

    existing = db.query(Asistencia).filter(
        Asistencia.empleado_id == emp_id,
        Asistencia.fecha >= inicio,
        Asistencia.fecha <= fin
    ).first()

    if existing:
        existing.tipo = tipo
        existing.horas = horas
        existing.registrado_en = datetime.now()
    else:
        asistencia = Asistencia(
            empleado_id=emp_id,
            fecha=fecha,
            tipo=tipo,
            horas=horas,
        )
        db.add(asistencia)

    db.commit()
    return {"ok": True}


# ─── LIQUIDACIÓN ──────────────────────────────────────────────────────────────

@router.get("/api/personal/liquidacion")
async def calcular_liquidacion(
    fecha_inicio: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    if fecha_inicio:
        try:
            inicio_semana = datetime.fromisoformat(fecha_inicio)
        except Exception:
            inicio_semana = _get_inicio_semana()
    else:
        inicio_semana = _get_inicio_semana()

    fin_semana = inicio_semana + timedelta(days=6)

    empleados = db.query(Empleado).filter(Empleado.activo == True).all()
    result = []

    for emp in empleados:
        asistencias = db.query(Asistencia).filter(
            Asistencia.empleado_id == emp.id,
            Asistencia.fecha >= inicio_semana,
            Asistencia.fecha <= fin_semana
        ).all()

        dias_trabajados = 0
        horas_trabajadas = 0
        monto = 0
        detalle = []

        for a in asistencias:
            dia_semana = a.fecha.weekday()  # 5 = sábado
            es_sabado = dia_semana == 5

            if a.tipo == "PRESENTE":
                if emp.tipo_tarifa == "POR_DIA":
                    dias = 1
                    tarifa = emp.monto_tarifa or 0
                    if es_sabado and emp.sabado_recargo:
                        tarifa = tarifa * (emp.multiplicador_sabado or 1.5)
                    monto += tarifa
                    dias_trabajados += 1
                elif emp.tipo_tarifa == "POR_HORA":
                    hs = a.horas or 8
                    tarifa = (emp.monto_tarifa or 0) * hs
                    if es_sabado and emp.sabado_recargo:
                        tarifa = tarifa * (emp.multiplicador_sabado or 1.5)
                    monto += tarifa
                    horas_trabajadas += hs
                    dias_trabajados += 1
            elif a.tipo == "MEDIO_DIA":
                if emp.tipo_tarifa == "POR_DIA":
                    tarifa = (emp.monto_tarifa or 0) * 0.5
                    monto += tarifa
                    dias_trabajados += 0.5
                elif emp.tipo_tarifa == "POR_HORA":
                    hs = (a.horas or 4)
                    tarifa = (emp.monto_tarifa or 0) * hs
                    monto += tarifa
                    horas_trabajadas += hs
                    dias_trabajados += 0.5

            detalle.append({
                "fecha": a.fecha.strftime("%Y-%m-%d"),
                "tipo": a.tipo,
                "dia_semana": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dia_semana],
            })

        # Check existing liquidacion
        liq_existing = db.query(LiquidacionSemanal).filter(
            LiquidacionSemanal.empleado_id == emp.id,
            LiquidacionSemanal.fecha_inicio_semana >= inicio_semana,
            LiquidacionSemanal.fecha_inicio_semana <= inicio_semana + timedelta(hours=1)
        ).first()

        result.append({
            "empleado_id": emp.id,
            "empleado_nombre": emp.nombre,
            "empleado_rol": emp.rol_empresa or "GENERAL",
            "tipo_tarifa": emp.tipo_tarifa,
            "monto_tarifa": emp.monto_tarifa or 0,
            "dias_trabajados": dias_trabajados,
            "horas_trabajadas": horas_trabajadas if emp.tipo_tarifa == "POR_HORA" else None,
            "monto_total": round(monto, 2),
            "pagado": liq_existing.pagado if liq_existing else False,
            "liquidacion_id": liq_existing.id if liq_existing else None,
            "detalle": detalle,
        })

    return {
        "semana_inicio": inicio_semana.isoformat(),
        "semana_fin": fin_semana.isoformat(),
        "empleados": result,
    }


@router.post("/api/personal/liquidacion/pagar")
async def marcar_pagado(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    data = await request.json()
    emp_id = data["empleado_id"]
    monto = data["monto_total"]
    dias = data.get("dias_trabajados", 0)

    if data.get("fecha_inicio"):
        inicio_semana = datetime.fromisoformat(data["fecha_inicio"])
    else:
        inicio_semana = _get_inicio_semana()

    fin_semana = inicio_semana + timedelta(days=6)

    existing = db.query(LiquidacionSemanal).filter(
        LiquidacionSemanal.empleado_id == emp_id,
        LiquidacionSemanal.fecha_inicio_semana >= inicio_semana,
        LiquidacionSemanal.fecha_inicio_semana <= inicio_semana + timedelta(hours=1)
    ).first()

    if existing:
        existing.pagado = True
        existing.fecha_pago = datetime.now()
        existing.monto_total = monto
    else:
        liq = LiquidacionSemanal(
            empleado_id=emp_id,
            fecha_inicio_semana=inicio_semana,
            fecha_fin_semana=fin_semana,
            dias_trabajados=dias,
            monto_total=monto,
            pagado=True,
            fecha_pago=datetime.now(),
        )
        db.add(liq)

    db.commit()
    return {"ok": True}


@router.get("/api/personal/liquidacion/historial")
async def historial_liquidaciones(
    emp_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    q = db.query(LiquidacionSemanal)
    if emp_id:
        q = q.filter(LiquidacionSemanal.empleado_id == emp_id)
    liqs = q.order_by(LiquidacionSemanal.fecha_inicio_semana.desc()).limit(50).all()

    return [{
        "id": l.id,
        "empleado_nombre": l.empleado.nombre if l.empleado else "",
        "semana_inicio": l.fecha_inicio_semana.isoformat() if l.fecha_inicio_semana else "",
        "semana_fin": l.fecha_fin_semana.isoformat() if l.fecha_fin_semana else "",
        "dias_trabajados": l.dias_trabajados,
        "monto_total": l.monto_total,
        "pagado": l.pagado,
        "fecha_pago": l.fecha_pago.isoformat() if l.fecha_pago else None,
    } for l in liqs]


def _get_inicio_semana() -> datetime:
    hoy = datetime.now()
    # Monday of current week
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes.replace(hour=0, minute=0, second=0, microsecond=0)


# ─── ADELANTOS DE SUELDO ──────────────────────────────────────────────────────

@router.get("/api/personal/adelantos")
async def list_adelantos(
    emp_id: Optional[int] = None,
    descontado: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    q = db.query(AdelantoSueldo)
    if emp_id:
        q = q.filter(AdelantoSueldo.empleado_id == emp_id)
    if descontado is not None:
        q = q.filter(AdelantoSueldo.descontado == descontado)
    adelantos = q.order_by(AdelantoSueldo.fecha.desc()).limit(100).all()

    return [{
        "id": a.id,
        "empleado_id": a.empleado_id,
        "empleado_nombre": a.empleado.nombre if a.empleado else "",
        "monto": a.monto,
        "fecha": a.fecha.isoformat() if a.fecha else "",
        "motivo": a.motivo or "",
        "descontado": a.descontado,
        "liquidacion_id": a.liquidacion_id,
    } for a in adelantos]


@router.post("/api/personal/adelantos")
async def create_adelanto(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    data = await request.json()
    emp_id = data.get("empleado_id")
    if not emp_id:
        raise HTTPException(400, "empleado_id requerido")

    emp = db.query(Empleado).filter(Empleado.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")

    fecha = datetime.now()
    if data.get("fecha"):
        try:
            fecha = datetime.fromisoformat(data["fecha"])
        except Exception:
            pass

    adelanto = AdelantoSueldo(
        empleado_id=emp_id,
        monto=float(data.get("monto", 0)),
        fecha=fecha,
        motivo=data.get("motivo", ""),
        descontado=False,
    )
    db.add(adelanto)
    db.commit()
    db.refresh(adelanto)
    return {"id": adelanto.id, "ok": True}


@router.put("/api/personal/adelantos/{adelanto_id}")
async def update_adelanto(
    adelanto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    adelanto = db.query(AdelantoSueldo).filter(AdelantoSueldo.id == adelanto_id).first()
    if not adelanto:
        raise HTTPException(404, "Adelanto no encontrado")

    data = await request.json()
    for field in ("monto", "motivo", "descontado", "liquidacion_id"):
        if field in data:
            setattr(adelanto, field, data[field])
    db.commit()
    return {"ok": True}


@router.delete("/api/personal/adelantos/{adelanto_id}")
async def delete_adelanto(
    adelanto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "FABRICA" not in roles and "ADMINISTRACION" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    adelanto = db.query(AdelantoSueldo).filter(AdelantoSueldo.id == adelanto_id).first()
    if not adelanto:
        raise HTTPException(404, "No encontrado")
    if adelanto.descontado:
        raise HTTPException(400, "No se puede eliminar un adelanto ya descontado")
    db.delete(adelanto)
    db.commit()
    return {"ok": True}
