"""
Políticas empresariales versionadas (capa 2 de instrucciones de los agentes).

Flujo: el propietario conversa con Máximo → Máximo PROPONE (PENDIENTE_APROBACION)
→ el propietario aprueba (ACTIVA) o rechaza → los agentes afectados la reciben
como capa 2 → se puede suspender o revertir (vuelve la versión anterior).

Límites duros (no los puede saltear una conversación):
- Una política nunca amplía permisos del backend: los permisos no salen del texto.
- No se aceptan políticas que cambien precios, descuentos, condiciones de
  financiación o crédito, comisiones, contratos o permisos: eso se decide en el
  CRM por las vías autorizadas, no por conversación.
- Valentín (asistente personal) no recibe políticas de la empresa.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import PoliticaEmpresarial, PoliticaEvento
from utils.motor_tareas import AGENTES_EMPRESA, DEPARTAMENTOS, ErrorMotor, normalizar_agente

ESTADOS = ["BORRADOR", "PROPUESTA", "PENDIENTE_APROBACION", "APROBADA", "EN_PRUEBAS", "ACTIVA", "SUSPENDIDA",
           "REVERTIDA", "RECHAZADA"]
_PROHIBIDO = re.compile(
    r"\b(descuent\w*|bonific\w*|rebaj\w*|cambi\w+ (el |los |de )?precio\w*|precio\w* (nuevo|distinto|especial)|"
    r"baj\w+ (el |los )?precio\w*|sub\w+ (el |los )?precio\w*|"
    r"(aprob|rechaz|otorg|conced)\w*\s+(el |la |los |las |un |una )?(cr[eé]dito|financiaci[oó]n|solicitud|plan)\w*|"
    r"tasa\w*|inter[eé]s|comisi[oó]n\w*|contrato\w*|permis\w+|"
    r"autoriz\w+ a (los )?agentes)\b", re.IGNORECASE)


def _ev(db: Session, p: PoliticaEmpresarial, de: str, a: str, actor: str, detalle: str = "") -> None:
    db.add(PoliticaEvento(politica_id=p.id, de=de or "", a=a, actor=actor[:60], detalle=(detalle or "")[:2000]))


def _slug(t: str) -> str:
    from utils.cotizacion import normalizar
    return re.sub(r"\s+", "-", normalizar(t))[:60] or "politica"


def proponer(db: Session, *, titulo: str, instruccion: str, autor: str, objetivo: str = "",
             departamento: str = "", agentes: Optional[list] = None, metrica_exito: str = "",
             codigo: Optional[str] = None) -> PoliticaEmpresarial:
    titulo, instruccion = (titulo or "").strip(), (instruccion or "").strip()
    if len(titulo) < 3 or len(instruccion) < 10:
        raise ErrorMotor("La política necesita título e instrucción operativa concretos")
    texto = f"{titulo} {objetivo} {instruccion}"
    m = _PROHIBIDO.search(texto)
    if m:
        raise ErrorMotor(f"Una política no puede cambiar precios, descuentos, condiciones de crédito, comisiones, "
                         f"contratos ni permisos ('{m.group(0)}'): eso se decide en el CRM por la vía autorizada", 422)
    dep = (departamento or "").strip().lower()
    if dep and dep not in DEPARTAMENTOS:
        raise ErrorMotor(f"Departamento inexistente ({', '.join(sorted(DEPARTAMENTOS))})")
    lista = sorted({normalizar_agente(a) for a in (agentes or [])} | (DEPARTAMENTOS.get(dep, set())))
    fuera = [a for a in lista if a not in AGENTES_EMPRESA]
    if fuera:
        raise ErrorMotor(f"Agentes fuera de la empresa: {', '.join(fuera)}")
    if not lista:
        raise ErrorMotor("Indicá departamento o agentes afectados")
    codigo = codigo or _slug(titulo)
    version = (max([x.version for x in db.query(PoliticaEmpresarial).filter_by(codigo=codigo)] or [0]) + 1)
    p = PoliticaEmpresarial(codigo=codigo, version=version, titulo=titulo[:200], objetivo=objetivo[:4000],
                            instruccion=instruccion[:6000], departamento=dep, agentes=lista,
                            metrica_exito=metrica_exito[:2000], estado="PENDIENTE_APROBACION", autor=autor[:60])
    db.add(p)
    db.flush()
    _ev(db, p, "", "PENDIENTE_APROBACION", autor, f"Propuesta v{version}")
    db.commit()
    db.refresh(p)
    return p


def decidir(db: Session, politica_id: int, usuario_id: int, aprobar: bool, comentario: str = "") -> PoliticaEmpresarial:
    p = db.get(PoliticaEmpresarial, politica_id)
    if not p:
        raise ErrorMotor("Política inexistente", 404)
    if p.estado != "PENDIENTE_APROBACION":
        raise ErrorMotor(f"La política está {p.estado}", 409)
    actor = f"usuario:{usuario_id}"
    if not aprobar:
        p.estado = "RECHAZADA"
        _ev(db, p, "PENDIENTE_APROBACION", "RECHAZADA", actor, comentario)
        db.commit()
        return p
    ahora = datetime.utcnow()
    for anterior in db.query(PoliticaEmpresarial).filter(PoliticaEmpresarial.codigo == p.codigo,
                                                         PoliticaEmpresarial.estado == "ACTIVA",
                                                         PoliticaEmpresarial.id != p.id):
        anterior.estado = "SUSPENDIDA"
        _ev(db, anterior, "ACTIVA", "SUSPENDIDA", actor, f"Reemplazada por v{p.version}")
    p.estado, p.aprobado_por_id, p.aprobado_at, p.aplicada_desde = "ACTIVA", usuario_id, ahora, ahora
    _ev(db, p, "PENDIENTE_APROBACION", "ACTIVA", actor, comentario or "Aprobada y activada")
    db.commit()
    return p


def suspender(db: Session, politica_id: int, usuario_id: int, motivo: str = "") -> PoliticaEmpresarial:
    p = db.get(PoliticaEmpresarial, politica_id)
    if not p or p.estado != "ACTIVA":
        raise ErrorMotor("Solo se suspende una política activa", 409)
    p.estado = "SUSPENDIDA"
    _ev(db, p, "ACTIVA", "SUSPENDIDA", f"usuario:{usuario_id}", motivo)
    db.commit()
    return p


def revertir(db: Session, politica_id: int, usuario_id: int, motivo: str = "") -> PoliticaEmpresarial:
    """Desactiva esta versión y reactiva la anterior aprobada del mismo código (si existe)."""
    p = db.get(PoliticaEmpresarial, politica_id)
    if not p or p.estado != "ACTIVA":
        raise ErrorMotor("Solo se revierte una política activa", 409)
    actor = f"usuario:{usuario_id}"
    p.estado = "REVERTIDA"
    _ev(db, p, "ACTIVA", "REVERTIDA", actor, motivo)
    previa = (db.query(PoliticaEmpresarial)
              .filter(PoliticaEmpresarial.codigo == p.codigo, PoliticaEmpresarial.version < p.version,
                      PoliticaEmpresarial.aprobado_at.isnot(None))
              .order_by(PoliticaEmpresarial.version.desc()).first())
    if previa:
        de = previa.estado
        previa.estado, previa.aplicada_desde = "ACTIVA", datetime.utcnow()
        _ev(db, previa, de, "ACTIVA", actor, f"Reactivada al revertir v{p.version}")
    db.commit()
    return p


def activas_para(db: Session, agente: str) -> list[PoliticaEmpresarial]:
    agente = normalizar_agente(agente)
    return [p for p in db.query(PoliticaEmpresarial).filter_by(estado="ACTIVA").order_by(PoliticaEmpresarial.id)
            if agente in (p.agentes or [])]


def politica_dict(p: PoliticaEmpresarial, eventos: Optional[list] = None) -> dict:
    d = {"id": p.id, "codigo": p.codigo, "version": p.version, "titulo": p.titulo, "objetivo": p.objetivo,
         "instruccion": p.instruccion, "departamento": p.departamento, "agentes": p.agentes or [],
         "metrica_exito": p.metrica_exito, "estado": p.estado, "autor": p.autor,
         "aprobado_at": p.aprobado_at.isoformat() if p.aprobado_at else None, "resultado": p.resultado,
         "created_at": p.created_at.isoformat() if p.created_at else None}
    if eventos is not None:
        d["eventos"] = [{"de": e.de, "a": e.a, "actor": e.actor, "detalle": e.detalle,
                         "ts": e.created_at.isoformat() if e.created_at else None} for e in eventos]
    return d
