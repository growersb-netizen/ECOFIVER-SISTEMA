"""
Control empresarial de agentes (Fase 2).

- Estado ADMINISTRATIVO (lo decide un administrador): ACTIVO | PAUSADO | DESACTIVADO,
  por agente o por departamento. Distinto de la ACTIVIDAD REAL (qué está
  haciendo), que se calcula desde las tareas del motor.
- Horario aprobado para salientes comerciales: lunes a sábado 09:00–21:00,
  America/Argentina/Buenos_Aires. El WhatsApp entrante se atiende 24/7.
- Guardias: ventanas autorizadas por un administrador para operar salientes
  fuera de horario (todos, un departamento o un agente), con límite de duración.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import AgenteControl, AgenteControlEvento, ComandoAgente, GuardiaOperativa
from utils.motor_tareas import AGENTES_EMPRESA, DEPARTAMENTOS, ErrorMotor, normalizar_agente

ESTADOS = ("ACTIVO", "PAUSADO", "DESACTIVADO")
DIAS_HABILES = {0, 1, 2, 3, 4, 5}      # lunes a sábado
HORA_DESDE, HORA_HASTA = 9, 21
MAX_GUARDIA_HORAS = 72

try:
    from zoneinfo import ZoneInfo
    TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:                       # sin base de zonas: Argentina no usa horario de verano
    TZ_AR = timezone(timedelta(hours=-3))

DEPARTAMENTO_DE = {a: d for d, agentes in DEPARTAMENTOS.items() for a in agentes}


def _utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _ahora_utc() -> datetime:
    return datetime.utcnow()


# ── Estados ───────────────────────────────────────────────────────────────────

def estados(db: Session) -> dict[str, dict]:
    filas = {f.agente: f for f in db.query(AgenteControl).all()}
    out = {}
    for a in sorted(AGENTES_EMPRESA):
        f = filas.get(a)
        out[a] = {"agente": a, "departamento": DEPARTAMENTO_DE.get(a, ""),
                  "estado": f.estado if f else "ACTIVO", "motivo": (f.motivo if f else "") or "",
                  "actualizado_at": f.actualizado_at.isoformat() if f and f.actualizado_at else None}
    return out


def cambiar_estado(db: Session, agente: str, estado: str, motivo: str, usuario_id: Optional[int],
                   commit: bool = True) -> dict:
    agente = normalizar_agente(agente)
    estado = (estado or "").upper()
    if agente not in AGENTES_EMPRESA:
        raise ErrorMotor(f"'{agente}' no es un agente de la empresa", 404)
    if estado not in ESTADOS:
        raise ErrorMotor(f"Estado inválido (usar {', '.join(ESTADOS)})")
    motivo = (motivo or "").strip()
    if estado != "ACTIVO" and len(motivo) < 3:
        raise ErrorMotor("Indicá el motivo de la pausa o desactivación")
    fila = db.get(AgenteControl, agente)
    anterior = fila.estado if fila else "ACTIVO"
    if fila is None:
        fila = AgenteControl(agente=agente)
        db.add(fila)
    fila.estado, fila.motivo, fila.actualizado_por_id = estado, motivo[:2000], usuario_id
    fila.actualizado_at = _ahora_utc()
    db.add(AgenteControlEvento(agente=agente, estado_anterior=anterior, estado_nuevo=estado,
                               motivo=motivo[:2000], usuario_id=usuario_id))
    if commit:
        db.commit()
    return {"agente": agente, "estado_anterior": anterior, "estado": estado}


def cambiar_departamento(db: Session, departamento: str, estado: str, motivo: str,
                         usuario_id: Optional[int]) -> list[dict]:
    dep = (departamento or "").strip().lower()
    if dep not in DEPARTAMENTOS:
        raise ErrorMotor(f"Departamento inexistente (usar {', '.join(sorted(DEPARTAMENTOS))})", 404)
    cambios = [cambiar_estado(db, a, estado, f"[departamento {dep}] {motivo or ''}".strip(), usuario_id, commit=False)
               for a in sorted(DEPARTAMENTOS[dep])]
    db.commit()
    return cambios


def activos(db: Session) -> list[str]:
    return [a for a, e in estados(db).items() if e["estado"] == "ACTIVO"]


# ── Horario y guardias ────────────────────────────────────────────────────────

def en_horario(ahora_utc: Optional[datetime] = None) -> bool:
    ahora = (ahora_utc or _ahora_utc()).replace(tzinfo=timezone.utc).astimezone(TZ_AR)
    return ahora.weekday() in DIAS_HABILES and HORA_DESDE <= ahora.hour < HORA_HASTA


def guardias_activas(db: Session, ahora_utc: Optional[datetime] = None) -> list[GuardiaOperativa]:
    ahora = ahora_utc or _ahora_utc()
    return (db.query(GuardiaOperativa)
            .filter(GuardiaOperativa.activa == True, GuardiaOperativa.desde <= ahora,  # noqa: E712
                    GuardiaOperativa.hasta > ahora).all())


def _cubre(g: GuardiaOperativa, agente: str) -> bool:
    return g.alcance in ("todos", f"agente:{agente}", f"dep:{DEPARTAMENTO_DE.get(agente, '')}")


def salida_permitida(db: Session, agente: str, ahora_utc: Optional[datetime] = None) -> tuple[bool, str]:
    """¿Puede este agente iniciar un contacto comercial saliente ahora?"""
    agente = normalizar_agente(agente)
    e = estados(db).get(agente)
    if not e:
        return False, "agente fuera de la empresa"
    if e["estado"] != "ACTIVO":
        return False, f"agente {e['estado'].lower()}"
    if en_horario(ahora_utc):
        return True, "dentro del horario"
    if any(_cubre(g, agente) for g in guardias_activas(db, ahora_utc)):
        return True, "guardia autorizada"
    return False, "fuera del horario (lunes a sábado 09–21)"


def crear_guardia(db: Session, alcance: str, desde: datetime, hasta: datetime, motivo: str,
                  usuario_id: Optional[int]) -> GuardiaOperativa:
    alcance = (alcance or "").strip().lower()
    valido = alcance == "todos" or (alcance.startswith("dep:") and alcance[4:] in DEPARTAMENTOS) or \
        (alcance.startswith("agente:") and normalizar_agente(alcance[7:]) in AGENTES_EMPRESA)
    if not valido:
        raise ErrorMotor("Alcance inválido: 'todos', 'dep:<departamento>' o 'agente:<nombre>'")
    if alcance.startswith("agente:"):
        alcance = "agente:" + normalizar_agente(alcance[7:])
    desde, hasta = _utc_naive(desde), _utc_naive(hasta)
    if hasta <= desde:
        raise ErrorMotor("La guardia debe terminar después de empezar")
    if hasta - desde > timedelta(hours=MAX_GUARDIA_HORAS):
        raise ErrorMotor(f"Una guardia dura como máximo {MAX_GUARDIA_HORAS} h")
    if len((motivo or "").strip()) < 3:
        raise ErrorMotor("Indicá el motivo de la guardia")
    g = GuardiaOperativa(alcance=alcance, desde=desde, hasta=hasta, motivo=motivo.strip()[:2000],
                         creado_por_id=usuario_id, activa=True)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def guardia_dict(g: GuardiaOperativa) -> dict:
    return {"id": g.id, "alcance": g.alcance, "desde": g.desde.isoformat() if g.desde else None,
            "hasta": g.hasta.isoformat() if g.hasta else None, "motivo": g.motivo, "activa": bool(g.activa),
            "creado_por_id": g.creado_por_id}


# ── Actividad real (desde el motor; no desde el estado administrativo) ────────

def actividad(db: Session, ahora_utc: Optional[datetime] = None) -> dict[str, dict]:
    ahora = ahora_utc or _ahora_utc()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    out = {a: {"tarea_en_curso": None, "pendientes": 0, "completadas_hoy": 0, "fallidas_hoy": 0,
               "ultima_actividad": None} for a in AGENTES_EMPRESA}
    filas = (db.query(ComandoAgente).filter(ComandoAgente.version_motor == 1)
             .filter((ComandoAgente.estado.in_(["PENDIENTE", "ERROR", "EN_EJECUCION", "ESPERANDO_APROBACION"]))
                     | (ComandoAgente.finalizado_at >= inicio_dia)).all())
    for t in filas:
        a = out.get(t.agente_destino)
        if a is None:
            continue
        if t.estado == "EN_EJECUCION" and (t.lease_hasta is None or t.lease_hasta > ahora):
            a["tarea_en_curso"] = {"id": t.id, "titulo": t.titulo, "desde": t.iniciado_at.isoformat() if t.iniciado_at else None}
        elif t.estado in ("PENDIENTE", "ERROR"):
            a["pendientes"] += 1
        elif t.estado == "COMPLETADO":
            a["completadas_hoy"] += 1
        elif t.estado == "FALLIDO":
            a["fallidas_hoy"] += 1
        ts = t.finalizado_at or t.iniciado_at
        if ts and (a["ultima_actividad"] is None or ts.isoformat() > a["ultima_actividad"]):
            a["ultima_actividad"] = ts.isoformat()
    return out
