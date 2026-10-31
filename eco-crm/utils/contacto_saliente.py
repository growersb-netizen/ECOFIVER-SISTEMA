"""
Autorización de cada contacto saliente iniciado por el sistema (WhatsApp).

Un mensaje de texto libre iniciado por la empresa solo se entrega dentro de las
24 h desde el último mensaje del cliente (política de WhatsApp Cloud API); fuera
de esa ventana hace falta una plantilla aprobada por Meta. Meta acepta el envío
(HTTP 200) y la falla llega después: por eso se verifica ANTES de enviar.

Reglas (en orden): sin baja comercial · dentro de la ventana de 24 h · sin otro
contacto proactivo al mismo teléfono en las últimas 20 h (evita seguimientos
duplicados entre tareas). Si se autoriza, queda registrado.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import ContactoProactivo, InboxMensaje
from utils import exclusiones

VENTANA_WA_H = 24
DEDUPE_H = 20


def _n(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt is not None and dt.tzinfo else dt


def ultimo_entrante(db: Session, clave: str) -> Optional[datetime]:
    m = (db.query(InboxMensaje)
         .filter(InboxMensaje.direccion == "IN", InboxMensaje.phone.like(f"%{clave}"))
         .order_by(InboxMensaje.created_at.desc()).first())
    return _n(m.created_at) if m else None


def _config(db: Session, clave: str, defecto: str) -> str:
    try:
        from routers.configuracion import get_config_value
        v = get_config_value(clave, db)
    except Exception:
        v = None
    return (v or defecto).strip()


def plantillas_habilitadas(db: Session) -> bool:
    return _config(db, "wa_plantillas_habilitadas", "no").lower() in ("si", "sí", "true", "1", "on")


def _plantillas_hoy(db: Session, ahora: datetime) -> int:
    inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    return (db.query(ContactoProactivo)
            .filter(ContactoProactivo.origen.like("plantilla:%"), ContactoProactivo.created_at >= inicio).count())


def autorizar(db: Session, telefono: str, origen: str = "", agente: str = "",
              ahora: Optional[datetime] = None, con_plantilla: bool = False, contractual: bool = False) -> dict:
    """modo='texto' (dentro de la ventana) o modo='plantilla' (fuera de ella, si el propietario habilitó
    las plantillas y quedan del tope diario). contractual=True: aviso de servicio pedido por el cliente
    (recordatorio de videollamada o de cuota): no lo frenan la baja comercial ni la deduplicación."""
    ahora = ahora or datetime.utcnow()
    clave = exclusiones.clave_telefono(telefono)
    if not clave:
        return {"permitido": False, "motivo": "telefono_invalido"}
    if not contractual and exclusiones.esta_excluido(db, telefono):
        return {"permitido": False, "motivo": "baja_comercial"}
    ult_in = ultimo_entrante(db, clave)
    en_ventana = ult_in is not None and ahora - ult_in <= timedelta(hours=VENTANA_WA_H)
    if contractual:
        if en_ventana:
            return {"permitido": True, "modo": "texto"}
        if con_plantilla and plantillas_habilitadas(db):
            return {"permitido": True, "modo": "plantilla"}
        return {"permitido": False, "motivo": "fuera_de_ventana_24h"}
    if not en_ventana and not (con_plantilla and plantillas_habilitadas(db)):
        return {"permitido": False, "motivo": "fuera_de_ventana_24h",
                "detalle": "Requiere plantilla aprobada por Meta (el cliente no escribió en las últimas 24 h)",
                "ultimo_entrante": ult_in.isoformat() if ult_in else None}
    reciente = (db.query(ContactoProactivo)
                .filter(ContactoProactivo.telefono_clave == clave,
                        ContactoProactivo.created_at >= ahora - timedelta(hours=DEDUPE_H)).first())
    if reciente:
        return {"permitido": False, "motivo": "contactado_recientemente", "por": reciente.origen}
    modo = "texto" if en_ventana else "plantilla"
    if modo == "plantilla":
        try:
            tope = int(_config(db, "wa_plantillas_max_dia", "40"))
        except ValueError:
            tope = 40
        if _plantillas_hoy(db, ahora) >= tope:
            return {"permitido": False, "motivo": "tope_diario_plantillas", "tope": tope}
    db.add(ContactoProactivo(telefono_clave=clave, origen=(("plantilla:" if modo == "plantilla" else "") + (origen or ""))[:80],
                             agente=(agente or "")[:30]))
    db.commit()
    return {"permitido": True, "modo": modo}
