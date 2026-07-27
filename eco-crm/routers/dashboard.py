from datetime import datetime, timedelta
import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database.database import get_db
from database.models import (
    Lead, Videollamada, VentaContado, VentaFinanciada,
    OrdenFabricaPiscina, OrdenFabricaModulo, Empleado, Asistencia,
    LiquidacionSemanal, Notificacion, Reclamo, Usuario, Contrato
)
from routers.auth import require_auth, get_user_roles, require_auth_or_apikey
from routers.ventas_financiadas import dias_atraso

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    # B1: ADMINISTRACION sin otros roles → va directo a la pantalla de asistencia
    solo_admin = set(roles) <= {"ADMINISTRACION"}
    if solo_admin:
        return RedirectResponse(url="/personal?tab=asistencia", status_code=302)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


# ─── NOTE: get_dashboard (ruta dinámica {rol}) está definida al FINAL del archivo ──
# Las rutas específicas /ranking /alertas /stock-oferta deben registrarse PRIMERO
# para que Starlette las matchee antes que el patrón dinámico /{rol}.


# get_dashboard placeholder — la función real está abajo
async def _get_dashboard_impl(
    rol: str,
    db: Session,
    current_user: "Usuario",
):
    roles = get_user_roles(current_user)
    hoy = datetime.now()
    inicio_hoy = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_hoy = hoy.replace(hour=23, minute=59, second=59, microsecond=999999)
    ayer = hoy - timedelta(days=1)
    inicio_ayer = ayer.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_ayer = ayer.replace(hour=23, minute=59, second=59, microsecond=999999)
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio_semana = (hoy - timedelta(days=hoy.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    if "ADMIN" in roles or rol == "ADMIN":
        leads_hoy = db.query(Lead).filter(Lead.created_at >= inicio_hoy).count()
        leads_ayer = db.query(Lead).filter(
            Lead.created_at >= inicio_ayer, Lead.created_at <= fin_ayer
        ).count()

        vl_hoy = db.query(Videollamada).filter(
            Videollamada.fecha_hora >= inicio_hoy, Videollamada.fecha_hora <= fin_hoy
        ).count()

        ventas_mes = db.query(VentaContado).filter(VentaContado.created_at >= inicio_mes).count()
        ventas_mes += db.query(VentaFinanciada).filter(VentaFinanciada.created_at >= inicio_mes).count()

        ventas_fin = db.query(VentaFinanciada).filter(
            VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
        ).all()
        cuotas_vencidas = sum(1 for v in ventas_fin if dias_atraso(v) > 0)
        monto_vencido = sum(v.valor_cuota or 0 for v in ventas_fin if dias_atraso(v) > 0)

        ordenes_piscinas = db.query(OrdenFabricaPiscina).filter(
            OrdenFabricaPiscina.estado.in_(["EN_ESPERA", "EN_PROCESO"])
        ).count()
        ordenes_modulos = db.query(OrdenFabricaModulo).filter(
            OrdenFabricaModulo.estado.in_(["EN_ESPERA", "EN_PROCESO"])
        ).count()

        presentes_hoy = db.query(Asistencia).filter(
            Asistencia.fecha >= inicio_hoy,
            Asistencia.tipo == "PRESENTE"
        ).count()

        liquidacion_pendiente = db.query(LiquidacionSemanal).filter(
            LiquidacionSemanal.pagado == False
        ).count()

        # Leads por estado esta semana
        leads_semana = db.query(Lead).filter(Lead.created_at >= inicio_semana).all()
        leads_por_estado = {}
        for l in leads_semana:
            leads_por_estado[l.estado] = leads_por_estado.get(l.estado, 0) + 1

        leads_sin_contactar = db.query(Lead).filter(Lead.estado.in_(["NUEVO", "INTENTADO"])).count()

        ventas_semana = db.query(VentaContado).filter(VentaContado.created_at >= inicio_semana).count()
        ventas_semana += db.query(VentaFinanciada).filter(VentaFinanciada.created_at >= inicio_semana).count()

        ventas_dia = db.query(VentaContado).filter(VentaContado.created_at >= inicio_hoy).count()
        ventas_dia += db.query(VentaFinanciada).filter(VentaFinanciada.created_at >= inicio_hoy).count()

        reclamos_abiertos = db.query(Reclamo).filter(Reclamo.estado.in_(["NUEVO", "EN_GESTION"])).count()

        return {
            "leads_hoy": leads_hoy,
            "leads_ayer": leads_ayer,
            "videollamadas_hoy": vl_hoy,
            "ventas_mes": ventas_mes,
            "cuotas_vencidas": cuotas_vencidas,
            "monto_vencido": monto_vencido,
            "ordenes_fabrica": ordenes_piscinas + ordenes_modulos,
            "presentes_hoy": presentes_hoy,
            "liquidacion_pendiente": liquidacion_pendiente,
            "leads_por_estado": leads_por_estado,
            "leads_sin_contactar": leads_sin_contactar,
            "ventas_semana": ventas_semana,
            "ventas_dia": ventas_dia,
            "reclamos_abiertos": reclamos_abiertos,
        }

    elif "ASESOR_APERTURA" in roles:
        mis_leads = db.query(Lead).filter(Lead.asesor_apertura_id == current_user.id).all()
        por_estado = {}
        for l in mis_leads:
            por_estado[l.estado] = por_estado.get(l.estado, 0) + 1

        mis_vl_hoy = db.query(Videollamada).filter(
            Videollamada.asesor_apertura_id == current_user.id,
            Videollamada.fecha_hora >= inicio_hoy,
            Videollamada.fecha_hora <= fin_hoy
        ).count()

        mis_cierres_mes = db.query(VentaContado).filter(
            VentaContado.vendedor_id == current_user.id,
            VentaContado.created_at >= inicio_mes
        ).count()
        mis_cierres_mes += db.query(VentaFinanciada).filter(
            VentaFinanciada.asesor_apertura_id == current_user.id,
            VentaFinanciada.created_at >= inicio_mes
        ).count()

        # Sin contactar +48hs
        limite_48 = hoy - timedelta(hours=48)
        sin_contactar = db.query(Lead).filter(
            Lead.asesor_apertura_id == current_user.id,
            Lead.estado == "NUEVO",
            Lead.created_at <= limite_48
        ).count()

        # Ventas canceladas que necesitan gestión del asesor
        ventas_canceladas = db.query(VentaContado).filter(
            VentaContado.vendedor_id == current_user.id,
            VentaContado.estado == "CANCELADA",
        ).count()

        return {
            "mis_leads_activos": len(mis_leads),
            "por_estado": por_estado,
            "videollamadas_hoy": mis_vl_hoy,
            "cierres_mes": mis_cierres_mes,
            "sin_contactar_48h": sin_contactar,
            "ventas_canceladas": ventas_canceladas,
        }

    elif "SUPERVISOR_CIERRE" in roles:
        sin_asignar = db.query(Videollamada).filter(
            Videollamada.supervisor_cierre_id == None,
            Videollamada.estado == "AGENDADA"
        ).count()

        mis_vl_hoy = db.query(Videollamada).filter(
            Videollamada.supervisor_cierre_id == current_user.id,
            Videollamada.fecha_hora >= inicio_hoy,
            Videollamada.fecha_hora <= fin_hoy
        ).count()

        mis_cierres_mes = db.query(VentaFinanciada).filter(
            VentaFinanciada.supervisor_cierre_id == current_user.id,
            VentaFinanciada.created_at >= inicio_mes
        ).count()

        return {
            "videollamadas_sin_asignar": sin_asignar,
            "mis_videollamadas_hoy": mis_vl_hoy,
            "cierres_mes": mis_cierres_mes,
        }

    elif "COORDINADOR_OPERATIVO" in roles:
        manana = hoy + timedelta(days=1)
        inicio_manana = manana.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_manana = manana.replace(hour=23, minute=59, second=59, microsecond=999999)

        from database.models import Entrega
        entregas_hoy = db.query(Entrega).filter(
            Entrega.fecha_instalacion >= inicio_hoy,
            Entrega.fecha_instalacion <= fin_hoy
        ).count()
        entregas_manana = db.query(Entrega).filter(
            Entrega.fecha_instalacion >= inicio_manana,
            Entrega.fecha_instalacion <= fin_manana
        ).count()

        ordenes_terminadas = db.query(OrdenFabricaPiscina).filter(
            OrdenFabricaPiscina.estado == "TERMINADA"
        ).count()
        ordenes_terminadas += db.query(OrdenFabricaModulo).filter(
            OrdenFabricaModulo.estado == "TERMINADA"
        ).count()

        reclamos_abiertos = db.query(Reclamo).filter(
            Reclamo.estado.in_(["NUEVO", "EN_GESTION"])
        ).count()

        contratos_pendientes = db.query(Contrato).filter(
            Contrato.estado.in_(["BORRADOR", "ENVIADO"])
        ).count()

        return {
            "instalaciones_hoy": entregas_hoy,
            "instalaciones_manana": entregas_manana,
            "ordenes_terminadas_sin_coordinar": ordenes_terminadas,
            "reclamos_abiertos": reclamos_abiertos,
            "contratos_pendientes": contratos_pendientes,
        }

    elif "COBRANZAS" in roles:
        ventas_fin = db.query(VentaFinanciada).filter(
            VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
        ).all()

        from routers.ventas_financiadas import calcular_proximo_vencimiento
        vencen_hoy = sum(1 for v in ventas_fin
                         if calcular_proximo_vencimiento(v) and
                         calcular_proximo_vencimiento(v).date() == hoy.date())
        vencidas = sum(1 for v in ventas_fin if dias_atraso(v) > 0)

        from database.models import GestionCobranza
        gestiones_hoy = db.query(GestionCobranza).filter(
            GestionCobranza.fecha_contacto >= inicio_hoy
        ).count()

        pagos_mes = db.query(GestionCobranza).filter(
            GestionCobranza.resultado == "PAGO",
            GestionCobranza.fecha_contacto >= inicio_mes
        ).count()

        return {
            "vencen_hoy": vencen_hoy,
            "vencidas": vencidas,
            "gestiones_hoy": gestiones_hoy,
            "pagos_mes": pagos_mes,
        }

    elif "FABRICA" in roles or "ADMINISTRACION" in roles:
        ordenes_proceso_piscinas = db.query(OrdenFabricaPiscina).filter(
            OrdenFabricaPiscina.estado.in_(["EN_ESPERA", "EN_PROCESO"])
        ).count()
        ordenes_proceso_modulos = db.query(OrdenFabricaModulo).filter(
            OrdenFabricaModulo.estado.in_(["EN_ESPERA", "EN_PROCESO"])
        ).count()

        from database.models import StockPiscina, StockPanel
        stock_critico_piscinas = db.query(StockPiscina).filter(StockPiscina.cantidad <= 1).count()
        stock_critico_paneles = db.query(StockPanel).filter(
            StockPanel.cantidad <= StockPanel.stock_minimo
        ).count()

        presentes_hoy = db.query(Asistencia).filter(
            Asistencia.fecha >= inicio_hoy,
            Asistencia.tipo == "PRESENTE"
        ).count()

        es_sabado = hoy.weekday() == 5
        liq_pendiente = db.query(LiquidacionSemanal).filter(
            LiquidacionSemanal.pagado == False
        ).count() if es_sabado else 0

        return {
            "ordenes_en_proceso": ordenes_proceso_piscinas + ordenes_proceso_modulos,
            "stock_critico": stock_critico_piscinas + stock_critico_paneles,
            "presentes_hoy": presentes_hoy,
            "liquidacion_pendiente": liq_pendiente,
            "es_sabado": es_sabado,
        }

    return {}


@router.get("/api/notificaciones")
async def get_notificaciones(
    no_leidas: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    q = db.query(Notificacion).filter(Notificacion.usuario_id == current_user.id)
    if no_leidas:
        q = q.filter(Notificacion.leida == False)
    notifs = q.order_by(Notificacion.created_at.desc()).limit(20).all()
    return [{
        "id": n.id,
        "titulo": n.titulo,
        "mensaje": n.mensaje,
        "leida": n.leida,
        "tipo": n.tipo,
        "created_at": n.created_at.isoformat() if n.created_at else "",
    } for n in notifs]


@router.post("/api/notificaciones/{notif_id}/leer")
async def marcar_leida(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    n = db.query(Notificacion).filter(
        Notificacion.id == notif_id,
        Notificacion.usuario_id == current_user.id
    ).first()
    if n:
        n.leida = True
        db.commit()
    return {"ok": True}


@router.post("/api/notificaciones/leer-todas")
async def marcar_todas_leidas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    db.query(Notificacion).filter(
        Notificacion.usuario_id == current_user.id,
        Notificacion.leida == False
    ).update({"leida": True})
    db.commit()
    return {"ok": True}


@router.get("/api/dashboard/ranking")
async def get_ranking(
    periodo: str = "mes",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Ranking de ventas por asesor/vendedor basado en ventas reales del período.
    periodo: dia | semana | mes | todo
    IMPORTANTE: incluye ventas con created_at NULL (filas sin fecha) y
    ventas sin vendedor asignado (aparecen como "Sin asesor").
    """
    hoy = datetime.now()
    if periodo == "dia":
        inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "semana":
        inicio = (hoy - timedelta(days=hoy.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "todo":
        inicio = None
    else:  # mes (default)
        inicio = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _filtro_fecha(col):
        """
        Filtra por período incluyendo filas con fecha NULL.
        SQLite/SQLAlchemy: NULL >= fecha devuelve NULL (falso), por eso usamos OR.
        """
        if inicio is None:
            return True  # sin filtro de fecha
        return or_(col >= inicio, col.is_(None))

    # ── VentaContado agrupada por vendedor ────────────────────────────────────
    vc_rows = (
        db.query(
            VentaContado.vendedor_id,
            func.count(VentaContado.id).label("cnt"),
            func.coalesce(func.sum(VentaContado.precio_final), 0).label("monto"),
        )
        .filter(_filtro_fecha(VentaContado.created_at))
        .group_by(VentaContado.vendedor_id)
        .all()
    )

    # ── VentaFinanciada por asesor_apertura ───────────────────────────────────
    vf_asesor_rows = (
        db.query(
            VentaFinanciada.asesor_apertura_id.label("uid"),
            func.count(VentaFinanciada.id).label("cnt"),
            func.coalesce(func.sum(VentaFinanciada.precio_total), 0).label("monto"),
        )
        .filter(
            _filtro_fecha(VentaFinanciada.created_at),
            VentaFinanciada.asesor_apertura_id.isnot(None),
        )
        .group_by(VentaFinanciada.asesor_apertura_id)
        .all()
    )

    # ── VentaFinanciada por supervisor_cierre ─────────────────────────────────
    vf_sup_rows = (
        db.query(
            VentaFinanciada.supervisor_cierre_id.label("uid"),
            func.count(VentaFinanciada.id).label("cnt"),
            func.coalesce(func.sum(VentaFinanciada.precio_total), 0).label("monto"),
        )
        .filter(
            _filtro_fecha(VentaFinanciada.created_at),
            VentaFinanciada.supervisor_cierre_id.isnot(None),
        )
        .group_by(VentaFinanciada.supervisor_cierre_id)
        .all()
    )

    # ── Acumular por usuario_id (None → clave especial "sin_asesor") ──────────
    SIN_ASESOR = "__sin_asesor__"
    totales: dict = {}

    def _acum(uid, tipo, cnt, monto):
        key = uid if uid is not None else SIN_ASESOR
        if key not in totales:
            totales[key] = {"vc": 0, "vf": 0, "monto_vc": 0.0, "monto_vf": 0.0}
        if tipo == "vc":
            totales[key]["vc"]       += int(cnt)
            totales[key]["monto_vc"] += float(monto)
        else:
            totales[key]["vf"]       += int(cnt)
            totales[key]["monto_vf"] += float(monto)

    for row in vc_rows:
        _acum(row.vendedor_id, "vc", row.cnt, row.monto)

    for row in vf_asesor_rows:
        _acum(row.uid, "vf", row.cnt, row.monto)

    for row in vf_sup_rows:
        _acum(row.uid, "vf", row.cnt, row.monto)

    if not totales:
        return {"periodo": periodo, "inicio": inicio.isoformat() if inicio else None, "ranking": []}

    # ── Obtener nombres de una sola query ──────────────────────────────────────
    uid_reales = [k for k in totales.keys() if k != SIN_ASESOR]
    usuarios_map = {}
    if uid_reales:
        usuarios_map = {
            u.id: u.nombre
            for u in db.query(Usuario).filter(Usuario.id.in_(uid_reales)).all()
        }

    ranking = []
    for key, t in totales.items():
        if key == SIN_ASESOR:
            nombre = "Sin asesor asignado"
            uid_val = None
        else:
            nombre = usuarios_map.get(key, f"Usuario #{key}")
            uid_val = key

        total_ventas = t["vc"] + t["vf"]
        monto_total  = round(t["monto_vc"] + t["monto_vf"], 2)
        ranking.append({
            "usuario_id":   uid_val,
            "nombre":       nombre,
            "total_ventas": total_ventas,
            "monto_total":  monto_total,
            "vc":           t["vc"],
            "vf":           t["vf"],
            "monto_vc":     round(t["monto_vc"], 2),
            "monto_vf":     round(t["monto_vf"], 2),
        })

    ranking.sort(key=lambda x: x["monto_total"], reverse=True)
    return {
        "periodo": periodo,
        "inicio": inicio.isoformat() if inicio else None,
        "total_ventas_periodo": sum(r["total_ventas"] for r in ranking),
        "ranking": ranking[:10],
    }


@router.get("/api/dashboard/metricas-avanzadas")
async def get_metricas_avanzadas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Métricas avanzadas de negocio:
    - Funnel de conversión de leads
    - Ticket promedio
    - Performance por asesor (leads activos, conversión)
    - Flujo de caja estimado próximos 30 días
    """
    from routers.auth import get_user_roles
    roles = get_user_roles(current_user)
    if "ADMIN" not in roles and "SUPERVISOR_CIERRE" not in roles:
        raise HTTPException(403, "Sin permisos")

    hoy = datetime.now()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hace_30 = hoy - timedelta(days=30)

    # ── Funnel de conversión (últimos 30 días) ─────────────────────────────────
    leads_30 = db.query(Lead).filter(Lead.created_at >= hace_30).all()
    total_leads = len(leads_30)

    funnel = {
        "total_ingresados": total_leads,
        "contactados": sum(1 for l in leads_30 if l.estado not in ("NUEVO", "INTENTADO")),
        "calificados": sum(1 for l in leads_30 if l.estado in ("CALIFICADO", "VL_AGENDADA", "CERRADO", "CERRADO_GANADO")),
        "ventas": sum(1 for l in leads_30 if l.estado in ("CERRADO", "CERRADO_GANADO")),
        "perdidos": sum(1 for l in leads_30 if l.estado in ("PERDIDO", "CERRADO_PERDIDO")),
    }
    funnel["tasa_contacto"]    = round(funnel["contactados"] / total_leads * 100, 1) if total_leads else 0
    funnel["tasa_calificacion"] = round(funnel["calificados"] / total_leads * 100, 1) if total_leads else 0
    funnel["tasa_conversion"]  = round(funnel["ventas"]     / total_leads * 100, 1) if total_leads else 0

    # ── Ticket promedio (mes actual) ───────────────────────────────────────────
    vc_mes = db.query(VentaContado).filter(VentaContado.created_at >= inicio_mes).all()
    vf_mes = db.query(VentaFinanciada).filter(VentaFinanciada.created_at >= inicio_mes).all()
    montos = [v.precio_final or 0 for v in vc_mes] + [v.precio_total or 0 for v in vf_mes]
    ticket_promedio = round(sum(montos) / len(montos)) if montos else 0

    # ── Performance por asesor ─────────────────────────────────────────────────
    asesores = db.query(Usuario).filter(Usuario.activo == True).all()
    performance = []
    for u in asesores:
        try:
            uroles = json.loads(u.roles_json or "[]")
        except Exception:
            uroles = []
        if "ASESOR_APERTURA" not in uroles and "ADMIN" not in uroles:
            continue

        mis_leads = [l for l in leads_30 if l.asesor_apertura_id == u.id]
        mis_ventas = sum(1 for l in mis_leads if l.estado in ("CERRADO", "CERRADO_GANADO"))
        performance.append({
            "id": u.id,
            "nombre": u.nombre,
            "leads_30d": len(mis_leads),
            "ventas_30d": mis_ventas,
            "conversion": round(mis_ventas / len(mis_leads) * 100, 1) if mis_leads else 0,
            "leads_activos": db.query(Lead).filter(
                Lead.asesor_apertura_id == u.id,
                Lead.estado.notin_(["CERRADO", "CERRADO_GANADO", "PERDIDO", "CERRADO_PERDIDO"])
            ).count(),
        })
    performance.sort(key=lambda x: x["ventas_30d"], reverse=True)

    # ── Flujo de caja próximos 30 días (cuotas esperadas) ─────────────────────
    fin_30 = hoy + timedelta(days=30)
    ventas_activas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
    ).all()

    from routers.ventas_financiadas import calcular_proximo_vencimiento
    flujo_30d = {}
    for v in ventas_activas:
        prox = calcular_proximo_vencimiento(v)
        if prox and hoy <= prox <= fin_30:
            dia = prox.strftime("%Y-%m-%d")
            flujo_30d[dia] = flujo_30d.get(dia, 0) + (v.valor_cuota or 0)

    flujo_lista = [{"fecha": k, "monto": round(v)} for k, v in sorted(flujo_30d.items())]
    total_flujo_30d = sum(f["monto"] for f in flujo_lista)

    # ── Origen de leads (últimos 30 días) ─────────────────────────────────────
    origenes = {}
    for l in leads_30:
        o = l.origen or "DESCONOCIDO"
        origenes[o] = origenes.get(o, 0) + 1

    # ── Producto más vendido (mes) ────────────────────────────────────────────
    productos = {}
    for v in vc_mes + vf_mes:
        p = getattr(v, "producto_tipo", None) or getattr(v, "tipo", None) or "SIN_DEFINIR"
        productos[p] = productos.get(p, 0) + 1

    return {
        "periodo": "últimos 30 días",
        "funnel": funnel,
        "ticket_promedio": ticket_promedio,
        "total_ventas_mes": len(montos),
        "revenue_mes": sum(montos),
        "performance_asesores": performance,
        "flujo_caja_30d": flujo_lista,
        "total_flujo_esperado_30d": total_flujo_30d,
        "leads_por_origen": origenes,
        "productos_mas_vendidos": productos,
    }


@router.get("/api/dashboard/alertas")
async def get_alertas_dashboard(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Alertas de actividad pendiente según rol del usuario."""
    from database.models import Entrega, Videollamada as VL2
    from routers.ventas_financiadas import dias_atraso as _dias_atraso

    roles = get_user_roles(current_user)
    hoy = datetime.now()
    alertas = []

    # Leads con seguimiento vencido
    q_seg = db.query(Lead).filter(
        Lead.proximo_seguimiento <= hoy,
        Lead.estado.notin_(["CERRADO", "PERDIDO", "CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO"]),
    )
    if "ADMIN" not in roles:
        q_seg = q_seg.filter(Lead.asesor_apertura_id == current_user.id)
    seg_vencidos = q_seg.count()
    if seg_vencidos > 0:
        alertas.append({"tipo": "seguimiento", "urgencia": "rojo", "titulo": f"{seg_vencidos} seguimiento{'s' if seg_vencidos != 1 else ''} vencido{'s' if seg_vencidos != 1 else ''}", "detalle": "Leads con llamada programada sin contactar", "url": "/leads"})

    # Leads sin contactar > 24h
    limite_24 = hoy - timedelta(hours=24)
    q_sc = db.query(Lead).filter(Lead.estado.in_(["NUEVO", "INTENTADO"]))
    if "ADMIN" not in roles:
        q_sc = q_sc.filter(Lead.asesor_apertura_id == current_user.id)
    sc = q_sc.filter(Lead.updated_at <= limite_24).count()
    if sc > 0:
        alertas.append({"tipo": "sin_contactar", "urgencia": "rojo" if sc > 5 else "amarillo", "titulo": f"{sc} lead{'s' if sc != 1 else ''} sin contactar hace +24hs", "detalle": "Riesgo de perder oportunidades de venta", "url": "/leads", "puede_redistribuir": "ADMIN" in roles})

    # VLs hoy sin supervisor
    if "ADMIN" in roles or "SUPERVISOR_CIERRE" in roles:
        ini_hoy = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_hoy = hoy.replace(hour=23, minute=59, second=59, microsecond=999999)
        vl_sin = db.query(VL2).filter(VL2.fecha_hora >= ini_hoy, VL2.fecha_hora <= fin_hoy, VL2.supervisor_cierre_id == None, VL2.estado == "AGENDADA").count()
        if vl_sin > 0:
            alertas.append({"tipo": "vl_sin_supervisor", "urgencia": "amarillo", "titulo": f"{vl_sin} VL{'s' if vl_sin != 1 else ''} de hoy sin supervisor", "detalle": "Asignar supervisor para cerrar la venta", "url": "/semana-vls"})

    # Entregas vencidas
    if "ADMIN" in roles or "COORDINADOR_OPERATIVO" in roles:
        ent_venc = db.query(Entrega).filter(Entrega.fecha_instalacion < hoy, Entrega.estado.in_(["COORDINADA", "EN_CAMINO"])).count()
        if ent_venc > 0:
            alertas.append({"tipo": "entrega_vencida", "urgencia": "rojo", "titulo": f"{ent_venc} entrega{'s' if ent_venc != 1 else ''} sin completar de días anteriores", "detalle": "Requieren reprogramación urgente", "url": "/semana-entregas"})

    # Cobranzas críticas (+30 días)
    if "ADMIN" in roles or "COBRANZAS" in roles:
        vf_all = db.query(VentaFinanciada).filter(VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])).all()
        criticas = sum(1 for v in vf_all if _dias_atraso(v) >= 30)
        if criticas > 0:
            alertas.append({"tipo": "cobranza_critica", "urgencia": "rojo", "titulo": f"{criticas} plan{'es' if criticas != 1 else ''} con +30 días de atraso", "detalle": "Gestión de cobranza urgente requerida", "url": "/cobranzas"})

    # Órdenes fábrica sin coordinar
    if "ADMIN" in roles or "COORDINADOR_OPERATIVO" in roles or "FABRICA" in roles:
        ord_list = db.query(OrdenFabricaPiscina).filter(OrdenFabricaPiscina.estado == "TERMINADA").count()
        ord_list += db.query(OrdenFabricaModulo).filter(OrdenFabricaModulo.estado == "TERMINADA").count()
        if ord_list > 0:
            alertas.append({"tipo": "fabrica_lista", "urgencia": "verde", "titulo": f"{ord_list} orden{'es' if ord_list != 1 else ''} lista{'s' if ord_list != 1 else ''} para coordinar entrega", "detalle": "Producción terminada esperando coordinación", "url": "/fabrica"})

    return alertas


@router.get("/api/dashboard/stock-oferta")
async def get_stock_oferta(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Stock disponible en fábrica para promover ventas desde el dashboard."""
    from database.models import StockPiscina, StockPanel
    piscinas = db.query(StockPiscina).filter(StockPiscina.cantidad > 0).order_by(StockPiscina.modelo).all()
    paneles = db.query(StockPanel).filter(StockPanel.cantidad > 0).order_by(StockPanel.tipo_panel).all()
    return {
        "piscinas": [{"id": p.id, "modelo": p.modelo, "color": p.color or "", "cantidad": p.cantidad} for p in piscinas],
        "paneles": [{"id": p.id, "tipo": p.tipo_panel, "cantidad": p.cantidad} for p in paneles],
        "total_piscinas": sum(p.cantidad for p in piscinas),
        "total_paneles": sum(p.cantidad for p in paneles),
    }


# ─── DASHBOARD POR ROL (debe ir AL FINAL para no interceptar rutas específicas) ──
# /api/dashboard/ranking, /api/dashboard/alertas, /api/dashboard/stock-oferta
# deben estar registradas ANTES de esta ruta dinámica.

@router.get("/api/dashboard/{rol}")
async def get_dashboard(
    rol: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    return await _get_dashboard_impl(rol, db, current_user)
