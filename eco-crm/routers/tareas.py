"""
API del motor de tareas (Fase 1).

/api/motor/*   → sistema de agentes (API key). Reclamar, latido, completar,
                 fallar, delegar, proponer acciones sensibles.
/api/tareas/*  → administradores humanos (sesión CRM con rol ADMIN). Crear,
                 consultar, cancelar y decidir aprobaciones.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AprobacionAccion, ComandoAgente, TareaEvento, Usuario
from routers.auth import require_roles
from utils import motor_tareas as motor
from utils.api_keys import api_key_valida

router = APIRouter()
_solo_admin = require_roles("ADMIN")


def _api_key(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and api_key_valida(auth[7:].strip()):
        return True
    raise HTTPException(401, "API key inválida")


def _humano(user: Usuario = Depends(_solo_admin)) -> Usuario:
    if getattr(user, "es_agente_ia", False):
        raise HTTPException(403, "Requiere un administrador humano")
    return user


def _err(e: motor.ErrorMotor):
    raise HTTPException(e.codigo, str(e))


class NuevaTarea(BaseModel):
    agente: str
    creado_por_agente: Optional[str] = None
    instruccion: str = Field(min_length=1, max_length=8000)
    titulo: str = ""
    prioridad: str = "NORMAL"
    area: str = "GENERAL"
    contexto: dict = {}
    clave_idempotencia: Optional[str] = Field(default=None, max_length=120)


class NuevaSubtarea(NuevaTarea):
    padre_id: int
    creado_por_agente: str


class Reclamo(BaseModel):
    worker: str = Field(min_length=1, max_length=80)
    agentes: Optional[list[str]] = None


class Lease(BaseModel):
    lease_token: str


class Resultado(Lease):
    resultado: dict = {}
    evidencia: dict = {}
    costo_usd: float = 0


class Falla(Lease):
    error: str = ""
    reintentable: bool = True
    costo_usd: float = 0


class Propuesta(BaseModel):
    tarea_id: Optional[int] = None
    agente: str
    tipo_accion: str
    datos: dict = {}
    motivo: str = ""


class ResultadoAprobacion(Lease):
    ok: bool
    resultado: str = ""


class Decision(BaseModel):
    aprobar: bool
    comentario: str = ""


# ── Sistema de agentes (API key) ─────────────────────────────────────────────

@router.post("/api/motor/tareas")
def motor_crear(body: NuevaTarea, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    """Tarea pedida por el sistema de agentes sin tarea padre (/api/comando, o Máximo desde el chat del propietario)."""
    try:
        t, creada = motor.crear_tarea(db, agente=body.agente, instruccion=body.instruccion, titulo=body.titulo,
                                      prioridad=body.prioridad, area=body.area, contexto=body.contexto,
                                      clave_idempotencia=body.clave_idempotencia,
                                      creado_por_agente=body.creado_por_agente)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "creada": creada, "tarea": motor.tarea_dict(t)}


@router.post("/api/motor/delegar")
def motor_delegar(body: NuevaSubtarea, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    try:
        t, creada = motor.crear_tarea(db, agente=body.agente, instruccion=body.instruccion, titulo=body.titulo,
                                      prioridad=body.prioridad, area=body.area, contexto=body.contexto,
                                      creado_por_agente=body.creado_por_agente, padre_id=body.padre_id,
                                      clave_idempotencia=body.clave_idempotencia)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "creada": creada, "tarea": motor.tarea_dict(t)}


@router.post("/api/motor/reclamar")
def motor_reclamar(body: Reclamo, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    agentes = None if body.agentes is None else {motor.normalizar_agente(a) for a in body.agentes}
    t = motor.reclamar(db, body.worker, agentes)
    if not t:
        return {"tarea": None}
    d = motor.tarea_dict(t)
    d["lease_token"] = t.lease_token
    return {"tarea": d}


@router.post("/api/motor/tareas/{tarea_id}/latido")
def motor_latido(tarea_id: int, body: Lease, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    try:
        return motor.latido(db, tarea_id, body.lease_token)
    except motor.ErrorMotor as e:
        _err(e)


@router.post("/api/motor/tareas/{tarea_id}/completar")
def motor_completar(tarea_id: int, body: Resultado, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    try:
        t = motor.completar(db, tarea_id, body.lease_token, body.resultado, body.evidencia, body.costo_usd)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "estado": t.estado}


@router.post("/api/motor/tareas/{tarea_id}/fallar")
def motor_fallar(tarea_id: int, body: Falla, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    try:
        t = motor.fallar(db, tarea_id, body.lease_token, body.error, body.reintentable, body.costo_usd)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "estado": t.estado}


@router.get("/api/motor/tareas/{tarea_id}")
def motor_ver(tarea_id: int, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    t = db.get(ComandoAgente, tarea_id)
    if not t or t.version_motor != 1:
        raise HTTPException(404, "Tarea inexistente")
    return motor.tarea_dict(t)


@router.post("/api/motor/aprobaciones")
def motor_proponer(body: Propuesta, db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    try:
        a = motor.proponer_accion(db, tarea_id=body.tarea_id, agente=body.agente, tipo_accion=body.tipo_accion,
                                  datos=body.datos, motivo=body.motivo)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "aprobacion": motor.aprobacion_dict(a)}


@router.post("/api/motor/aprobaciones/reclamar")
def motor_reclamar_aprobada(db: Session = Depends(get_db), _: bool = Depends(_api_key)):
    a = motor.reclamar_aprobada(db)
    if not a:
        return {"aprobacion": None}
    d = motor.aprobacion_dict(a)
    d["lease_token"] = a.lease_token
    return {"aprobacion": d}


@router.post("/api/motor/aprobaciones/{aprobacion_id}/resultado")
def motor_resultado_aprobacion(aprobacion_id: int, body: ResultadoAprobacion, db: Session = Depends(get_db),
                               _: bool = Depends(_api_key)):
    try:
        a = motor.resultado_aprobacion(db, aprobacion_id, body.lease_token, body.ok, body.resultado)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "estado": a.estado}


# ── Administradores humanos ──────────────────────────────────────────────────

@router.post("/api/tareas")
def crear(body: NuevaTarea, db: Session = Depends(get_db), user: Usuario = Depends(_humano)):
    try:
        t, creada = motor.crear_tarea(db, agente=body.agente, instruccion=body.instruccion, titulo=body.titulo,
                                      prioridad=body.prioridad, area=body.area, contexto=body.contexto,
                                      enviado_por_id=user.id, clave_idempotencia=body.clave_idempotencia)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "creada": creada, "tarea": motor.tarea_dict(t)}


@router.get("/api/tareas")
def listar(estado: Optional[str] = None, agente: Optional[str] = None, limit: int = 50,
           db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    q = db.query(ComandoAgente).filter(ComandoAgente.version_motor == 1)
    if estado:
        q = q.filter(ComandoAgente.estado == estado.upper())
    if agente:
        q = q.filter(ComandoAgente.agente_destino == motor.normalizar_agente(agente))
    return {"tareas": [motor.tarea_dict(t) for t in q.order_by(ComandoAgente.id.desc()).limit(min(limit, 200))]}


@router.get("/api/tareas/{tarea_id}")
def ver(tarea_id: int, db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    t = db.get(ComandoAgente, tarea_id)
    if not t or t.version_motor != 1:
        raise HTTPException(404, "Tarea inexistente")
    eventos = db.query(TareaEvento).filter_by(tarea_id=t.id).order_by(TareaEvento.id).all()
    d = motor.tarea_dict(t, eventos)
    d["subtareas"] = [motor.tarea_dict(x) for x in
                      db.query(ComandoAgente).filter(ComandoAgente.padre_id == t.id).order_by(ComandoAgente.id)]
    d["aprobaciones"] = [motor.aprobacion_dict(a) for a in
                         db.query(AprobacionAccion).filter_by(tarea_id=t.id).order_by(AprobacionAccion.id)]
    return d


@router.post("/api/tareas/{tarea_id}/cancelar")
def cancelar(tarea_id: int, db: Session = Depends(get_db), user: Usuario = Depends(_humano)):
    try:
        t = motor.cancelar(db, tarea_id, f"usuario:{user.id}")
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "estado": t.estado, "cancelacion_solicitada": bool(t.cancelacion_solicitada)}


@router.get("/api/aprobaciones")
def aprobaciones(estado: str = "PENDIENTE", db: Session = Depends(get_db), _: Usuario = Depends(_humano)):
    q = db.query(AprobacionAccion)
    if estado != "TODAS":
        q = q.filter(AprobacionAccion.estado == estado.upper())
    return {"aprobaciones": [motor.aprobacion_dict(a) for a in q.order_by(AprobacionAccion.id.desc()).limit(200)]}


@router.post("/api/aprobaciones/{aprobacion_id}/decidir")
def decidir(aprobacion_id: int, body: Decision, db: Session = Depends(get_db), user: Usuario = Depends(_humano)):
    try:
        a = motor.decidir(db, aprobacion_id, user, body.aprobar, body.comentario)
    except motor.ErrorMotor as e:
        _err(e)
    return {"ok": True, "aprobacion": motor.aprobacion_dict(a)}
