from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Videollamada, Usuario, Notificacion, Lead, Interaccion
from routers.auth import require_auth, require_roles, get_user_roles
from routers.notificaciones import notificar_videollamada

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def vl_to_dict(vl: Videollamada) -> dict:
    return {
        "id": vl.id,
        "lead_id": vl.lead_id,
        "cliente_nombre": vl.cliente_nombre,
        "cliente_telefono": vl.cliente_telefono or "",
        "producto_interes": vl.producto_interes or "",
        "forma_pago": vl.forma_pago or "",
        "asesor_apertura_id": vl.asesor_apertura_id,
        "asesor_apertura_nombre": vl.asesor_apertura.nombre if vl.asesor_apertura else "",
        "supervisor_cierre_id": vl.supervisor_cierre_id,
        "supervisor_cierre_nombre": vl.supervisor_cierre.nombre if vl.supervisor_cierre else "",
        "fecha_hora": vl.fecha_hora.isoformat() if vl.fecha_hora else None,
        "estado": vl.estado or "AGENDADA",
        "estado_admision": vl.estado_admision,
        "resultado": vl.resultado or "PENDIENTE",
        "notas": vl.notas or "",
        "comision_asesor_pct": vl.comision_asesor_pct or 0,
        "comision_supervisor_pct": vl.comision_supervisor_pct or 0,
        "created_at": vl.created_at.isoformat() if vl.created_at else "",
    }


@router.get("/semana-vls", response_class=HTMLResponse)
async def semana_vls_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("semana_vls.html", {
        "request": request, "user": current_user, "roles": roles,
    })


@router.get("/api/videollamadas/semana")
async def get_semana_vls(
    offset: Optional[int] = 0,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """VLs agrupadas por día — rolling 7 días desde hoy + offset."""
    hoy = datetime.now().date()
    inicio_date = hoy + timedelta(days=offset or 0)
    fin_date    = inicio_date + timedelta(days=6)

    inicio = datetime.combine(inicio_date, datetime.min.time())
    fin    = datetime.combine(fin_date,    datetime.max.time().replace(microsecond=0))

    vls = db.query(Videollamada).filter(
        Videollamada.fecha_hora >= inicio,
        Videollamada.fecha_hora <= fin,
    ).order_by(Videollamada.fecha_hora.asc()).all()

    def _vl(v):
        return {
            "id": v.id,
            "cliente_nombre": v.cliente_nombre or "",
            "cliente_telefono": v.cliente_telefono or "",
            "producto_interes": v.producto_interes or "",
            "forma_pago": v.forma_pago or "",
            "asesor_nombre": v.asesor_apertura.nombre if v.asesor_apertura else "",
            "supervisor_nombre": v.supervisor_cierre.nombre if v.supervisor_cierre else "",
            "hora": v.fecha_hora.strftime("%H:%M") if v.fecha_hora else "",
            "estado": v.estado or "AGENDADA",
            "resultado": v.resultado or "PENDIENTE",
            "notas": v.notas or "",
        }

    DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dias = []
    for i in range(7):
        dia_date = inicio_date + timedelta(days=i)
        wd = dia_date.weekday()
        dia_vls = [_vl(v) for v in vls if v.fecha_hora and v.fecha_hora.date() == dia_date]
        dias.append({
            "fecha": dia_date.isoformat(),
            "dia": DIAS[wd],
            "dia_corto": DIAS[wd][:3],
            "numero": dia_date.day,
            "mes": dia_date.strftime("%b"),
            "es_hoy": dia_date == hoy,
            "vls": dia_vls,
            "total": len(dia_vls),
        })

    return {
        "inicio": inicio_date.isoformat(),
        "fin": fin_date.isoformat(),
        "offset": offset or 0,
        "dias": dias,
        "total_semana": len(vls),
    }


@router.get("/videollamadas", response_class=HTMLResponse)
async def videollamadas_page(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    supervisores = db.query(Usuario).filter(Usuario.activo == True).all()
    return templates.TemplateResponse("videollamadas.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "supervisores": [{"id": u.id, "nombre": u.nombre} for u in supervisores],
    })


@router.get("/api/videollamadas")
async def list_videollamadas(
    request: Request,
    fecha: Optional[str] = None,
    estado: Optional[str] = None,
    sin_supervisor: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    q = db.query(Videollamada)

    if "SUPERVISOR_CIERRE" in roles and "ADMIN" not in roles:
        pass  # supervisores ven todas

    if estado:
        q = q.filter(Videollamada.estado == estado)
    if sin_supervisor:
        q = q.filter(Videollamada.supervisor_cierre_id == None)
    if fecha:
        try:
            dt = datetime.fromisoformat(fecha)
            q = q.filter(
                Videollamada.fecha_hora >= dt.replace(hour=0, minute=0, second=0),
                Videollamada.fecha_hora <= dt.replace(hour=23, minute=59, second=59)
            )
        except Exception:
            pass

    vls = q.order_by(Videollamada.fecha_hora.asc()).all()
    return [vl_to_dict(v) for v in vls]


@router.get("/api/videollamadas/hoy")
async def videollamadas_hoy(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    hoy = datetime.now()
    inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = hoy.replace(hour=23, minute=59, second=59, microsecond=999999)
    vls = db.query(Videollamada).filter(
        Videollamada.fecha_hora >= inicio,
        Videollamada.fecha_hora <= fin
    ).order_by(Videollamada.fecha_hora.asc()).all()
    return [vl_to_dict(v) for v in vls]


@router.post("/api/videollamadas/{vl_id}/resultado-trabajo")
async def resultado_trabajo_vl(
    vl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    """Registra resultado de VL desde el modo trabajo del supervisor."""
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "VL no encontrada")
    data = await request.json()

    # Asignar supervisor si aún no tiene
    if not vl.supervisor_cierre_id:
        vl.supervisor_cierre_id = current_user.id

    estado = data.get("estado")      # REALIZADA | NO_SE_PRESENTO | REPROGRAMAR
    resultado = data.get("resultado")  # AVANZO | NO_CALIFICO | CERRO | PENDIENTE
    notas = data.get("notas", "")

    if estado:
        vl.estado = estado
    if resultado:
        vl.resultado = resultado
    if notas:
        vl.notas = (vl.notas or "") + f"\n[Trabajo {datetime.now().strftime('%d/%m %H:%M')}] {notas}"

    db.commit()
    return {"ok": True, "estado": vl.estado, "resultado": vl.resultado}


@router.get("/api/videollamadas/{vl_id}")
async def get_videollamada(
    vl_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    return vl_to_dict(vl)


@router.post("/api/videollamadas")
async def create_videollamada(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    data = await request.json()
    fecha_hora = None
    if data.get("fecha_hora"):
        try:
            fecha_hora = datetime.fromisoformat(data["fecha_hora"])
        except Exception:
            pass

    # A5: Auto-vincular lead por teléfono si no viene lead_id
    lead_id = data.get("lead_id")
    telefono = data.get("cliente_telefono", "")
    if not lead_id and telefono:
        lead = db.query(Lead).filter(
            Lead.telefono.ilike(f"%{telefono.strip()}%")
        ).order_by(Lead.created_at.desc()).first()
        if lead and lead.estado not in ["CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]:
            lead_id = lead.id
            lead.estado = "VIDEOLLAMADA_AGENDADA"

    vl = Videollamada(
        lead_id=lead_id,
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_telefono=telefono,
        producto_interes=data.get("producto_interes", ""),
        forma_pago=data.get("forma_pago", ""),
        asesor_apertura_id=data.get("asesor_apertura_id"),
        supervisor_cierre_id=data.get("supervisor_cierre_id"),
        fecha_hora=fecha_hora,
        estado=data.get("estado", "AGENDADA"),
        estado_admision=data.get("estado_admision"),
        notas=data.get("notas", ""),
        comision_asesor_pct=data.get("comision_asesor_pct", 0),
        comision_supervisor_pct=data.get("comision_supervisor_pct", 0),
    )
    db.add(vl)
    db.commit()
    db.refresh(vl)

    # Notificar a todos
    asesor = db.query(Usuario).filter(Usuario.id == vl.asesor_apertura_id).first() if vl.asesor_apertura_id else None
    fecha_str = vl.fecha_hora.strftime("%d/%m/%Y %H:%M") if vl.fecha_hora else ""
    notificar_videollamada(
        db,
        accion="NUEVA",
        cliente_nombre=vl.cliente_nombre,
        producto=vl.producto_interes or "",
        fecha_hora=fecha_str,
        asesor_nombre=asesor.nombre if asesor else "",
        referencia_id=vl.id,
    )
    db.commit()

    return {"id": vl.id, "ok": True}


@router.put("/api/videollamadas/{vl_id}")
async def update_videollamada(
    vl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")

    data = await request.json()

    if "fecha_hora" in data and data["fecha_hora"]:
        try:
            vl.fecha_hora = datetime.fromisoformat(data["fecha_hora"])
        except Exception:
            pass

    old_estado = vl.estado
    old_resultado = vl.resultado

    for field in ["cliente_nombre", "cliente_telefono", "producto_interes", "forma_pago",
                  "asesor_apertura_id", "supervisor_cierre_id", "estado", "estado_admision",
                  "resultado", "notas", "comision_asesor_pct", "comision_supervisor_pct"]:
        if field in data:
            setattr(vl, field, data[field])

    db.commit()

    # Notificar cambios de estado relevantes
    nuevo_estado    = data.get("estado", old_estado)
    nuevo_resultado = data.get("resultado", old_resultado)

    accion = None
    if nuevo_estado != old_estado:
        if nuevo_estado == "REALIZADA":
            accion = "REALIZADA"
        elif nuevo_estado == "NO_SE_PRESENTO":
            accion = "NO_SE_PRESENTO"
        elif nuevo_estado == "REPROGRAMAR":
            accion = "REPROGRAMAR"
    if nuevo_resultado != old_resultado and nuevo_resultado == "CERRO":
        accion = "CERRO"

    if accion:
        notificar_videollamada(
            db,
            accion=accion,
            cliente_nombre=vl.cliente_nombre,
            producto=vl.producto_interes or "",
            referencia_id=vl.id,
        )
        db.commit()

    return {"ok": True}


@router.post("/api/videollamadas/{vl_id}/tomar")
async def tomar_videollamada(
    vl_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("SUPERVISOR_CIERRE"))
):
    vl = db.query(Videollamada).filter(Videollamada.id == vl_id).first()
    if not vl:
        raise HTTPException(404, "Videollamada no encontrada")
    vl.supervisor_cierre_id = current_user.id
    db.commit()
    return {"ok": True}
