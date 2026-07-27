import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import VentaFinanciada, Pago, Usuario, Lead, Interaccion, SolicitudContador
from routers.auth import require_auth, require_roles, get_user_roles, get_current_user, require_auth_or_apikey
from routers.notificaciones import notificar_nueva_venta

router = APIRouter()
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("API_KEY", "eco-crm-api-key-2024")


def _import_auth(x_api_key: Optional[str], current_user: Optional[Usuario]):
    """Importación histórica: sesión ADMIN, o X-API-Key (uso puntual/scripts)."""
    if x_api_key and x_api_key == API_KEY:
        return
    if current_user and "ADMIN" in get_user_roles(current_user):
        return
    raise HTTPException(403, "Sin permisos")


_DIAS_MES = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _es_bisiesto(anio: int) -> bool:
    return anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)


def _sumar_meses(fecha: datetime, n: int) -> datetime:
    """Suma n meses calendario a fecha, ajustando el día si el mes destino es más corto."""
    mes_total = fecha.month - 1 + n
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia_max = 29 if (mes == 2 and _es_bisiesto(anio)) else _DIAS_MES[mes - 1]
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, dia_max))


def calcular_proximo_vencimiento(venta: VentaFinanciada) -> Optional[datetime]:
    """
    Vigencia mensual: la venta entra en cobro el mes SIGUIENTE al del pago de
    la entrada (2 cuotas de ingreso). Cada cuota vence entre el día 1 y el 10
    del mes que corresponda — no abonar dentro de esa ventana hace perder las
    promociones vigentes del contrato. Se usa el día 10 (límite) como fecha
    de vencimiento de referencia.
    """
    base = venta.fecha_inicio_plan or venta.fecha_primer_vencimiento
    if not base:
        return None
    cuotas_pagadas = venta.cuotas_pagas or 0
    mes_objetivo = _sumar_meses(base, 1 + cuotas_pagadas)
    return mes_objetivo.replace(day=10, hour=23, minute=59, second=59, microsecond=0)


def dias_atraso(venta: VentaFinanciada) -> int:
    proximo = calcular_proximo_vencimiento(venta)
    if not proximo:
        return 0
    if proximo < datetime.now():
        return (datetime.now() - proximo).days
    return 0


def venta_to_dict(v: VentaFinanciada) -> dict:
    cuotas_pendientes = max(0, (v.cantidad_cuotas or 0) - (v.cuotas_pagas or 0))
    proximo_vcto = calcular_proximo_vencimiento(v)
    atraso = dias_atraso(v)

    return {
        "id": v.id,
        "cliente_nombre": v.cliente_nombre,
        "cliente_telefono": v.cliente_telefono or "",
        "cliente_localidad": v.cliente_localidad or "",
        "numero_solicitud": v.numero_solicitud or "",
        "cliente_dni": v.cliente_dni or "",
        "cliente_cuil": v.cliente_cuil or "",
        "cliente_domicilio": v.cliente_domicilio or "",
        "cliente_estado_civil": v.cliente_estado_civil or "",
        "cliente_ocupacion": v.cliente_ocupacion or "",
        "cliente_email": v.cliente_email or "",
        "producto": v.producto or "",
        "modelo_especifico": v.modelo_especifico or "",
        "color": v.color or "",
        "superficie_m2": v.superficie_m2,
        "forma_pago": v.forma_pago or "",
        "precio_total": v.precio_total or 0,
        "anticipo": v.anticipo or 0,
        "cantidad_cuotas": v.cantidad_cuotas or 0,
        "valor_cuota": v.valor_cuota or 0,
        "fecha_inicio_plan": v.fecha_inicio_plan.isoformat() if v.fecha_inicio_plan else None,
        "fecha_primer_vencimiento": v.fecha_primer_vencimiento.isoformat() if v.fecha_primer_vencimiento else None,
        "cuotas_pagas": v.cuotas_pagas or 0,
        "cuotas_pendientes": cuotas_pendientes,
        "proximo_vencimiento": proximo_vcto.isoformat() if proximo_vcto else None,
        "monto_proxima_cuota": v.valor_cuota or 0,
        "dias_atraso": atraso,
        "asesor_apertura_id": v.asesor_apertura_id,
        "asesor_apertura_nombre": v.asesor_apertura.nombre if v.asesor_apertura else "",
        "supervisor_cierre_id": v.supervisor_cierre_id,
        "supervisor_cierre_nombre": v.supervisor_cierre.nombre if v.supervisor_cierre else "",
        "estado_plan": v.estado_plan or "ACTIVO",
        "estado_admision": v.estado_admision,
        "notas": v.notas or "",
        "created_at": v.created_at.isoformat() if v.created_at else "",
        "alerta": "ROJA" if atraso > 0 else ("AMARILLA" if proximo_vcto and (proximo_vcto - datetime.now()).days <= 3 else None),
    }


@router.get("/ventas-financiadas", response_class=HTMLResponse)
async def ventas_financiadas_page(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_auth)):
    roles = get_user_roles(current_user)
    usuarios = db.query(Usuario).filter(Usuario.activo == True).all()
    return templates.TemplateResponse("ventas_financiadas.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
        "usuarios": [{"id": u.id, "nombre": u.nombre} for u in usuarios],
    })


@router.get("/api/ventas-financiadas")
async def list_ventas_financiadas(
    estado_plan: Optional[str] = None,
    forma_pago: Optional[str] = None,
    search: Optional[str] = None,
    con_atraso: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    q = db.query(VentaFinanciada)
    if estado_plan:
        q = q.filter(VentaFinanciada.estado_plan == estado_plan)
    if forma_pago:
        q = q.filter(VentaFinanciada.forma_pago == forma_pago)
    if search:
        q = q.filter(VentaFinanciada.cliente_nombre.ilike(f"%{search}%"))

    ventas = q.order_by(VentaFinanciada.created_at.desc()).all()

    if con_atraso:
        ventas = [v for v in ventas if dias_atraso(v) > 0]

    return [venta_to_dict(v) for v in ventas]


@router.post("/api/ventas-financiadas")
async def create_venta_financiada(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    data = await request.json()

    fecha_inicio = None
    fecha_primer_vcto = None
    if data.get("fecha_inicio_plan"):
        try:
            fecha_inicio = datetime.fromisoformat(data["fecha_inicio_plan"])
        except Exception:
            pass
    if data.get("fecha_primer_vencimiento"):
        try:
            fecha_primer_vcto = datetime.fromisoformat(data["fecha_primer_vencimiento"])
        except Exception:
            pass

    venta = VentaFinanciada(
        cliente_nombre=data.get("cliente_nombre", ""),
        cliente_telefono=data.get("cliente_telefono", ""),
        cliente_localidad=data.get("cliente_localidad", ""),
        producto=data.get("producto", ""),
        modelo_especifico=data.get("modelo_especifico", ""),
        color=data.get("color"),
        superficie_m2=data.get("superficie_m2"),
        forma_pago=data.get("forma_pago", "PMI"),
        precio_total=data.get("precio_total", 0),
        anticipo=data.get("anticipo", 0),
        cantidad_cuotas=data.get("cantidad_cuotas", 1),
        valor_cuota=data.get("valor_cuota", 0),
        fecha_inicio_plan=fecha_inicio,
        fecha_primer_vencimiento=fecha_primer_vcto,
        cuotas_pagas=0,
        asesor_apertura_id=data.get("asesor_apertura_id") or current_user.id,
        supervisor_cierre_id=data.get("supervisor_cierre_id"),
        estado_plan=data.get("estado_plan", "ACTIVO"),
        estado_admision=data.get("estado_admision"),
        notas=data.get("notas", ""),
    )
    db.add(venta)
    db.commit()
    db.refresh(venta)

    # ── A5: Auto-vincular lead por teléfono ─────────────────────────────────
    if venta.cliente_telefono:
        lead = db.query(Lead).filter(
            Lead.telefono.ilike(f"%{venta.cliente_telefono.strip()}%")
        ).order_by(Lead.created_at.desc()).first()
        if lead and lead.estado not in ["CERRADO_GANADO", "CERRADO_PERDIDO"]:
            lead.estado = "CERRADO_GANADO"
            db.add(Interaccion(
                lead_id=lead.id,
                tipo="VENTA",
                resultado="VENTA_CONCRETADA",
                notas=f"Venta financiada #{venta.id} — {venta.modelo_especifico or venta.producto}",
                asesor_id=venta.asesor_apertura_id,
            ))
            db.commit()

    # ── Notificaciones ───────────────────────────────────────────────────────
    notificar_nueva_venta(
        db,
        tipo_venta="FINANCIADA",
        cliente_nombre=venta.cliente_nombre,
        producto=venta.producto or "",
        modelo=venta.modelo_especifico or "",
        monto=venta.precio_total or 0,
        vendedor_id=venta.asesor_apertura_id,
        supervisor_id=venta.supervisor_cierre_id,
        referencia_id=venta.id,
    )
    db.commit()

    return {"id": venta.id, "ok": True}


@router.put("/api/ventas-financiadas/{venta_id}")
async def update_venta_financiada(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()

    for dt_field in ["fecha_inicio_plan", "fecha_primer_vencimiento"]:
        if dt_field in data and data[dt_field]:
            try:
                setattr(venta, dt_field, datetime.fromisoformat(data[dt_field]))
            except Exception:
                pass

    for field in ["cliente_nombre", "cliente_telefono", "cliente_localidad", "producto",
                  "modelo_especifico", "color", "superficie_m2", "forma_pago", "precio_total",
                  "anticipo", "cantidad_cuotas", "valor_cuota", "cuotas_pagas",
                  "asesor_apertura_id", "supervisor_cierre_id", "estado_plan",
                  "estado_admision", "notas"]:
        if field in data:
            setattr(venta, field, data[field])

    db.commit()
    return {"ok": True}


@router.post("/api/ventas-financiadas/{venta_id}/pago")
async def registrar_pago(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey)
):
    """
    Registra un pago (cuota mensual, seña/entrada o saldo final) y emite el
    recibo real en PDF automáticamente. Body:
    {"monto": 120000, "notas": "...", "concepto": "cuota"|"entrada"|"saldo_final",
     "modalidad": "transferencia"|"efectivo"}
    concepto default "cuota" (incrementa cuotas_pagas); "entrada"/"saldo_final"
    no tocan cuotas_pagas, solo suman al anticipo/saldo.
    """
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")

    data = await request.json()
    monto = data.get("monto", venta.valor_cuota or 0)
    concepto = (data.get("concepto") or "cuota").lower()

    pago = Pago(
        venta_financiada_id=venta_id,
        monto=monto,
        notas=data.get("notas", ""),
    )
    db.add(pago)

    if concepto == "cuota":
        venta.cuotas_pagas = (venta.cuotas_pagas or 0) + 1
    else:
        venta.anticipo = (venta.anticipo or 0) + float(monto)

    if venta.cuotas_pagas >= venta.cantidad_cuotas or (venta.anticipo or 0) + (venta.cuotas_pagas or 0) * (venta.valor_cuota or 0) >= (venta.precio_total or 0):
        venta.estado_plan = "FINALIZADO"
    elif dias_atraso(venta) > 0:
        venta.estado_plan = "ACTIVO"

    db.commit()

    concepto_recibo = {"cuota": "Pago de cuota", "entrada": "Cuota inicial", "saldo_final": "Saldo final"}.get(concepto, "Pago")
    resultado = {"ok": True, "cuotas_pagas": venta.cuotas_pagas, "recibo": None}
    try:
        from routers.contratos import generar_recibo_pdf
        recibo = await generar_recibo_pdf(
            db, venta, monto_recibido=float(monto), concepto=concepto_recibo,
            modalidad=data.get("modalidad", ""),
        )
        resultado["recibo"] = {
            "recibo_id": recibo.id,
            "download_url": f"/api/contratos/{recibo.id}/download",
            "saldo_pendiente": recibo.saldo_pendiente,
            "es_cierre": recibo.es_cierre,
        }
    except Exception as e:
        logger_msg = f"No se pudo generar el recibo automático: {e}"
        resultado["recibo_error"] = logger_msg

    return resultado


@router.get("/api/ventas-financiadas/{venta_id}")
async def get_venta_financiada(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth)
):
    venta = db.query(VentaFinanciada).filter(VentaFinanciada.id == venta_id).first()
    if not venta:
        raise HTTPException(404, "Venta no encontrada")
    return venta_to_dict(venta)


# ─── Importación de contratos históricos (numeración 000-13860XXX) ───────────
# Registros cuyo teléfono/email quedó cruzado entre sí en el origen (misma
# fuente reportó el mismo dato de contacto para 3 clientes distintos) —
# se importan sin contacto, marcados para verificar antes de escribirles.
_CONTACTO_A_VERIFICAR = {"000-13860151", "000-13860155", "000-13860158"}


def _parse_fecha(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _categoria_producto(producto: Optional[str]) -> str:
    if not producto:
        return ""
    p = producto.lower()
    if "combo" in p:
        return "COMBO"
    return "PISCINA"


@router.post("/api/ventas-financiadas/importar-historico")
async def importar_historico(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: Optional[Usuario] = Depends(get_current_user),
):
    """
    Importación puntual de contratos históricos (numeración 000-13860XXX)
    generados fuera del CRM. Idempotente por numero_solicitud: si ya existe,
    se omite (no pisa datos existentes).
    """
    _import_auth(x_api_key, current_user)
    data = await request.json()
    contratos = data.get("contratos") or []
    if not isinstance(contratos, list) or not contratos:
        raise HTTPException(400, "Falta 'contratos' (lista)")

    creados, omitidos, contacto_limpiado, incompletos = [], [], [], []
    max_numero = None

    for c in contratos:
        numero = (c.get("numero_solicitud") or "").strip()
        if not numero:
            continue

        # Trackear el número más alto visto para reacomodar el contador al final
        try:
            n_int = int(numero.split("-")[-1])
            max_numero = n_int if max_numero is None else max(max_numero, n_int)
        except Exception:
            pass

        ya_existe = db.query(VentaFinanciada).filter(VentaFinanciada.numero_solicitud == numero).first()
        if ya_existe:
            omitidos.append(numero)
            continue

        telefono, email = c.get("telefono"), c.get("email")
        notas_partes = []
        if numero in _CONTACTO_A_VERIFICAR:
            notas_partes.append(
                "⚠️ CONTACTO SIN VERIFICAR: el teléfono/email de origen quedó "
                "cruzado con el de otro cliente en la fuente — se dejó vacío a "
                "propósito. Confirmar con el cliente antes de contactarlo."
            )
            telefono, email = None, None
            contacto_limpiado.append(numero)

        incompleto = not c.get("producto") and not c.get("dni")
        if incompleto:
            notas_partes.append("⚠️ INCOMPLETO: contrato referenciado con datos faltantes en el origen.")
            incompletos.append(numero)

        for campo in ("nota", "nota_error"):
            if c.get(campo):
                notas_partes.append(f"[{campo}] {c[campo]}")

        for campo, etiqueta in (
            ("medidas", "Medidas"), ("medidas_piscina", "Medidas piscina"),
            ("sistema", "Sistema"), ("entrega", "Entrega"),
            ("estado_inscripcion", "Estado inscripción"),
            ("inscripcion_total", "Inscripción total"),
            ("saldo_inscripcion", "Saldo inscripción"),
            ("incluye", "Incluye"),
            ("dni_conyuge", "DNI cónyuge"), ("cuil_conyuge", "CUIL cónyuge"),
            ("telefono_conyuge", "Tel. cónyuge"), ("ocupacion_conyuge", "Ocupación cónyuge"),
            ("fecha_contrato", "Fecha contrato (origen)"),
        ):
            if c.get(campo) not in (None, ""):
                notas_partes.append(f"{etiqueta}: {c[campo]}")

        venta = VentaFinanciada(
            cliente_nombre=c.get("cliente") or "(sin nombre)",
            cliente_telefono=telefono,
            cliente_email=email,
            producto=_categoria_producto(c.get("producto")),
            modelo_especifico=c.get("producto") or "",
            forma_pago="HISTORICO",
            precio_total=c.get("valor_total") or 0,
            anticipo=c.get("pagado_inscripcion") or 0,
            cantidad_cuotas=c.get("cant_cuotas") or 1,
            valor_cuota=c.get("valor_cuota") or 0,
            fecha_inicio_plan=_parse_fecha(c.get("fecha_contrato")),
            estado_plan="ACTIVO",
            estado_admision="INCOMPLETO" if incompleto else None,
            numero_solicitud=numero,
            cliente_dni=c.get("dni"),
            cliente_cuil=c.get("cuil"),
            cliente_domicilio=c.get("domicilio"),
            cliente_estado_civil=c.get("estado_civil"),
            cliente_ocupacion=c.get("ocupacion"),
            notas="\n".join(notas_partes),
        )
        db.add(venta)
        creados.append(numero)

    # Reacomodar el contador de numeración para que el próximo emitido no colisione
    if max_numero is not None:
        contador = db.query(SolicitudContador).filter(SolicitudContador.id == 1).first()
        if not contador:
            contador = SolicitudContador(id=1, prefijo="000", ultimo_numero=max_numero)
            db.add(contador)
        elif (contador.ultimo_numero or 0) < max_numero:
            contador.ultimo_numero = max_numero

    db.commit()
    return {
        "ok": True,
        "creados": creados,
        "omitidos_ya_existian": omitidos,
        "contacto_limpiado_a_verificar": contacto_limpiado,
        "incompletos": incompletos,
        "total_creados": len(creados),
    }


@router.post("/api/ventas-financiadas/corregir-fechas-historico")
async def corregir_fechas_historico(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth_or_apikey),
):
    """
    Corrige los contratos importados desde el historial (numero_solicitud
    000-138601xx): created_at quedó en la fecha de la IMPORTACIÓN (hoy), no
    la fecha real del contrato — contaminaba "ventas de hoy"/"ventas del
    mes". calcular_proximo_vencimiento() ya usa fecha_inicio_plan como base
    (vigencia mensual, día 10), así que no hace falta tocar
    fecha_primer_vencimiento. Idempotente.
    """
    ventas = db.query(VentaFinanciada).filter(
        VentaFinanciada.numero_solicitud.like("000-1386%")
    ).all()

    corregidas = []
    for v in ventas:
        if v.fecha_inicio_plan and (v.created_at is None or v.created_at.date() != v.fecha_inicio_plan.date()):
            v.created_at = v.fecha_inicio_plan
            corregidas.append(v.numero_solicitud)

    db.commit()
    return {"ok": True, "corregidas": corregidas, "total": len(corregidas)}
