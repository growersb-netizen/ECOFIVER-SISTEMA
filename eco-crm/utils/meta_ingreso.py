"""Persistencia y distribución de formularios Meta, independiente de WhatsApp."""
import json
import re

from fastapi import HTTPException
from sqlalchemy import func, or_, text
from database.models import Aliado, ConfiguracionSistema, Interaccion, Lead, Usuario

FINALIZADOS = ("CERRADO_GANADO", "CERRADO_PERDIDO", "INACTIVO", "CERRADO", "PERDIDO")


def _serializar_ingreso(db):
    """Serializa deduplicación y elección por carga hasta el commit del ingreso.

    La llave es global del canal: dos eventos diferentes también deben observar
    la carga que dejó el anterior. No requiere cambio de esquema.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(573121828423)"))
    elif dialect == "sqlite":
        connection = db.connection().connection.driver_connection
        if not connection.in_transaction:
            db.execute(text("BEGIN IMMEDIATE"))


def _elegir_responsable(db):
    cfg = db.query(ConfiguracionSistema).filter_by(clave="leads_rr_asesores").first()
    pool = None
    if cfg and cfg.valor:
        try:
            values = json.loads(cfg.valor)
            if not isinstance(values, list):
                raise ValueError("El pool debe ser una lista")
            pool = {int(i) for i in values}
        except (ValueError, TypeError):
            pool = set()  # Una configuración inválida no habilita a todo el equipo.
    candidates = []
    for user in db.query(Usuario).filter_by(activo=True).all():
        try:
            roles = json.loads(user.roles_json or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(roles, list):
            continue
        if user.aliado_codigo or not {"ASESOR_APERTURA", "SUPERVISOR_CIERRE"}.intersection(roles):
            continue
        if pool is not None and user.id not in pool:
            continue
        carga = db.query(Lead).filter(Lead.asesor_apertura_id == user.id,
                                     or_(Lead.estado.is_(None), Lead.estado.notin_(FINALIZADOS))).count()
        candidates.append((carga, f"asesor:{user.id:010d}", user.id, None))
    # El contrato habilita la operativa; la cuenta permite trabajar el lead.
    for aliado in db.query(Aliado).filter_by(estado="activo", contrato_firmado=True).all():
        if not aliado.password_hash:
            continue
        carga = db.query(Lead).filter(Lead.aliado_codigo == aliado.codigo,
                                     or_(Lead.estado.is_(None), Lead.estado.notin_(FINALIZADOS))).count()
        candidates.append((carga, f"aliado:{aliado.codigo}", None, aliado.codigo))
    return min(candidates) if candidates else None


def _telefono_sin_separadores(column):
    """Compara formatos históricos sin reescribirlos ni inferir prefijos."""
    expression = column
    for separator in ("+", " ", "-", "(", ")", ".", "\t", "\r", "\n"):
        expression = func.replace(expression, separator, "")
    return expression


def registrar_formulario_meta(db, data):
    if not isinstance(data, dict):
        raise HTTPException(422, "El formulario debe ser un objeto")
    meta_id = str(data.get("meta_lead_id") or "").strip()
    telefono = re.sub(r"\D", "", str(data.get("telefono") or ""))
    session_id = f"meta:{meta_id}" if meta_id else telefono
    if not session_id:
        raise HTTPException(422, "Se requiere meta_lead_id o teléfono")
    if len(session_id) > 100 or len(telefono) > 30:
        raise HTTPException(422, "Identificador o teléfono demasiado largo")
    marker = f"Meta Ads | ID:{meta_id or 'telefono:' + telefono} |"
    metadata = json.dumps(data, ensure_ascii=False)
    _serializar_ingreso(db)
    try:
        # La interacción conserva el ID del evento aunque se editen las notas
        # del lead o se reciba otro formulario para el mismo teléfono.
        event = db.query(Interaccion).filter(
            Interaccion.tipo == "NOTA", Interaccion.notas.startswith(marker, autoescape=True)
        ).first()
        existing = db.get(Lead, event.lead_id) if event else None
        if not existing:
            existing = db.query(Lead).filter(Lead.session_id == session_id).first()
        if not existing and meta_id:
            existing = db.query(Lead).filter(Lead.notas.contains(marker, autoescape=True)).first()
        if not existing and telefono:
            existing = db.query(Lead).filter(
                (Lead.session_id == telefono) | (_telefono_sin_separadores(Lead.telefono) == telefono)
            ).order_by(Lead.id).first()
        creado = existing is None
        elegido = None
        if creado:
            existing = Lead(
                session_id=session_id, nombre=str(data.get("nombre") or f"Lead Meta {meta_id}")[:150],
                telefono=telefono, localidad=str(data.get("ciudad") or "")[:100],
                producto_interes=str(data.get("producto_interes") or "SIN_DEFINIR").upper()[:20],
                forma_pago="SIN_DEFINIR", estado="NUEVO", origen="META_ADS",
                canal_ingreso="crm", agente_asignado="valentina",
                utm_source="facebook", utm_medium="lead_ads",
                utm_campaign=str(data.get("ad_name") or "")[:150],
                notas=f"{marker} Formulario: {data.get('form_id', '')}\n{metadata}",
            )
            db.add(existing)
        # No se altera una asignación o gestión existente. Un lead histórico sin
        # responsable sí entra a distribución al llegar su formulario.
        if not existing.asesor_apertura_id and not existing.aliado_codigo:
            elegido = _elegir_responsable(db)
            if elegido:
                existing.asesor_apertura_id = elegido[2]
                existing.aliado_codigo = elegido[3]
        db.flush()
        if not event:
            responsable = (f"asesor:{existing.asesor_apertura_id}" if existing.asesor_apertura_id
                           else f"aliado:{existing.aliado_codigo}" if existing.aliado_codigo
                           else "SIN RESPONSABLE: no hay destinatarios habilitados")
            db.add(Interaccion(lead_id=existing.id, tipo="NOTA", resultado="ENVIADO",
                               notas=f"{marker} Ingreso formulario. Asignación: {responsable}\n{metadata}",
                               asesor_id=existing.asesor_apertura_id))
        elif elegido:
            db.add(Interaccion(lead_id=existing.id, tipo="NOTA", resultado="ENVIADO",
                               notas=f"Formulario Meta: asignación pendiente resuelta a {elegido[1]}",
                               asesor_id=existing.asesor_apertura_id))
        db.commit()
        db.refresh(existing)
        existing.meta_created = creado
        existing.meta_duplicate_event = event is not None
        return existing
    except Exception:
        db.rollback()
        raise
