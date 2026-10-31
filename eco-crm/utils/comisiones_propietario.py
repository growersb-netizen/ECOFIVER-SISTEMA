"""
Comisiones e indicadores personales del propietario (reglas confirmadas).

  CONTADO     10% del valor del producto (precio_final; no incluye flete ni
              instalación). Se GENERA al confirmarse la entrega. Antes es
              PROYECTADA (se calcula, no se guarda).
  FINANCIADO  100% de las dos cuotas iniciales (2 × valor de cuota del plan
              formalizado). Se GENERA con Admisión aprobada + suscripción
              formalizada + dos cuotas iniciales pagas (confirmadas por una persona).

GENERADA → COBRADA (con evidencia, por una persona) | ANULADA (con motivo).
Clave única por operación: reprocesar un evento nunca duplica.
Separado de la contabilidad de la cooperativa y de las comisiones de socios.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import (ComisionPropietario, ExpedienteFinanciacion, GastoPublicitario, ObjetivoEconomico,
                             VentaContado, VentaFinanciada)
from utils.motor_tareas import ErrorMotor

PCT_CONTADO = 0.10
CUOTAS_FINANCIADO = 2
INDICADORES = {"facturacion", "comisiones_generadas", "comisiones_cobradas", "resultado_personal"}


def _ahora() -> datetime:
    return datetime.utcnow()


def _n(dt: Optional[datetime]) -> Optional[datetime]:
    """UTC sin zona (PostgreSQL devuelve TIMESTAMPTZ con zona; SQLite sin zona)."""
    if dt is None:
        return None
    from datetime import timezone
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _crear_si_no_existe(db: Session, clave: str, **campos) -> ComisionPropietario:
    existente = db.query(ComisionPropietario).filter_by(clave=clave).first()
    if existente:
        return existente
    c = ComisionPropietario(clave=clave, estado="GENERADA", **campos)
    db.add(c)
    try:
        db.commit()
    except Exception:            # carrera: otro proceso la creó primero (clave única)
        db.rollback()
        return db.query(ComisionPropietario).filter_by(clave=clave).one()
    db.refresh(c)
    return c


def generar_contado(db: Session, venta: VentaContado) -> Optional[ComisionPropietario]:
    if venta.entrega_confirmada_at is None or venta.estado == "CANCELADO":
        return None
    base = float(venta.precio_final or 0)
    if base <= 0:
        return None
    return _crear_si_no_existe(
        db, f"contado:{venta.id}", tipo="CONTADO", venta_contado_id=venta.id, producto=venta.producto or "",
        base_calculo=base, regla="10% del valor del producto", monto=round(base * PCT_CONTADO, 2),
        generada_at=venta.entrega_confirmada_at, canal=_canal_venta(venta))


def generar_financiada(db: Session, exp: ExpedienteFinanciacion) -> Optional[ComisionPropietario]:
    if exp.estado != "CIERRE_HUMANO_CONFIRMADO" or not exp.venta_financiada_id or not exp.cuotas_iniciales_confirmadas_at:
        return None
    vf = db.get(VentaFinanciada, exp.venta_financiada_id)
    cuota = float(vf.valor_cuota or 0) if vf else 0
    if cuota <= 0:
        raise ErrorMotor("La venta financiada no tiene valor de cuota contractual: no se puede calcular la comisión", 409)
    return _crear_si_no_existe(
        db, f"financiada:{vf.id}", tipo="FINANCIADO", venta_financiada_id=vf.id, expediente_id=exp.id,
        producto=vf.producto or exp.producto, base_calculo=cuota, regla="100% de las 2 cuotas iniciales",
        monto=round(cuota * CUOTAS_FINANCIADO, 2), generada_at=exp.cuotas_iniciales_confirmadas_at,
        canal=None)


def _canal_venta(v: VentaContado) -> str:
    if v.aliado_codigo:
        return "socio"
    if (v.cerrada_por or "").startswith("agente:"):
        return "agentes_ia"
    return "directo"


def marcar_cobrada(db: Session, comision_id: int, usuario_id: int, evidencia: str,
                   fecha: Optional[datetime] = None) -> ComisionPropietario:
    c = db.get(ComisionPropietario, comision_id)
    if not c:
        raise ErrorMotor("Comisión inexistente", 404)
    if c.estado != "GENERADA":
        raise ErrorMotor(f"La comisión está {c.estado}", 409)
    if len((evidencia or "").strip()) < 5:
        raise ErrorMotor("Indicá la evidencia del cobro de la comisión", 400)
    c.estado, c.cobrada_at, c.cobrada_evidencia, c.actualizada_por_id = "COBRADA", fecha or _ahora(), evidencia.strip()[:2000], usuario_id
    db.commit()
    return c


def anular(db: Session, comision_id: int, usuario_id: int, motivo: str) -> ComisionPropietario:
    c = db.get(ComisionPropietario, comision_id)
    if not c:
        raise ErrorMotor("Comisión inexistente", 404)
    if c.estado == "ANULADA":
        return c
    if len((motivo or "").strip()) < 5:
        raise ErrorMotor("Indicá el motivo de la anulación", 400)
    c.estado, c.anulada_motivo, c.actualizada_por_id = "ANULADA", motivo.strip()[:2000], usuario_id
    db.commit()
    return c


def comision_dict(c: ComisionPropietario) -> dict:
    return {"id": c.id, "tipo": c.tipo, "producto": c.producto, "venta_contado_id": c.venta_contado_id,
            "venta_financiada_id": c.venta_financiada_id, "expediente_id": c.expediente_id,
            "base_calculo": c.base_calculo, "regla": c.regla, "monto": c.monto, "estado": c.estado,
            "generada_at": c.generada_at.isoformat() if c.generada_at else None,
            "cobrada_at": c.cobrada_at.isoformat() if c.cobrada_at else None,
            "cobrada_evidencia": c.cobrada_evidencia, "anulada_motivo": c.anulada_motivo, "canal": c.canal}


# ── Objetivos versionados y gastos ────────────────────────────────────────────

def fijar_objetivo(db: Session, *, periodo: str, indicador: str, valor: float, usuario_id: int,
                   producto: str = "", canal: str = "", origen: str = "panel", nota: str = "") -> ObjetivoEconomico:
    if indicador not in INDICADORES:
        raise ErrorMotor(f"Indicador inválido ({', '.join(sorted(INDICADORES))})")
    try:
        datetime.strptime(periodo, "%Y-%m")
    except ValueError:
        raise ErrorMotor("Período inválido (YYYY-MM)")
    if valor is None or float(valor) < 0:
        raise ErrorMotor("Valor inválido")
    anteriores = db.query(ObjetivoEconomico).filter_by(periodo=periodo, indicador=indicador, producto=producto or "",
                                                       canal=canal or "").all()
    version = max([o.version for o in anteriores] or [0]) + 1
    for o in anteriores:
        o.vigente = False
    o = ObjetivoEconomico(periodo=periodo, indicador=indicador, producto=producto or "", canal=canal or "",
                          valor=float(valor), version=version, vigente=True, origen=origen[:40],
                          nota=(nota or "")[:2000], autorizado_por_id=usuario_id)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def registrar_gasto(db: Session, *, tipo: str, fecha: date, monto: float, usuario_id: int, campana: str = "",
                    producto: str = "", canal: str = "", nota: str = "") -> GastoPublicitario:
    tipo = (tipo or "").upper()
    if tipo not in ("PRESUPUESTO", "GASTO"):
        raise ErrorMotor("tipo debe ser PRESUPUESTO o GASTO")
    if monto is None or float(monto) <= 0:
        raise ErrorMotor("El monto debe ser mayor a cero")
    g = GastoPublicitario(tipo=tipo, fecha=fecha, monto=float(monto), campana=campana[:150], producto=producto[:20],
                          canal=canal[:40], nota=nota[:2000], registrado_por_id=usuario_id)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ── Panel económico personal ──────────────────────────────────────────────────

def _rango(periodo: str) -> tuple[datetime, datetime, int]:
    y, m = (int(x) for x in periodo.split("-"))
    dias = calendar.monthrange(y, m)[1]
    desde = datetime(y, m, 1)
    hasta = datetime(y + (m == 12), (m % 12) + 1, 1)
    return desde, hasta, dias


def panel(db: Session, periodo: str, hoy: Optional[datetime] = None) -> dict:
    """Indicadores del propietario para un mes. Cada cifra trae su procedencia; nada estimado se presenta como real."""
    try:
        desde, hasta, dias = _rango(periodo)
    except Exception:
        raise ErrorMotor("Período inválido (YYYY-MM)")
    hoy = _n(hoy) or _ahora()
    faltantes = []

    com = db.query(ComisionPropietario).filter(ComisionPropietario.estado != "ANULADA").all()
    generadas_mes = [c for c in com if desde <= _n(c.generada_at) < hasta]
    cobradas_mes = [c for c in com if c.estado == "COBRADA" and c.cobrada_at and desde <= _n(c.cobrada_at) < hasta]
    pendientes = [c for c in com if c.estado == "GENERADA"]

    entregadas = db.query(VentaContado).filter(VentaContado.entrega_confirmada_at >= desde,
                                               VentaContado.entrega_confirmada_at < hasta,
                                               VentaContado.estado != "CANCELADO").all()
    fin_cerradas = [e for e in db.query(ExpedienteFinanciacion).filter_by(estado="CIERRE_HUMANO_CONFIRMADO").all()
                    if e.cuotas_iniciales_confirmadas_at and desde <= _n(e.cuotas_iniciales_confirmadas_at) < hasta]
    facturacion_contado = sum(float(v.precio_final or 0) for v in entregadas)
    facturacion_fin = 0.0
    for e in fin_cerradas:
        vf = db.get(VentaFinanciada, e.venta_financiada_id) if e.venta_financiada_id else None
        facturacion_fin += float(vf.precio_total or 0) if vf else 0

    # Proyectadas: operaciones abiertas que todavía no generan comisión
    abiertas_contado = db.query(VentaContado).filter(VentaContado.entrega_confirmada_at.is_(None),
                                                     VentaContado.estado != "CANCELADO",
                                                     VentaContado.circuito_estado.isnot(None)).all()
    proy_contado = sum(round(float(v.precio_final or 0) * PCT_CONTADO, 2) for v in abiertas_contado)
    sin_precio = [v.id for v in abiertas_contado if not v.precio_final]
    if sin_precio:
        faltantes.append(f"{len(sin_precio)} venta(s) de contado abiertas sin precio: no suman a la proyección")
    exp_abiertos = db.query(ExpedienteFinanciacion).filter(
        ExpedienteFinanciacion.estado.in_(["APROBADO_POR_ADMISION", "CIERRE_HUMANO_CONFIRMADO"]),
        ExpedienteFinanciacion.cuotas_iniciales_confirmadas_at.is_(None)).all()
    proy_fin, sin_cuota = 0.0, 0
    for e in exp_abiertos:
        vf = db.get(VentaFinanciada, e.venta_financiada_id) if e.venta_financiada_id else None
        cuota = float(vf.valor_cuota or 0) if vf else float(e.valor_cuota_estimado or 0)
        if cuota > 0:
            proy_fin += cuota * CUOTAS_FINANCIADO
        else:
            sin_cuota += 1
    if sin_cuota:
        faltantes.append(f"{sin_cuota} expediente(s) aprobados sin valor de cuota: no suman a la proyección")

    gastos = db.query(GastoPublicitario).filter(GastoPublicitario.fecha >= desde.date(),
                                                GastoPublicitario.fecha < hasta.date()).all()
    gasto_real = sum(g.monto for g in gastos if g.tipo == "GASTO")
    presupuesto = sum(g.monto for g in gastos if g.tipo == "PRESUPUESTO")
    if not gastos:
        faltantes.append("Sin gastos publicitarios cargados en el período: el resultado personal puede estar sobreestimado")

    generadas_total = round(sum(c.monto for c in generadas_mes), 2)
    cobradas_total = round(sum(c.monto for c in cobradas_mes), 2)
    objetivos = {o.indicador: o for o in db.query(ObjetivoEconomico).filter_by(periodo=periodo, vigente=True,
                                                                                producto="", canal="").all()}
    valores = {"facturacion": facturacion_contado + facturacion_fin, "comisiones_generadas": generadas_total,
               "comisiones_cobradas": cobradas_total, "resultado_personal": round(cobradas_total - gasto_real, 2)}

    en_curso = desde <= hoy < hasta
    dia = hoy.day if en_curso else dias
    proyeccion_cierre = round(generadas_total / dia * dias, 2) if en_curso and dia else generadas_total

    return {
        "periodo": periodo,
        "facturacion_comercial": {"total": round(valores["facturacion"], 2), "contado_entregado": round(facturacion_contado, 2),
                                  "financiado_suscripto_y_cobrado": round(facturacion_fin, 2),
                                  "fuente": "ventas de contado con entrega confirmada + planes con cierre de Admisión y 2 cuotas pagas"},
        "comisiones_generadas": {"total": generadas_total, "cantidad": len(generadas_mes),
                                 "fuente": "comisiones_propietario por fecha de generación"},
        "comisiones_cobradas": {"total": cobradas_total, "cantidad": len(cobradas_mes),
                                "fuente": "comisiones marcadas COBRADA con evidencia"},
        "comisiones_pendientes": {"total": round(sum(c.monto for c in pendientes), 2), "cantidad": len(pendientes),
                                  "fuente": "generadas aún no cobradas (todos los períodos)"},
        "comisiones_proyectadas": {"total": round(proy_contado + proy_fin, 2), "contado": round(proy_contado, 2),
                                   "financiado": round(proy_fin, 2),
                                   "fuente": "PROYECCIÓN: ventas cerradas sin entrega y planes aprobados sin 2 cuotas pagas"},
        "inversion_publicitaria": {"gasto_real": round(gasto_real, 2), "presupuesto": round(presupuesto, 2),
                                   "fuente": "gastos_publicitarios del período"},
        "resultado_personal": {"total": valores["resultado_personal"],
                               "fuente": "comisiones cobradas − gasto publicitario real"},
        "objetivos": {k: {"valor": o.valor, "version": o.version,
                          "cumplimiento_pct": round(100 * valores[k] / o.valor, 1) if o.valor else None}
                      for k, o in objetivos.items()},
        "proyeccion_cierre_mes": {"comisiones_generadas": proyeccion_cierre,
                                  "fuente": "ESTIMACIÓN lineal según días transcurridos"},
        "datos_faltantes": faltantes,
    }
