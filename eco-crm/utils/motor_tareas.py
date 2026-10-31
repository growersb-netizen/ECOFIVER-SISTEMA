"""
Motor de tareas de EcoFiver AI Company (Fase 1).

La fuente de verdad es la base del CRM (tabla comandos_agente, ampliada). El
multiagente ejecuta: reclama una tarea con un lease, la ejecuta con el agente
real y devuelve resultado y evidencia. Si el proceso se reinicia a mitad de
camino, el lease vence y otra ejecución la retoma (hasta max_intentos).

Reglas:
  - Solo las tareas con version_motor=1 se ejecutan (los comandos históricos no).
  - Idempotencia: misma clave_idempotencia → misma tarea.
  - Reclamo y finalización son condicionales (UPDATE … WHERE): dos workers no
    ejecutan la misma tarea y un worker con lease vencido no pisa un resultado.
  - Delegación: solo directores (Máximo, Aurora, Tomás), profundidad y cantidad
    acotadas, nunca a Valentín (asistente personal, fuera de la empresa).
  - Los permisos NO salen del texto de la instrucción: las acciones sensibles se
    proponen y requieren la decisión de un administrador humano.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.models import AprobacionAccion, ComandoAgente, TareaEvento

# Los 16 agentes de la empresa. Valentín es el asistente personal: no recibe tareas.
AGENTES_EMPRESA = {
    "maximo", "aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo",
    "renata", "bruno", "ezequiel", "elena", "ignacio", "sebastian", "daniela", "franco",
}
DEPARTAMENTOS = {
    "direccion": {"maximo"},
    "comercial": {"aurora", "tomas", "valentina", "camila", "nicolas", "luciano", "mateo"},
    "marketing": {"renata"},
    "operaciones": {"bruno"},
    "administracion": {"ezequiel", "elena", "ignacio"},
    "postventa": {"sebastian"},
    "reputacion": {"daniela"},
    "socios": {"franco"},
}
DELEGADORES = {"maximo", "aurora", "tomas"}

MAX_PROFUNDIDAD = 2          # Máximo → Aurora → Camila
MAX_TAREAS_POR_RAIZ = 10     # una orden no puede abrir más de 10 subtareas
LEASE_SEGUNDOS = 300
PRIORIDAD_ORDEN = {"URGENTE": 0, "NORMAL": 1, "BAJA": 2}

ESTADOS_TERMINALES = {"COMPLETADO", "FALLIDO", "CANCELADO"}


class ErrorMotor(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _ahora() -> datetime:
    return datetime.utcnow()


def presupuesto_raiz_usd() -> float:
    try:
        return float(os.getenv("MOTOR_PRESUPUESTO_RAIZ_USD", "0.50"))
    except ValueError:
        return 0.50


def evento(db: Session, tarea_id: int, tipo: str, detalle: str = "", actor: str = "") -> None:
    db.add(TareaEvento(tarea_id=tarea_id, tipo=tipo, detalle=(detalle or "")[:4000], actor=(actor or "")[:100]))


def normalizar_agente(nombre: str) -> str:
    n = (nombre or "").strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        n = n.replace(a, b)
    return "maximo" if n in ("orquestador", "ceo", "") else n


def tarea_dict(t: ComandoAgente, con_eventos: Optional[list] = None) -> dict:
    d = {
        "id": t.id, "agente": t.agente_destino, "titulo": t.titulo, "instruccion": t.instruccion,
        "estado": t.estado, "prioridad": t.prioridad, "area": t.area, "contexto": t.contexto or {},
        "intentos": t.intentos or 0, "max_intentos": t.max_intentos or 0,
        "padre_id": t.padre_id, "raiz_id": t.raiz_id, "profundidad": t.profundidad or 0,
        "creado_por": t.creado_por_agente or "humano", "resultado": t.resultado,
        "evidencia": t.evidencia, "costo_usd": round(t.costo_usd or 0, 6),
        "cancelacion_solicitada": bool(t.cancelacion_solicitada),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "iniciado_at": t.iniciado_at.isoformat() if t.iniciado_at else None,
        "finalizado_at": t.finalizado_at.isoformat() if t.finalizado_at else None,
    }
    if con_eventos is not None:
        d["eventos"] = [{"tipo": e.tipo, "detalle": e.detalle, "actor": e.actor,
                         "ts": e.created_at.isoformat() if e.created_at else None} for e in con_eventos]
    return d


# ── Creación ──────────────────────────────────────────────────────────────────

def crear_tarea(db: Session, *, agente: str, instruccion: str, titulo: str = "", prioridad: str = "NORMAL",
                area: str = "GENERAL", contexto: Optional[dict] = None, enviado_por_id: Optional[int] = None,
                creado_por_agente: Optional[str] = None, padre_id: Optional[int] = None,
                clave_idempotencia: Optional[str] = None, max_intentos: int = 3) -> tuple[ComandoAgente, bool]:
    """Devuelve (tarea, creada). Si la clave ya existe devuelve la tarea existente."""
    agente = normalizar_agente(agente)
    instruccion = (instruccion or "").strip()
    if agente not in AGENTES_EMPRESA:
        raise ErrorMotor(f"Agente '{agente}' no recibe tareas de la empresa")
    if not instruccion:
        raise ErrorMotor("La instrucción no puede estar vacía")
    prioridad = (prioridad or "NORMAL").upper()
    if prioridad not in PRIORIDAD_ORDEN:
        prioridad = "NORMAL"
    if clave_idempotencia:
        existente = db.query(ComandoAgente).filter_by(clave_idempotencia=clave_idempotencia).first()
        if existente:
            return existente, False

    profundidad, raiz_id = 0, None
    if padre_id is not None:
        padre = db.get(ComandoAgente, padre_id)
        if not padre or padre.version_motor != 1:
            raise ErrorMotor("Tarea padre inexistente", 404)
        delegador = normalizar_agente(creado_por_agente or "")
        if delegador != padre.agente_destino:
            raise ErrorMotor("Solo el agente que ejecuta la tarea puede delegar desde ella", 403)
        if delegador not in DELEGADORES:
            raise ErrorMotor(f"'{delegador}' no tiene facultad de delegar", 403)
        if agente == delegador:
            raise ErrorMotor("Un agente no puede delegarse a sí mismo", 400)
        if padre.estado != "EN_EJECUCION":
            raise ErrorMotor("Solo se delega desde una tarea en ejecución", 409)
        profundidad = (padre.profundidad or 0) + 1
        if profundidad > MAX_PROFUNDIDAD:
            raise ErrorMotor(f"Profundidad de delegación máxima ({MAX_PROFUNDIDAD}) alcanzada", 409)
        raiz_id = padre.raiz_id or padre.id
        if db.query(ComandoAgente).filter(ComandoAgente.raiz_id == raiz_id).count() >= MAX_TAREAS_POR_RAIZ:
            raise ErrorMotor(f"La orden original ya tiene {MAX_TAREAS_POR_RAIZ} subtareas", 409)
        if costo_raiz(db, raiz_id) >= presupuesto_raiz_usd():
            raise ErrorMotor("Presupuesto de la orden original agotado", 409)

    t = ComandoAgente(
        tipo="TAREA", area=(area or "GENERAL").upper()[:30], prioridad=prioridad,
        titulo=(titulo or instruccion[:80])[:200], instruccion=instruccion, contexto=contexto or {},
        agente_destino=agente, estado="PENDIENTE", enviado_por_id=enviado_por_id,
        version_motor=1, clave_idempotencia=clave_idempotencia, intentos=0,
        max_intentos=max(1, min(int(max_intentos or 3), 5)), padre_id=padre_id, raiz_id=raiz_id,
        profundidad=profundidad, creado_por_agente=normalizar_agente(creado_por_agente) if creado_por_agente else None,
        costo_usd=0, cancelacion_solicitada=False,
    )
    db.add(t)
    db.flush()
    actor = f"agente:{t.creado_por_agente}" if t.creado_por_agente else f"usuario:{enviado_por_id or '?'}"
    evento(db, t.id, "DELEGADA" if padre_id else "CREADA", f"→ {agente}" + (f" (desde #{padre_id})" if padre_id else ""), actor)
    if padre_id:
        evento(db, padre_id, "SUBTAREA_CREADA", f"#{t.id} → {agente}", actor)
    db.commit()
    db.refresh(t)
    return t, True


def costo_raiz(db: Session, raiz_id: int) -> float:
    filas = db.query(ComandoAgente.costo_usd).filter(
        or_(ComandoAgente.id == raiz_id, ComandoAgente.raiz_id == raiz_id)).all()
    return sum((f[0] or 0) for f in filas)


# ── Reclamo, latido, resultado ────────────────────────────────────────────────

def _condicion_reclamable(ahora: datetime):
    disponible = and_(ComandoAgente.estado.in_(["PENDIENTE", "ERROR"]),
                      or_(ComandoAgente.proximo_intento.is_(None), ComandoAgente.proximo_intento <= ahora))
    lease_vencido = and_(ComandoAgente.estado == "EN_EJECUCION", ComandoAgente.lease_hasta < ahora)
    return and_(ComandoAgente.version_motor == 1,
                or_(ComandoAgente.cancelacion_solicitada.is_(None), ComandoAgente.cancelacion_solicitada == False),  # noqa: E712
                or_(disponible, lease_vencido))


def reclamar(db: Session, worker: str, agentes: Optional[set] = None) -> Optional[ComandoAgente]:
    """Toma la próxima tarea ejecutable (o una con lease vencido). Atómico entre workers."""
    ahora = _ahora()
    _vencer_agotadas(db, ahora)
    q = db.query(ComandoAgente).filter(_condicion_reclamable(ahora))
    if agentes is not None:
        if not agentes:
            return None
        q = q.filter(ComandoAgente.agente_destino.in_(sorted(agentes)))
    candidatas = q.order_by(ComandoAgente.id).limit(20).all()
    candidatas.sort(key=lambda t: (PRIORIDAD_ORDEN.get(t.prioridad or "NORMAL", 1), t.id))
    for c in candidatas:
        recuperada = c.estado == "EN_EJECUCION"
        token = secrets.token_hex(16)
        n = (db.query(ComandoAgente)
             .filter(ComandoAgente.id == c.id, _condicion_reclamable(ahora),
                     ComandoAgente.intentos < ComandoAgente.max_intentos)
             .update({ComandoAgente.estado: "EN_EJECUCION", ComandoAgente.lease_token: token,
                      ComandoAgente.lease_hasta: ahora + timedelta(seconds=LEASE_SEGUNDOS),
                      ComandoAgente.worker: (worker or "")[:80],
                      ComandoAgente.intentos: ComandoAgente.intentos + 1,
                      ComandoAgente.iniciado_at: ahora}, synchronize_session=False))
        if n == 1:
            evento(db, c.id, "RECUPERADA" if recuperada else "RECLAMADA", f"worker={worker}", f"worker:{worker}")
            db.commit()
            db.expire_all()
            return db.get(ComandoAgente, c.id)
        db.rollback()
    return None


def _vencer_agotadas(db: Session, ahora: datetime) -> None:
    """Tareas con lease vencido que ya usaron todos sus intentos → FALLIDO."""
    agotadas = db.query(ComandoAgente).filter(
        ComandoAgente.version_motor == 1, ComandoAgente.estado == "EN_EJECUCION",
        ComandoAgente.lease_hasta < ahora, ComandoAgente.intentos >= ComandoAgente.max_intentos).all()
    for t in agotadas:
        n = (db.query(ComandoAgente).filter(ComandoAgente.id == t.id, ComandoAgente.estado == "EN_EJECUCION",
                                            ComandoAgente.lease_hasta < ahora)
             .update({ComandoAgente.estado: "FALLIDO", ComandoAgente.finalizado_at: ahora,
                      ComandoAgente.lease_token: None}, synchronize_session=False))
        if n:
            evento(db, t.id, "FALLIDO", "Se agotaron los intentos (la ejecución se interrumpió)", "motor")
    if agotadas:
        db.commit()


def _con_lease(db: Session, tarea_id: int, token: str) -> ComandoAgente:
    t = db.get(ComandoAgente, tarea_id)
    if not t or t.version_motor != 1:
        raise ErrorMotor("Tarea inexistente", 404)
    if t.estado != "EN_EJECUCION" or not token or t.lease_token != token:
        raise ErrorMotor("El lease no es válido (vencido o tomado por otra ejecución)", 409)
    return t


def latido(db: Session, tarea_id: int, token: str) -> dict:
    t = _con_lease(db, tarea_id, token)
    t.lease_hasta = _ahora() + timedelta(seconds=LEASE_SEGUNDOS)
    db.commit()
    return {"cancelacion_solicitada": bool(t.cancelacion_solicitada)}


def completar(db: Session, tarea_id: int, token: str, resultado: dict, evidencia: Optional[dict] = None,
              costo_usd: float = 0) -> ComandoAgente:
    t = _con_lease(db, tarea_id, token)
    ahora = _ahora()
    t.costo_usd = (t.costo_usd or 0) + max(0.0, float(costo_usd or 0))
    t.resultado = resultado or {}
    t.evidencia = evidencia or {}
    t.respuesta = str((resultado or {}).get("texto", ""))[:4000]
    t.lease_token, t.lease_hasta, t.finalizado_at = None, None, ahora
    if t.cancelacion_solicitada:
        t.estado = "CANCELADO"
        evento(db, t.id, "CANCELADA", "Cancelada durante la ejecución: el resultado queda solo como registro", "motor")
    else:
        t.estado = "COMPLETADO"
        evento(db, t.id, "COMPLETADA", f"costo_usd={t.costo_usd:.6f}", f"worker:{t.worker}")
    db.commit()
    db.refresh(t)
    return t


def fallar(db: Session, tarea_id: int, token: str, error: str, reintentable: bool = True,
           costo_usd: float = 0) -> ComandoAgente:
    t = _con_lease(db, tarea_id, token)
    ahora = _ahora()
    t.costo_usd = (t.costo_usd or 0) + max(0.0, float(costo_usd or 0))
    t.error_detalle = (error or "")[:4000]
    t.lease_token, t.lease_hasta = None, None
    if t.cancelacion_solicitada:
        t.estado, t.finalizado_at = "CANCELADO", ahora
        evento(db, t.id, "CANCELADA", "Cancelada (la ejecución además falló)", "motor")
    elif reintentable and (t.intentos or 0) < (t.max_intentos or 1):
        espera = min(3600, 60 * 2 ** max(0, (t.intentos or 1) - 1))
        t.estado, t.proximo_intento = "ERROR", ahora + timedelta(seconds=espera)
        evento(db, t.id, "REINTENTO", f"{error[:300]} · próximo intento en {espera}s", f"worker:{t.worker}")
    else:
        t.estado, t.finalizado_at = "FALLIDO", ahora
        evento(db, t.id, "FALLIDO", error[:500], f"worker:{t.worker}")
    db.commit()
    db.refresh(t)
    return t


def cancelar(db: Session, tarea_id: int, actor: str) -> ComandoAgente:
    """Cancela la tarea y sus subtareas abiertas. Una en ejecución termina como CANCELADO."""
    t = db.get(ComandoAgente, tarea_id)
    if not t or t.version_motor != 1:
        raise ErrorMotor("Tarea inexistente", 404)
    pendientes = [t] + db.query(ComandoAgente).filter(
        or_(ComandoAgente.raiz_id == (t.raiz_id or t.id), ComandoAgente.padre_id == t.id)).all()
    vistos = set()
    for x in pendientes:
        if x.id in vistos or x.estado in ESTADOS_TERMINALES:
            continue
        if x.id != t.id and not _desciende_de(db, x, t.id):
            continue
        vistos.add(x.id)
        if x.estado == "EN_EJECUCION":
            x.cancelacion_solicitada = True
            evento(db, x.id, "CANCELACION_SOLICITADA", "", actor)
        else:
            x.estado, x.cancelacion_solicitada, x.finalizado_at = "CANCELADO", True, _ahora()
            evento(db, x.id, "CANCELADA", "", actor)
    db.commit()
    db.refresh(t)
    return t


def _desciende_de(db: Session, t: ComandoAgente, ancestro_id: int) -> bool:
    actual, pasos = t, 0
    while actual and actual.padre_id and pasos <= MAX_PROFUNDIDAD + 1:
        if actual.padre_id == ancestro_id:
            return True
        actual, pasos = db.get(ComandoAgente, actual.padre_id), pasos + 1
    return False


# ── Aprobaciones humanas ──────────────────────────────────────────────────────

def proponer_accion(db: Session, *, tarea_id: Optional[int], agente: str, tipo_accion: str, datos: dict,
                    motivo: str = "") -> AprobacionAccion:
    agente = normalizar_agente(agente)
    if agente not in AGENTES_EMPRESA:
        raise ErrorMotor("Agente inválido")
    if tarea_id is not None and not db.get(ComandoAgente, tarea_id):
        raise ErrorMotor("Tarea inexistente", 404)
    a = AprobacionAccion(tarea_id=tarea_id, agente=agente, tipo_accion=(tipo_accion or "")[:50],
                         datos=datos or {}, motivo=(motivo or "")[:2000], estado="PENDIENTE")
    db.add(a)
    db.flush()
    if tarea_id:
        evento(db, tarea_id, "ACCION_PROPUESTA", f"aprobación #{a.id}: {a.tipo_accion}", f"agente:{agente}")
    db.commit()
    db.refresh(a)
    return a


def decidir(db: Session, aprobacion_id: int, usuario, aprobar: bool, comentario: str = "") -> AprobacionAccion:
    if usuario is None or getattr(usuario, "es_agente_ia", False):
        raise ErrorMotor("Solo un administrador humano decide aprobaciones", 403)
    a = db.get(AprobacionAccion, aprobacion_id)
    if not a:
        raise ErrorMotor("Aprobación inexistente", 404)
    n = (db.query(AprobacionAccion).filter(AprobacionAccion.id == a.id, AprobacionAccion.estado == "PENDIENTE")
         .update({AprobacionAccion.estado: "APROBADA" if aprobar else "RECHAZADA",
                  AprobacionAccion.decidido_por_id: usuario.id, AprobacionAccion.decidido_at: _ahora(),
                  AprobacionAccion.comentario: (comentario or "")[:2000]}, synchronize_session=False))
    if n != 1:
        db.rollback()
        raise ErrorMotor("La aprobación ya fue decidida", 409)
    if a.tarea_id:
        evento(db, a.tarea_id, "APROBADA" if aprobar else "RECHAZADA",
               f"aprobación #{a.id}: {a.tipo_accion}", f"usuario:{usuario.id}")
    db.commit()
    db.refresh(a)
    return a


def reclamar_aprobada(db: Session) -> Optional[AprobacionAccion]:
    for a in db.query(AprobacionAccion).filter_by(estado="APROBADA").order_by(AprobacionAccion.id).limit(10).all():
        token = secrets.token_hex(16)
        n = (db.query(AprobacionAccion).filter(AprobacionAccion.id == a.id, AprobacionAccion.estado == "APROBADA")
             .update({AprobacionAccion.estado: "EJECUTANDO", AprobacionAccion.lease_token: token},
                     synchronize_session=False))
        if n == 1:
            db.commit()
            db.expire_all()
            return db.get(AprobacionAccion, a.id)
        db.rollback()
    return None


def resultado_aprobacion(db: Session, aprobacion_id: int, token: str, ok: bool, resultado: str) -> AprobacionAccion:
    a = db.get(AprobacionAccion, aprobacion_id)
    if not a or a.estado != "EJECUTANDO" or not token or a.lease_token != token:
        raise ErrorMotor("La aprobación no está en ejecución con ese token", 409)
    a.estado = "EJECUTADA" if ok else "FALLIDA"
    a.resultado = (resultado or "")[:4000]
    a.lease_token = None
    if a.tarea_id:
        evento(db, a.tarea_id, "ACCION_EJECUTADA" if ok else "ACCION_FALLIDA",
               f"aprobación #{a.id}: {a.resultado[:300]}", "motor")
    db.commit()
    db.refresh(a)
    return a


def aprobacion_dict(a: AprobacionAccion) -> dict:
    return {"id": a.id, "tarea_id": a.tarea_id, "agente": a.agente, "tipo_accion": a.tipo_accion,
            "datos": a.datos or {}, "motivo": a.motivo, "estado": a.estado,
            "decidido_por_id": a.decidido_por_id, "comentario": a.comentario, "resultado": a.resultado,
            "decidido_at": a.decidido_at.isoformat() if a.decidido_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None}
