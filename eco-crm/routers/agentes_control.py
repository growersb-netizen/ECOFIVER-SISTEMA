"""
API de control empresarial de agentes (Fase 2).

Administradores humanos: estado por agente y por departamento, guardias,
historial. Sistema de agentes (API key): lectura del estado efectivo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AgenteControlEvento, GuardiaOperativa, Usuario
from routers.auth import get_user_roles
from routers.tareas import _api_key, _humano
from utils import control_agentes as ctl
from utils.motor_tareas import ErrorMotor

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/operaciones-ia", response_class=HTMLResponse)
def pagina_operaciones(request: Request, user: Usuario = Depends(_humano)):
    """Vista 2D de EcoFiver AI Company: agentes, tareas, aprobaciones y guardias (datos reales del motor)."""
    return templates.TemplateResponse(request, "operaciones_ia.html",
                                      {"request": request, "user": user, "roles": get_user_roles(user)})


class CambioEstado(BaseModel):
    estado: str
    motivo: str = ""


class NuevaGuardia(BaseModel):
    alcance: str
    desde: datetime
    hasta: datetime
    motivo: str


def _err(e: ErrorMotor):
    raise HTTPException(e.codigo, str(e))


def _tablero(db: Session) -> dict:
    est, act = ctl.estados(db), ctl.actividad(db)
    agentes = []
    for a, e in est.items():
        permitido, motivo = ctl.salida_permitida(db, a)
        agentes.append({**e, "actividad": act[a], "salientes_permitidos": permitido, "salientes_motivo": motivo})
    return {"agentes": agentes, "en_horario": ctl.en_horario(),
            "horario": "Salientes: lunes a sábado 09:00–21:00 (America/Argentina/Buenos_Aires). Entrante WhatsApp: 24/7.",
            "guardias_activas": [ctl.guardia_dict(g) for g in ctl.guardias_activas(db)],
            "departamentos": {d: sorted(v) for d, v in ctl.DEPARTAMENTOS.items()}}


@router.get("/api/agentes/control")
def tablero(db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    return _tablero(db)


@router.post("/api/agentes/{agente}/estado")
def estado_agente(agente: str, body: CambioEstado, db: Session = Depends(get_db), user: Usuario = Depends(_humano)):
    try:
        return {"ok": True, **ctl.cambiar_estado(db, agente, body.estado, body.motivo, user.id)}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/departamentos/{departamento}/estado")
def estado_departamento(departamento: str, body: CambioEstado, db: Session = Depends(get_db),
                        user: Usuario = Depends(_humano)):
    try:
        return {"ok": True, "cambios": ctl.cambiar_departamento(db, departamento, body.estado, body.motivo, user.id)}
    except ErrorMotor as e:
        _err(e)


@router.get("/api/agentes/control/historial")
def historial(agente: Optional[str] = None, db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    q = db.query(AgenteControlEvento)
    if agente:
        q = q.filter(AgenteControlEvento.agente == agente)
    return {"eventos": [{"agente": e.agente, "de": e.estado_anterior, "a": e.estado_nuevo, "motivo": e.motivo,
                         "usuario_id": e.usuario_id, "ts": e.created_at.isoformat() if e.created_at else None}
                        for e in q.order_by(AgenteControlEvento.id.desc()).limit(200)]}


@router.get("/api/guardias")
def guardias(db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    return {"guardias": [ctl.guardia_dict(g) for g in
                         db.query(GuardiaOperativa).order_by(GuardiaOperativa.id.desc()).limit(100)]}


@router.post("/api/guardias")
def crear_guardia(body: NuevaGuardia, db: Session = Depends(get_db), user: Usuario = Depends(_humano)):
    try:
        return {"ok": True, "guardia": ctl.guardia_dict(
            ctl.crear_guardia(db, body.alcance, body.desde, body.hasta, body.motivo, user.id))}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/guardias/{guardia_id}/finalizar")
def finalizar_guardia(guardia_id: int, db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    g = db.get(GuardiaOperativa, guardia_id)
    if not g:
        raise HTTPException(404, "Guardia inexistente")
    g.activa = False
    db.commit()
    return {"ok": True}


@router.get("/api/motor/control")
def control_para_agentes(db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    """Estado efectivo para el multiagente: quién trabaja y quién puede iniciar salientes ahora."""
    est = ctl.estados(db)
    return {"estados": {a: e["estado"] for a, e in est.items()},
            "salientes_permitidos": {a: ctl.salida_permitida(db, a)[0] for a in est},
            "en_horario": ctl.en_horario()}
