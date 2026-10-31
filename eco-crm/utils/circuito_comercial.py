"""
Circuito comercial de EcoFiver (reglas confirmadas por el propietario).

CONTADO (piscinas, viviendas y módulos) — la IA vende y cierra comercialmente:
  CIERRE_COMERCIAL_CONFIRMADO → ENTREGA_PENDIENTE → ENTREGA_CONFIRMADA →
  COBRO_PENDIENTE → COBRO_CONFIRMADO. Pago en domicilio contra entrega.
  - La IA (Camila: piscinas; Luciano: viviendas y módulos) registra el cierre
    con modelo y precio del catálogo vigente (sin descuentos) y pide la entrega.
  - Entrega y cobro los confirma una persona con evidencia.

FINANCIACIÓN — la IA capta y abre; Admisión humana verifica, aprueba y cierra:
  CONSULTA_RECIBIDA, APERTURA_EN_PROCESO, PRECALIFICADO, VIDEOLLAMADA_PENDIENTE,
  EN_ADMISION | DOCUMENTACION_PENDIENTE, APROBADO_POR_ADMISION,
  RECHAZADO_POR_ADMISION, CIERRE_HUMANO_CONFIRMADO.
  - La IA (Nicolás: piscinas; Mateo: viviendas y módulos; Valentina solo abre la
    consulta) llega como máximo a EN_ADMISION.
  - Los estados reservados solo los cambia personal con rol ADMISION (sin
    excepción para ADMIN: un socio con ADMIN no aprueba créditos).
Todo cambio queda auditado, incluidos los intentos rechazados.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import ExpedienteEvento, ExpedienteFinanciacion, Lead, VentaContado, VentaFinanciada
from utils.motor_tareas import ErrorMotor


# ── Contado ───────────────────────────────────────────────────────────────────

ESTADOS_CONTADO = ["CIERRE_COMERCIAL_CONFIRMADO", "ENTREGA_PENDIENTE", "ENTREGA_CONFIRMADA",
                   "COBRO_PENDIENTE", "COBRO_CONFIRMADO"]
AGENTES_CONTADO = {"camila": {"PISCINA"}, "luciano": {"MODULO", "VIVIENDA"}}
ROLES_ENTREGA = {"ADMIN", "LOGISTICA", "COORDINADOR_OPERATIVO"}
ROLES_COBRO = {"ADMIN", "COBRANZAS", "ADMINISTRACION"}

# ── Financiación ──────────────────────────────────────────────────────────────

ESTADOS_FIN = ["CONSULTA_RECIBIDA", "APERTURA_EN_PROCESO", "PRECALIFICADO", "VIDEOLLAMADA_PENDIENTE",
               "EN_ADMISION", "DOCUMENTACION_PENDIENTE", "APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION",
               "CIERRE_HUMANO_CONFIRMADO"]
RESERVADOS_ADMISION = {"DOCUMENTACION_PENDIENTE", "APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION",
                       "CIERRE_HUMANO_CONFIRMADO"}
AGENTES_APERTURA = {"nicolas": {"PISCINA"}, "mateo": {"MODULO", "VIVIENDA"}, "valentina": {"PISCINA", "MODULO", "VIVIENDA"}}
# Transiciones de la IA (Valentina solo crea la consulta; deriva el especialista)
TRANSICIONES_IA = {
    "CONSULTA_RECIBIDA": {"APERTURA_EN_PROCESO"},
    "APERTURA_EN_PROCESO": {"PRECALIFICADO", "VIDEOLLAMADA_PENDIENTE"},
    "PRECALIFICADO": {"VIDEOLLAMADA_PENDIENTE", "EN_ADMISION"},
    "VIDEOLLAMADA_PENDIENTE": {"EN_ADMISION"},
}
TRANSICIONES_ADMISION = {
    "EN_ADMISION": {"DOCUMENTACION_PENDIENTE", "APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION"},
    "DOCUMENTACION_PENDIENTE": {"EN_ADMISION", "APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION"},
    "APROBADO_POR_ADMISION": {"CIERRE_HUMANO_CONFIRMADO", "RECHAZADO_POR_ADMISION"},
}
# Datos de apertura permitidos (sin documentación personal ni crediticia)
CAMPOS_APERTURA = {"localidad", "provincia", "ocupacion_declarada", "ingreso_declarado_rango", "uso_previsto",
                   "plazo_preferido", "cuota_objetivo", "como_nos_conocio", "observaciones"}

PRODUCTOS = {"PISCINA", "MODULO", "VIVIENDA"}


def _ahora() -> datetime:
    return datetime.utcnow()


def _roles(usuario) -> set:
    from routers.auth import get_user_roles
    return set(get_user_roles(usuario))


def _humano_interno(usuario) -> None:
    """Persona del equipo interno: no el usuario técnico de IA ni una cuenta de socio."""
    if usuario is None or getattr(usuario, "es_agente_ia", False):
        raise ErrorMotor("Requiere una persona autorizada", 403)
    if getattr(usuario, "aliado_codigo", None):
        raise ErrorMotor("Las cuentas de socios no confirman operaciones internas", 403)


def _persona_admision(usuario) -> None:
    """Decisiones sobre expedientes: persona interna, o la cuenta de un socio SOLO si un ADMIN le
    asignó el rol ADMISION (decisión del propietario: la Admisión la hace AL-010).
    Entregas, cobros y pagos siguen cerrados a las cuentas de socios."""
    if usuario is not None and getattr(usuario, "aliado_codigo", None) and "ADMISION" in _roles(usuario) \
            and not getattr(usuario, "es_agente_ia", False):
        return
    _humano_interno(usuario)


# ── Contado: precio de catálogo ───────────────────────────────────────────────

def precio_catalogo(producto: str, modelo: str) -> Optional[float]:
    from routers.catalogo import load_catalogo
    cat = load_catalogo()
    seccion = "piscinas" if producto == "PISCINA" else "modulos"
    precio = (cat.get(seccion, {}).get("precios") or {}).get(modelo)
    return float(precio) if precio else None


def cerrar_contado_ia(db: Session, agente: str, d: dict) -> tuple[VentaContado, bool]:
    """Cierre comercial de contado por un agente IA. Devuelve (venta, creada)."""
    agente = (agente or "").lower()
    producto = str(d.get("producto") or "").upper()
    if agente not in AGENTES_CONTADO:
        raise ErrorMotor(f"'{agente}' no está autorizado a cerrar ventas de contado", 403)
    if producto not in AGENTES_CONTADO[agente]:
        raise ErrorMotor(f"{agente} cierra solo {', '.join(sorted(AGENTES_CONTADO[agente]))}", 403)
    if str(d.get("forma_pago") or "CONTADO").upper() != "CONTADO":
        raise ErrorMotor("La IA solo cierra ventas de contado; la financiación va a Admisión", 403)
    lead = db.get(Lead, int(d.get("lead_id") or 0)) if d.get("lead_id") else None
    if not lead:
        raise ErrorMotor("El cierre debe estar asociado al lead de la conversación", 400)
    modelo = str(d.get("modelo") or "").strip()
    if producto == "PISCINA":
        v = _venta_piscina(db, agente, lead, modelo, d)
    else:
        v = _venta_modulo(db, agente, lead, modelo, d)
    if isinstance(v, tuple):          # (existente, False)
        return v
    db.add(v)
    db.commit()
    db.refresh(v)
    return v, True


def _existente(db: Session, lead_id: int, modelo: str):
    return (db.query(VentaContado)
            .filter(VentaContado.lead_id == lead_id, VentaContado.modelo_especifico == modelo,
                    VentaContado.estado != "CANCELADO", VentaContado.circuito_estado.isnot(None)).first())


def _faltan(d: dict, campos) -> None:
    faltan = [c for c in campos if not str(d.get(c) or "").strip()]
    if faltan:
        raise ErrorMotor(f"Faltan datos para el cierre: {', '.join(faltan)}", 400)


def _venta_piscina(db: Session, agente: str, lead, modelo: str, d: dict):
    """Piscina de contado: precio final único validado contra la cotización del servidor."""
    from datetime import date as _date
    from utils.cotizacion import cotizar_piscina
    _faltan(d, ("cliente_nombre", "cliente_localidad", "cliente_domicilio", "color", "aceptacion_cliente",
                "fecha_entrega_solicitada", "precio_final_acordado"))
    try:
        fecha = _date.fromisoformat(str(d["fecha_entrega_solicitada"])[:10])
    except ValueError:
        raise ErrorMotor("fecha_entrega_solicitada inválida (AAAA-MM-DD)", 400)
    if fecha < _date.today():
        raise ErrorMotor("La fecha de entrega solicitada ya pasó", 400)
    q = cotizar_piscina(db, modelo, str(d["cliente_localidad"]), str(d.get("cliente_provincia") or ""),
                        reserva_fecha=True)
    if not q["ok"]:
        raise ErrorMotor(f"No se puede cerrar: {q['detalle']}",
                         409 if q["motivo"] in ("distancia_no_disponible", "localidad_ambigua") else 400)
    try:
        acordado = float(d["precio_final_acordado"])
    except (TypeError, ValueError):
        raise ErrorMotor("Precio inválido", 400)
    if abs(acordado - q["precio_final"]) > 1:
        raise ErrorMotor(f"El precio acordado no coincide con la cotización vigente (${q['precio_final']:,.0f}). "
                         "La IA no puede modificar precios ni aplicar descuentos no autorizados", 403)
    existente = _existente(db, lead.id, modelo)
    if existente:
        return existente, False
    i = q["interno"]
    nota_ruta = f" Distancia: {i['km_ida']} km ({i['proveedor']}, {i['estado_distancia']})."
    q_dir = cotizar_piscina(db, modelo, str(d["cliente_localidad"]), str(d.get("cliente_provincia") or ""),
                            reserva_fecha=True, direccion=str(d["cliente_domicilio"]))
    if q_dir.get("ok") and abs(q_dir["interno"]["km_ida"] - i["km_ida"]) >= 5:
        nota_ruta += (f" REVISAR: por la dirección exacta son {q_dir['interno']['km_ida']} km "
                      f"(precio acordado con el cliente por localidad: se respeta).")
    condiciones = (f"Precio final único ${q['precio_final']:,.0f} (incluye {', '.join(q['incluye'])}). "
                   f"Pago contra entrega en domicilio, sin seña."
                   + (" Promoción aplicada sobre el traslado." if i["promocion_id"] else ""))
    return VentaContado(
        cliente_nombre=str(d["cliente_nombre"])[:150], cliente_telefono=lead.telefono or "",
        cliente_localidad=str(d["cliente_localidad"])[:100], cliente_domicilio=str(d["cliente_domicilio"])[:300],
        producto="PISCINA", modelo_especifico=modelo, color=str(d["color"])[:50],
        precio_final=i["precio_producto"], flete_calculado=i["flete_neto"], flete_bruto=i["flete_bruto"],
        descuento_flete=i["descuento_flete"], distancia_km=i["km_ida"], promocion_id=i["promocion_id"],
        precio_total_acordado=q["precio_final"], fecha_entrega_solicitada=fecha,
        forma_pago="CONTADO", modalidad_cobro="CONTRAENTREGA", cobro_estado="PENDIENTE",
        estado="PENDIENTE_COORDINACION", circuito_estado="CIERRE_COMERCIAL_CONFIRMADO",
        cerrada_por=f"agente:{agente}", lead_id=lead.id,
        notas=(f"Cierre comercial por {agente} (IA). {condiciones}{nota_ruta} Fecha de entrega solicitada: {fecha:%d/%m/%Y}. "
               f"Aceptación del cliente: {str(d['aceptacion_cliente'])[:500]}"),
    )


def _venta_modulo(db: Session, agente: str, lead, modelo: str, d: dict):
    """Viviendas/módulos de contado: precio de catálogo exacto (reglas de piscinas no aplican)."""
    precio_cat = precio_catalogo(str(d.get("producto")).upper(), modelo)
    if precio_cat is None:
        raise ErrorMotor(f"'{modelo}' no tiene precio de contado vigente en el catálogo", 400)
    try:
        precio = float(d.get("precio") if d.get("precio") is not None else d.get("precio_final_acordado"))
    except (TypeError, ValueError):
        raise ErrorMotor("Precio inválido", 400)
    if abs(precio - precio_cat) > 0.5:
        raise ErrorMotor(f"El precio no coincide con el catálogo vigente (${precio_cat:,.0f}). "
                         "La IA no puede modificar precios ni aplicar descuentos", 403)
    _faltan(d, ("cliente_nombre", "cliente_localidad", "aceptacion_cliente"))
    existente = _existente(db, lead.id, modelo)
    if existente:
        return existente, False
    return VentaContado(
        cliente_nombre=str(d["cliente_nombre"])[:150], cliente_telefono=lead.telefono or "",
        cliente_localidad=str(d["cliente_localidad"])[:100], cliente_domicilio=(str(d.get("cliente_domicilio") or "")[:300] or None),
        producto=str(d.get("producto")).upper(), modelo_especifico=modelo, color=(d.get("color") or None),
        precio_final=precio_cat, forma_pago="CONTADO", modalidad_cobro="CONTRAENTREGA", cobro_estado="PENDIENTE",
        estado="PENDIENTE_COORDINACION", circuito_estado="CIERRE_COMERCIAL_CONFIRMADO",
        cerrada_por=f"agente:{agente}", lead_id=lead.id,
        notas=f"Cierre comercial por {agente} (IA). Aceptación del cliente: {str(d['aceptacion_cliente'])[:500]}",
    )


def solicitar_entrega(db: Session, venta: VentaContado, actor: str) -> VentaContado:
    if venta.circuito_estado != "CIERRE_COMERCIAL_CONFIRMADO":
        raise ErrorMotor(f"La venta está en {venta.circuito_estado or 'circuito anterior'}", 409)
    venta.circuito_estado = "ENTREGA_PENDIENTE"
    venta.notas = (venta.notas or "") + f"\n[{_ahora():%d/%m/%Y}] Entrega solicitada por {actor}."
    db.commit()
    return venta


def confirmar_entrega(db: Session, venta: VentaContado, usuario, evidencia: str,
                      fecha: Optional[datetime] = None, verificar_rol: bool = True) -> VentaContado:
    """Entrega confirmada por una persona → genera la comisión de contado (idempotente)."""
    _humano_interno(usuario)
    if verificar_rol and not (_roles(usuario) & ROLES_ENTREGA):
        raise ErrorMotor("Confirmar entregas requiere rol de logística o coordinación", 403)
    if len((evidencia or "").strip()) < 5:
        raise ErrorMotor("Indicá la evidencia de la entrega (remito, foto, conformidad del cliente)", 400)
    if venta.estado == "CANCELADO":
        raise ErrorMotor("Venta cancelada", 409)
    if venta.entrega_confirmada_at is None:
        venta.entrega_confirmada_at = fecha or _ahora()
        venta.entrega_confirmada_por_id = usuario.id
        venta.entrega_evidencia = evidencia.strip()[:2000]
    if venta.circuito_estado in (None, "CIERRE_COMERCIAL_CONFIRMADO", "ENTREGA_PENDIENTE"):
        venta.circuito_estado = "ENTREGA_CONFIRMADA"
    db.commit()
    from utils.comisiones_propietario import generar_contado
    generar_contado(db, venta)
    return venta


def confirmar_cobro(db: Session, venta: VentaContado, usuario, evidencia: str, monto: Optional[float] = None,
                    verificar_rol: bool = True) -> VentaContado:
    _humano_interno(usuario)
    if verificar_rol and not (_roles(usuario) & ROLES_COBRO):
        raise ErrorMotor("Confirmar cobros requiere rol de cobranzas o administración", 403)
    if venta.entrega_confirmada_at is None:
        raise ErrorMotor("Pago contra entrega: primero se confirma la entrega", 409)
    if venta.circuito_estado == "COBRO_CONFIRMADO":
        return venta
    if len((evidencia or "").strip()) < 5:
        raise ErrorMotor("Indicá la evidencia del cobro (recibo, comprobante)", 400)
    venta.circuito_estado = "COBRO_CONFIRMADO"
    venta.cobro_estado = "COBRADO"
    venta.cobro_confirmado_por_id = usuario.id
    venta.cobro_evidencia = evidencia.strip()[:2000]
    venta.cobro_fecha = venta.cobro_fecha or _ahora()
    if monto is not None:
        venta.cobro_monto_real = float(monto)
    db.commit()
    return venta


def cobro_no_concretado(db: Session, venta: VentaContado, usuario, motivo: str) -> VentaContado:
    """Se entregó pero el cobro en domicilio no se concretó: queda COBRO_PENDIENTE."""
    _humano_interno(usuario)
    if venta.entrega_confirmada_at is None:
        raise ErrorMotor("Primero se confirma la entrega", 409)
    venta.circuito_estado = "COBRO_PENDIENTE"
    venta.cobro_estado = "PROBLEMA"
    venta.cobro_notas = ((venta.cobro_notas or "") + f"\n{motivo}").strip()[:2000]
    db.commit()
    return venta


def estado_contado_efectivo(v: VentaContado) -> str:
    """Estado del circuito, también para ventas cargadas antes de este circuito (sin circuito_estado)."""
    if v.circuito_estado:
        return v.circuito_estado
    if v.cobro_estado == "COBRADO":
        return "COBRO_CONFIRMADO"
    if v.entrega_confirmada_at:
        return "ENTREGA_CONFIRMADA"
    return "CIERRE_COMERCIAL_CONFIRMADO"


# ── Financiación ──────────────────────────────────────────────────────────────

def _evento(db: Session, exp: ExpedienteFinanciacion, anterior: str, nuevo: str, actor: str, detalle: str = ""):
    db.add(ExpedienteEvento(expediente_id=exp.id, estado_anterior=anterior or "", estado_nuevo=nuevo,
                            actor=actor[:60], detalle=(detalle or "")[:2000]))


def abrir_expediente(db: Session, d: dict, *, agente: Optional[str] = None, usuario=None) -> ExpedienteFinanciacion:
    producto = str(d.get("producto") or "").upper()
    if producto not in PRODUCTOS:
        raise ErrorMotor("Producto inválido (PISCINA, MODULO o VIVIENDA)")
    if agente:
        agente = agente.lower()
        if agente not in AGENTES_APERTURA or producto not in AGENTES_APERTURA[agente]:
            raise ErrorMotor(f"'{agente}' no realiza aperturas de financiación de {producto}", 403)
        actor = f"agente:{agente}"
    else:
        _persona_admision(usuario)
        actor = f"usuario:{usuario.id}"
    if not str(d.get("cliente_nombre") or "").strip():
        raise ErrorMotor("Falta el nombre del cliente")
    datos = {k: v for k, v in (d.get("datos_apertura") or {}).items() if k in CAMPOS_APERTURA}
    descartados = sorted(set((d.get("datos_apertura") or {}).keys()) - CAMPOS_APERTURA)
    lead_id = d.get("lead_id")
    if lead_id:
        abierto = (db.query(ExpedienteFinanciacion)
                   .filter(ExpedienteFinanciacion.lead_id == int(lead_id), ExpedienteFinanciacion.producto == producto,
                           ExpedienteFinanciacion.estado.notin_(["RECHAZADO_POR_ADMISION", "CIERRE_HUMANO_CONFIRMADO"]))
                   .first())
        if abierto:
            return abierto
    exp = ExpedienteFinanciacion(
        lead_id=int(lead_id) if lead_id else None, cliente_nombre=str(d["cliente_nombre"])[:150],
        cliente_telefono=str(d.get("cliente_telefono") or "")[:30], producto=producto,
        modelo=str(d.get("modelo") or "")[:150], valor_cuota_estimado=d.get("valor_cuota_estimado"),
        datos_apertura=datos, estado="CONSULTA_RECIBIDA", abierto_por=actor)
    db.add(exp)
    db.flush()
    _evento(db, exp, "", "CONSULTA_RECIBIDA", actor,
            "Apertura" + (f" · campos no permitidos descartados: {', '.join(descartados)}" if descartados else ""))
    db.commit()
    db.refresh(exp)
    return exp


def cambiar_estado_expediente(db: Session, exp: ExpedienteFinanciacion, nuevo: str, *, agente: Optional[str] = None,
                              usuario=None, detalle: str = "", venta_financiada_id: Optional[int] = None,
                              videollamada_id: Optional[int] = None) -> ExpedienteFinanciacion:
    nuevo = (nuevo or "").upper()
    if nuevo not in ESTADOS_FIN:
        raise ErrorMotor("Estado de financiación inválido")
    anterior = exp.estado
    if agente:
        agente = agente.lower()
        actor = f"agente:{agente}"
        permitido = (agente in AGENTES_APERTURA and agente != "valentina" and exp.producto in AGENTES_APERTURA[agente]
                     and nuevo in TRANSICIONES_IA.get(anterior, set()))
        if not permitido:
            motivo = ("estado reservado a Admisión humana" if nuevo in RESERVADOS_ADMISION
                      else f"transición {anterior} → {nuevo} no permitida a {agente}")
            _evento(db, exp, anterior, anterior, actor, f"INTENTO RECHAZADO → {nuevo}: {motivo}")
            db.commit()
            raise ErrorMotor(f"No autorizado: {motivo}", 403)
    else:
        _persona_admision(usuario)
        actor = f"usuario:{usuario.id}"
        if nuevo in RESERVADOS_ADMISION or anterior in RESERVADOS_ADMISION:
            if "ADMISION" not in _roles(usuario):
                _evento(db, exp, anterior, anterior, actor, f"INTENTO RECHAZADO → {nuevo}: requiere rol ADMISION")
                db.commit()
                raise ErrorMotor("Solo personal de Admisión decide sobre financiaciones", 403)
            if nuevo not in TRANSICIONES_ADMISION.get(anterior, set()):
                raise ErrorMotor(f"Transición {anterior} → {nuevo} inválida", 409)
        elif nuevo not in TRANSICIONES_IA.get(anterior, set()):
            raise ErrorMotor(f"Transición {anterior} → {nuevo} inválida", 409)
        if nuevo in ("APROBADO_POR_ADMISION", "RECHAZADO_POR_ADMISION") and len((detalle or "").strip()) < 5:
            raise ErrorMotor("Registrá el fundamento de la decisión", 400)
        if nuevo == "CIERRE_HUMANO_CONFIRMADO":
            vf = db.get(VentaFinanciada, int(venta_financiada_id or 0)) if venta_financiada_id else None
            if not vf:
                raise ErrorMotor("El cierre requiere la venta financiada formalizada (venta_financiada_id)", 400)
            exp.venta_financiada_id = vf.id
        exp.asignado_admision_id = exp.asignado_admision_id or usuario.id
    if videollamada_id:
        exp.videollamada_id = int(videollamada_id)
    exp.estado = nuevo
    _evento(db, exp, anterior, nuevo, actor, detalle)
    db.commit()
    db.refresh(exp)
    return exp


def confirmar_cuotas_iniciales(db: Session, exp: ExpedienteFinanciacion, usuario, evidencia: str,
                               fecha: Optional[datetime] = None) -> ExpedienteFinanciacion:
    """Pago confirmado de las dos cuotas iniciales → genera la comisión de financiación."""
    _humano_interno(usuario)
    if not (_roles(usuario) & {"ADMISION", "COBRANZAS", "ADMINISTRACION"}):
        raise ErrorMotor("Requiere rol de Admisión, Cobranzas o Administración", 403)
    if exp.estado != "CIERRE_HUMANO_CONFIRMADO" or not exp.venta_financiada_id:
        raise ErrorMotor("Primero Admisión aprueba y formaliza la suscripción", 409)
    if len((evidencia or "").strip()) < 5:
        raise ErrorMotor("Indicá la evidencia del pago de las dos cuotas iniciales", 400)
    if exp.cuotas_iniciales_confirmadas_at is None:
        exp.cuotas_iniciales_confirmadas_at = fecha or _ahora()
        exp.cuotas_iniciales_confirmadas_por_id = usuario.id
        _evento(db, exp, exp.estado, exp.estado, f"usuario:{usuario.id}", f"Dos cuotas iniciales pagas: {evidencia[:500]}")
        db.commit()
    from utils.comisiones_propietario import generar_financiada
    generar_financiada(db, exp)
    return exp


def expediente_dict(e: ExpedienteFinanciacion, eventos: Optional[list] = None, con_datos: bool = True) -> dict:
    d = {"id": e.id, "lead_id": e.lead_id, "cliente_nombre": e.cliente_nombre, "producto": e.producto,
         "modelo": e.modelo, "estado": e.estado, "abierto_por": e.abierto_por,
         "valor_cuota_estimado": e.valor_cuota_estimado, "venta_financiada_id": e.venta_financiada_id,
         "videollamada_id": e.videollamada_id,
         "cuotas_iniciales_confirmadas_at": e.cuotas_iniciales_confirmadas_at.isoformat() if e.cuotas_iniciales_confirmadas_at else None,
         "created_at": e.created_at.isoformat() if e.created_at else None,
         "updated_at": e.updated_at.isoformat() if e.updated_at else None}
    if con_datos:
        d["cliente_telefono"] = e.cliente_telefono
        d["datos_apertura"] = e.datos_apertura or {}
    if eventos is not None:
        d["eventos"] = [{"de": x.estado_anterior, "a": x.estado_nuevo, "actor": x.actor, "detalle": x.detalle,
                         "ts": x.created_at.isoformat() if x.created_at else None} for x in eventos]
    return d
