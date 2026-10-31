"""Recepción durable y round robin explícito por campaña y producto Meta."""
import json
import re

from fastapi import HTTPException
from sqlalchemy import func, or_, text
from database.models import (
    Aliado, ConfiguracionSistema, Interaccion, Lead, Usuario,
    MetaLeadCampana, MetaLeadDestino, MetaLeadOrganizacion, MetaLeadRecepcion,
)

PLAN_18_FORM_ID = "1122869520123560"
PLAN_18_PAGE_ID = "634872006383162"


def seed_campanas_meta(db):
    """Registra el formulario verificado sin habilitar vendedores por defecto."""
    if not db.get(MetaLeadCampana, PLAN_18_FORM_ID):
        db.add(MetaLeadCampana(form_id=PLAN_18_FORM_ID, page_id=PLAN_18_PAGE_ID,
                              nombre="Plan 18 Pasos", producto="MODULO", activa=True))
        db.flush()


def _serializar_ingreso(db):
    """Cursor, deduplicación y preferencias se leen en una sola transacción."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(573121828423)"))
    elif db.get_bind().dialect.name == "sqlite":
        connection = db.connection().connection.driver_connection
        if not connection.in_transaction:
            db.execute(text("BEGIN IMMEDIATE"))


def _organizacion_aliado(aliado):
    return aliado.codigo if aliado.es_organizador or aliado.codigo == "AL-010" else aliado.organizacion_codigo


def candidatos_meta(db, campana):
    """Destinatarios aptos ordenados: (clave, asesor_id, aliado_codigo)."""
    if not campana or not campana.activa or campana.producto not in ("MODULO", "PISCINA"):
        return []
    producto_flag = MetaLeadDestino.modulos if campana.producto == "MODULO" else MetaLeadDestino.piscinas
    prefs = db.query(MetaLeadDestino).filter(MetaLeadDestino.habilitado.is_(True),
                                            producto_flag.is_(True)).all()
    elegibles = []
    for pref in prefs:
        tipo, _, identifier = pref.clave.partition(":")
        if tipo == "asesor" and identifier.isdigit():
            user = db.get(Usuario, int(identifier))
            if (not user or not user.activo or not user.password_hash or user.aliado_codigo
                    or user.es_agente_ia):
                continue
            try:
                roles = json.loads(user.roles_json or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(roles, list) or not {"ASESOR_APERTURA", "SUPERVISOR_CIERRE"}.intersection(roles):
                continue
            elegibles.append((pref.clave, user.id, None))
        elif tipo == "aliado" and identifier:
            aliado = db.query(Aliado).filter_by(codigo=identifier, estado="activo").first()
            if not aliado or not aliado.password_hash:
                continue
            org = _organizacion_aliado(aliado)
            if org:
                gate = db.get(MetaLeadOrganizacion, (campana.form_id, org))
                if not gate or not gate.habilitada:
                    continue
            elegibles.append((pref.clave, None, aliado.codigo))
    return sorted(elegibles, key=lambda item: item[0])


def _elegir_responsable(db, campana):
    candidatos = candidatos_meta(db, campana)
    if not candidatos:
        return None
    cursor_key = f"meta_rr_cursor:{campana.form_id}"
    cursor = db.query(ConfiguracionSistema).filter_by(clave=cursor_key).first()
    ultimo = cursor.valor if cursor else ""
    elegido = next((c for c in candidatos if c[0] > (ultimo or "")), candidatos[0])
    if cursor:
        cursor.valor = elegido[0]
    else:
        db.add(ConfiguracionSistema(clave=cursor_key, valor=elegido[0], es_secreto=False,
                                    categoria="meta", estado="activa"))
    db.flush()  # SessionLocal desactiva autoflush; el siguiente turno debe ver el cursor.
    return elegido


def _telefono_sin_separadores(column):
    expression = column
    for separator in ("+", " ", "-", "(", ")", ".", "\t", "\r", "\n"):
        expression = func.replace(expression, separator, "")
    return expression


def _campana(db, form_id, datos):
    campaign = db.get(MetaLeadCampana, form_id) if form_id else None
    page_id = str(datos.get("page_id") or "")
    if campaign and page_id and page_id != campaign.page_id:
        return None
    return campaign


def _asignar(db, lead, campana, *, contexto="Ingreso formulario"):
    # Una pausa sólo afecta futuros ingresos/pendientes, nunca quita el trabajo
    # ya asignado ni vuelve a distribuir la gestión de un cliente existente.
    if lead.asesor_apertura_id or lead.aliado_codigo or lead.estado != "NUEVO":
        return None
    elegido = _elegir_responsable(db, campana)
    if elegido:
        if not lead.producto_interes or lead.producto_interes in ("SIN_DEFINIR", "GENERAL"):
            lead.producto_interes = campana.producto
        lead.asesor_apertura_id, lead.aliado_codigo = elegido[1], elegido[2]
        db.add(Interaccion(lead_id=lead.id, tipo="NOTA", resultado="ENVIADO",
                           notas=f"{contexto}. Round robin {campana.nombre} ({campana.form_id}): {elegido[0]}",
                           asesor_id=elegido[1]))
    return elegido


def registrar_formulario_meta(db, data):
    if not isinstance(data, dict):
        raise HTTPException(422, "El formulario debe ser un objeto")
    meta_id = str(data.get("meta_lead_id") or "").strip()
    telefono = re.sub(r"\D", "", str(data.get("telefono") or ""))
    event_id = meta_id or (f"telefono:{telefono}" if telefono else "")
    session_id = f"meta:{meta_id}" if meta_id else telefono
    form_id = str(data.get("form_id") or "").strip()
    if not event_id:
        raise HTTPException(422, "Se requiere meta_lead_id o teléfono")
    if len(session_id) > 100 or len(event_id) > 100 or len(telefono) > 30 or len(form_id) > 50:
        raise HTTPException(422, "Identificador o teléfono demasiado largo")
    marker = f"Meta Ads | ID:{event_id} |"
    metadata = json.dumps(data, ensure_ascii=False)
    _serializar_ingreso(db)
    try:
        db.flush()
        receipt = db.get(MetaLeadRecepcion, event_id)
        # Compatibilidad con los ingresos anteriores a la tabla de recepciones.
        event = db.query(Interaccion).filter(
            Interaccion.tipo == "NOTA", Interaccion.notas.startswith(marker, autoescape=True)
        ).first() if not receipt else None
        existing = db.get(Lead, receipt.lead_id) if receipt else db.get(Lead, event.lead_id) if event else None
        if not existing:
            existing = db.query(Lead).filter(Lead.session_id == session_id).first()
        if not existing and meta_id:
            existing = db.query(Lead).filter(Lead.notas.contains(marker, autoescape=True)).first()
        if not existing and telefono:
            existing = db.query(Lead).filter(
                (Lead.session_id == telefono) | (_telefono_sin_separadores(Lead.telefono) == telefono)
            ).order_by(Lead.id).first()
        creado = existing is None
        campaign = _campana(db, form_id, data)
        if creado:
            producto = campaign.producto if campaign else "SIN_DEFINIR"
            existing = Lead(
                session_id=session_id, nombre=str(data.get("nombre") or f"Lead Meta {meta_id}")[:150],
                telefono=telefono, localidad=str(data.get("ciudad") or "")[:100],
                producto_interes=producto, forma_pago="SIN_DEFINIR", estado="NUEVO", origen="META_ADS",
                canal_ingreso="crm", agente_asignado="valentina", utm_source="facebook", utm_medium="lead_ads",
                utm_campaign=str(data.get("ad_name") or "")[:150],
                notas=f"{marker} Formulario: {form_id}\n{metadata}")
            db.add(existing)
            db.flush()
        duplicate = receipt is not None or event is not None
        if not receipt:
            db.add(MetaLeadRecepcion(meta_lead_id=event_id, lead_id=existing.id,
                                    form_id=form_id, datos_json=metadata))
        if not duplicate:
            db.add(Interaccion(lead_id=existing.id, tipo="NOTA", resultado="ENVIADO",
                               notas=f"{marker} Ingreso formulario {form_id}\n{metadata}"))
        elegido = _asignar(db, existing, campaign)
        if not elegido and not existing.asesor_apertura_id and not existing.aliado_codigo and not duplicate:
            db.add(Interaccion(lead_id=existing.id, tipo="NOTA", resultado="ENVIADO",
                               notas=f"SIN RESPONSABLE: pendiente de reparto Meta; formulario {form_id}. "
                                     "No hay campaña activa/destinatarios habilitados o ya tiene gestión."))
        db.commit()
        db.refresh(existing)
        existing.meta_created = creado
        existing.meta_duplicate_event = duplicate
        return existing
    except Exception:
        db.rollback()
        raise


def repartir_pendientes(db, form_id=None, limite=500, organizacion_codigo=None):
    """Reparte sólo NUEVOS sin responsable respetando el mismo cursor de ingreso.

    Si el solicitante es una organización, sólo se revisan sus campañas
    habilitadas; el pool sigue siendo global para no saltarse turnos de otros.
    La función confirma también los toggles pendientes en la misma transacción.
    """
    if not isinstance(limite, int) or isinstance(limite, bool) or not 1 <= limite <= 500:
        raise HTTPException(422, "El límite debe estar entre 1 y 500")
    _serializar_ingreso(db)
    try:
        db.flush()
        q = db.query(MetaLeadRecepcion).join(Lead, Lead.id == MetaLeadRecepcion.lead_id).filter(
            Lead.asesor_apertura_id.is_(None), or_(Lead.aliado_codigo.is_(None), Lead.aliado_codigo == ""),
            Lead.estado == "NUEVO")
        if form_id:
            q = q.filter(MetaLeadRecepcion.form_id == form_id)
        if organizacion_codigo:
            q = q.join(MetaLeadOrganizacion, MetaLeadOrganizacion.form_id == MetaLeadRecepcion.form_id).filter(
                MetaLeadOrganizacion.organizacion_codigo == organizacion_codigo,
                MetaLeadOrganizacion.habilitada.is_(True))
        total = q.with_entities(Lead.id).distinct().count()
        # Los formularios desconocidos/pausados no deben bloquear la cola útil
        # si hay más de `limite` recepciones pendientes de configuración.
        active_forms = [c.form_id for c in db.query(MetaLeadCampana).filter_by(activa=True).all()
                        if candidatos_meta(db, c)]
        records = (q.filter(MetaLeadRecepcion.form_id.in_(active_forms))
                   .order_by(MetaLeadRecepcion.created_at, MetaLeadRecepcion.meta_lead_id)
                   .limit(limite).all())
        assigned = []
        assigned_org = 0
        for record in records:
            lead = db.get(Lead, record.lead_id)
            try:
                datos = json.loads(record.datos_json)
            except (ValueError, TypeError):
                datos = {}
            campaign = _campana(db, record.form_id, datos)
            elegido = _asignar(db, lead, campaign, contexto="Asignación de pendiente")
            if elegido:
                assigned.append(lead.id)
                if organizacion_codigo and elegido[2]:
                    al = db.query(Aliado).filter_by(codigo=elegido[2]).first()
                    if al and _organizacion_aliado(al) == organizacion_codigo:
                        assigned_org += 1
        db.commit()
        return {"total": total, "asignados": len(assigned), "pendientes": total - len(assigned),
                "lead_ids": assigned, "asignados_organizacion": assigned_org}
    except Exception:
        db.rollback()
        raise
