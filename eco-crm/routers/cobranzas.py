from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import VentaFinanciada, GestionCobranza, Usuario
from routers.auth import require_auth, require_roles, get_user_roles, require_auth_or_apikey
from routers.ventas_financiadas import venta_to_dict, dias_atraso, calcular_proximo_vencimiento

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def mensaje_whatsapp(venta: VentaFinanciada) -> str:
    atraso = dias_atraso(venta)
    nombre = venta.cliente_nombre.split()[0] if venta.cliente_nombre else "cliente"
    monto = f"${venta.valor_cuota:,.0f}" if venta.valor_cuota else ""
    proximo = calcular_proximo_vencimiento(venta)

    if atraso == 0 and proximo:
        diff = (proximo - datetime.now()).days
        if diff <= 0:
            return f"Hola {nombre}, te recordamos que hoy vence tu cuota de {monto}. Podés abonar por transferencia. ¡Gracias!"
    if 0 < atraso <= 7:
        return f"Hola {nombre}, notamos que tenés una cuota vencida de {monto}. ¿Podemos coordinar el pago?"
    if atraso > 7:
        pendientes = max(0, (venta.cantidad_cuotas or 0) - (venta.cuotas_pagas or 0))
        monto_total = f"${(venta.valor_cuota or 0) * pendientes:,.0f}"
        return f"Hola {nombre}, tenés {pendientes} cuota(s) vencida(s) por {monto_total}. Necesitamos regularizar. ¿Cuándo podemos hablar?"
    return f"Hola {nombre}, te contactamos desde EcoFiver."


@router.get("/cobranzas", response_class=HTMLResponse)
async def cobranzas_page(request: Request, current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    return templates.TemplateResponse("cobranzas.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


@router.get("/api/cobranzas/cartera")
async def get_cartera(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "COBRANZAS" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    ventas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
    ).order_by(VentaFinanciada.fecha_primer_vencimiento.asc()).all()

    result = []
    for v in ventas:
        atraso = dias_atraso(v)
        proximo = calcular_proximo_vencimiento(v)

        # Buscar último contacto
        ultima_gestion = db.query(GestionCobranza).filter(
            GestionCobranza.venta_financiada_id == v.id
        ).order_by(GestionCobranza.fecha_contacto.desc()).first()

        d = venta_to_dict(v)
        d["mensaje_whatsapp"] = mensaje_whatsapp(v)
        d["ultimo_contacto"] = ultima_gestion.fecha_contacto.isoformat() if ultima_gestion else None
        d["ultimo_resultado"] = ultima_gestion.resultado if ultima_gestion else None
        result.append(d)

    return sorted(result, key=lambda x: x["dias_atraso"], reverse=True)


@router.post("/api/cobranzas/{venta_id}/gestion")
async def registrar_gestion(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()
    gestion = GestionCobranza(
        venta_financiada_id=venta_id,
        canal=data.get("canal", "WHATSAPP"),
        resultado=data.get("resultado", "NO_CONTESTO"),
        notas=data.get("notas", ""),
    )
    db.add(gestion)

    # Update estado if pago registered
    if data.get("resultado") == "PAGO":
        venta.cuotas_pagas = (venta.cuotas_pagas or 0) + 1
        if venta.cuotas_pagas >= venta.cantidad_cuotas:
            venta.estado_plan = "FINALIZADO"
        else:
            venta.estado_plan = "ACTIVO"

    db.commit()
    return {"ok": True}


@router.get("/api/cobranzas/{venta_id}/gestiones")
async def get_gestiones(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    gestiones = db.query(GestionCobranza).filter(
        GestionCobranza.venta_financiada_id == venta_id
    ).order_by(GestionCobranza.fecha_contacto.desc()).all()

    return [{
        "id": g.id,
        "fecha_contacto": g.fecha_contacto.isoformat(),
        "canal": g.canal,
        "resultado": g.resultado,
        "notas": g.notas,
    } for g in gestiones]


@router.get("/api/cobranzas/resumen")
async def resumen_cobranzas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    roles = get_user_roles(current_user)
    if "COBRANZAS" not in roles and "ADMIN" not in roles:
        raise HTTPException(403, "Sin permisos")

    hoy = datetime.now()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    ventas_activas = db.query(VentaFinanciada).filter(
        VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"])
    ).all()

    vencen_hoy = 0
    vencidas = 0
    monto_vencido = 0

    for v in ventas_activas:
        atraso = dias_atraso(v)
        proximo = calcular_proximo_vencimiento(v)
        if atraso > 0:
            vencidas += 1
            monto_vencido += (v.valor_cuota or 0)
        elif proximo and proximo.date() == hoy.date():
            vencen_hoy += 1

    gestiones_hoy = db.query(GestionCobranza).filter(
        GestionCobranza.fecha_contacto >= hoy.replace(hour=0, minute=0, second=0)
    ).count()

    pagos_mes = db.query(GestionCobranza).filter(
        GestionCobranza.resultado == "PAGO",
        GestionCobranza.fecha_contacto >= inicio_mes
    ).count()

    return {
        "vencen_hoy": vencen_hoy,
        "vencidas": vencidas,
        "monto_vencido": monto_vencido,
        "gestiones_hoy": gestiones_hoy,
        "pagos_mes": pagos_mes,
    }
