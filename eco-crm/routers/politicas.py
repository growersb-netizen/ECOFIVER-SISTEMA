"""
API de políticas empresariales versionadas y de la dirección (Máximo).

Sistema de agentes (API key + X-Origen-Cliente + X-Agente):
  - proponer políticas (Máximo, Aurora, Tomás) → quedan PENDIENTE_APROBACION;
  - leer las políticas activas de un agente (capa 2);
  - fijar objetivos económicos SOLO con autorización humana (canal del propietario);
  - leer el panel económico (solo Máximo).
Propietario (rol PROPIETARIO): aprobar, rechazar, suspender y revertir.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import PoliticaEmpresarial, PoliticaEvento, Usuario
from routers.circuito_comercial import _agente, _propietario
from routers.auth import get_user_roles
from utils import comisiones_propietario as cp
from utils import politicas as pol
from utils.motor_tareas import ErrorMotor
from utils.origen import autorizacion_humana

router = APIRouter()
DIRECTORES = {"maximo", "aurora", "tomas"}


def _err(e: ErrorMotor):
    raise HTTPException(e.codigo, str(e))


class Propuesta(BaseModel):
    titulo: str
    instruccion: str
    objetivo: str = ""
    departamento: str = ""
    agentes: list[str] = []
    metrica_exito: str = ""
    codigo: Optional[str] = None


class Decision(BaseModel):
    aprobar: bool
    comentario: str = ""


class Motivo(BaseModel):
    motivo: str = ""


class ObjetivoChat(BaseModel):
    periodo: str
    indicador: str
    valor: float
    producto: str = ""
    canal: str = ""
    nota: str = ""


def _propietario_id(db: Session) -> Optional[int]:
    for u in db.query(Usuario).filter(Usuario.activo == True):  # noqa: E712
        if "PROPIETARIO" in get_user_roles(u) and not u.aliado_codigo and not u.es_agente_ia:
            return u.id
    return None


# ── Sistema de agentes ────────────────────────────────────────────────────────

@router.post("/api/motor/politicas")
def proponer(body: Propuesta, request: Request, db: Session = Depends(get_db)):
    agente = _agente(request)
    if agente not in DIRECTORES:
        raise HTTPException(403, "Solo la dirección (Máximo, Aurora, Tomás) propone políticas")
    try:
        p = pol.proponer(db, titulo=body.titulo, instruccion=body.instruccion, autor=f"agente:{agente}",
                         objetivo=body.objetivo, departamento=body.departamento, agentes=body.agentes,
                         metrica_exito=body.metrica_exito, codigo=body.codigo)
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "politica": pol.politica_dict(p)}


@router.get("/api/motor/politicas/activas")
def activas(agente: str, request: Request, db: Session = Depends(get_db)):
    _agente(request)
    return {"politicas": [{"codigo": p.codigo, "version": p.version, "titulo": p.titulo, "instruccion": p.instruccion}
                          for p in pol.activas_para(db, agente)]}


@router.post("/api/motor/objetivos")
def objetivo_desde_chat(body: ObjetivoChat, request: Request, db: Session = Depends(get_db)):
    """Máximo fija un objetivo SOLO cuando el propietario lo pidió en su canal verificado."""
    agente = _agente(request)
    if agente != "maximo" or not autorizacion_humana(request).startswith("canal:"):
        raise HTTPException(403, "Los objetivos se fijan por pedido del propietario en su canal (o desde el panel)")
    uid = _propietario_id(db)
    if uid is None:
        raise HTTPException(409, "No hay un usuario con rol PROPIETARIO para registrar la autorización")
    try:
        o = cp.fijar_objetivo(db, periodo=body.periodo, indicador=body.indicador, valor=body.valor, usuario_id=uid,
                              producto=body.producto, canal=body.canal, origen="conversacion_maximo",
                              nota=(body.nota + f" [{autorizacion_humana(request)}]").strip())
    except ErrorMotor as e:
        _err(e)
    return {"ok": True, "objetivo": {"id": o.id, "version": o.version, "valor": o.valor}}


@router.get("/api/motor/propietario/panel")
def panel_para_maximo(request: Request, periodo: Optional[str] = None, db: Session = Depends(get_db)):
    if _agente(request) != "maximo":
        raise HTTPException(403, "El panel económico del propietario es solo para Máximo")
    from datetime import datetime
    try:
        return cp.panel(db, periodo or datetime.utcnow().strftime("%Y-%m"))
    except ErrorMotor as e:
        _err(e)


# ── Propietario ───────────────────────────────────────────────────────────────

@router.get("/api/politicas")
def listar(estado: Optional[str] = None, db: Session = Depends(get_db), _: Usuario = Depends(_propietario)):
    q = db.query(PoliticaEmpresarial)
    if estado:
        q = q.filter(PoliticaEmpresarial.estado == estado.upper())
    return {"politicas": [pol.politica_dict(p) for p in q.order_by(PoliticaEmpresarial.id.desc()).limit(200)]}


@router.get("/api/politicas/{pid}")
def ver(pid: int, db: Session = Depends(get_db), _: Usuario = Depends(_propietario)):
    p = db.get(PoliticaEmpresarial, pid)
    if not p:
        raise HTTPException(404, "Política inexistente")
    return pol.politica_dict(p, db.query(PoliticaEvento).filter_by(politica_id=pid).order_by(PoliticaEvento.id).all())


@router.post("/api/politicas/{pid}/decidir")
def decidir(pid: int, body: Decision, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        return {"ok": True, "politica": pol.politica_dict(pol.decidir(db, pid, user.id, body.aprobar, body.comentario))}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/politicas/{pid}/suspender")
def suspender(pid: int, body: Motivo, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        return {"ok": True, "politica": pol.politica_dict(pol.suspender(db, pid, user.id, body.motivo))}
    except ErrorMotor as e:
        _err(e)


@router.post("/api/politicas/{pid}/revertir")
def revertir(pid: int, body: Motivo, db: Session = Depends(get_db), user: Usuario = Depends(_propietario)):
    try:
        return {"ok": True, "politica": pol.politica_dict(pol.revertir(db, pid, user.id, body.motivo))}
    except ErrorMotor as e:
        _err(e)
