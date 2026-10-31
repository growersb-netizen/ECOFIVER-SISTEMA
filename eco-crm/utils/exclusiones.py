"""
Bajas de comunicaciones comerciales.

Una baja bloquea los contactos automáticos comerciales (seguimientos, nutrición,
reactivación, primer contacto, pedido de testimonio). No bloquea responder cuando
el contacto escribe por iniciativa propia, ni avisos contractuales (cobranza de
cuotas, recordatorio de una videollamada que el cliente agendó).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database.models import ExclusionComercial


def clave_telefono(tel: Optional[str]) -> str:
    """Últimos 10 dígitos (número nacional argentino): '+54 9 11 3516-4644' == '1135164644'.
    '' si no parece un teléfono."""
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) < 8:
        return ""
    return digitos[-10:]


def exclusion_activa(db: Session, tel: Optional[str]) -> Optional[ExclusionComercial]:
    clave = clave_telefono(tel)
    if not clave:
        return None
    return (db.query(ExclusionComercial)
            .filter(ExclusionComercial.telefono_clave == clave, ExclusionComercial.activa == True)  # noqa: E712
            .first())


def esta_excluido(db: Session, tel: Optional[str]) -> bool:
    return exclusion_activa(db, tel) is not None


def claves_excluidas(db: Session) -> set[str]:
    filas = (db.query(ExclusionComercial.telefono_clave)
             .filter(ExclusionComercial.activa == True)  # noqa: E712
             .all())
    return {f[0] for f in filas}


def sin_excluidos(db: Session, leads: Iterable) -> list:
    """Filtra leads (modelos con .telefono) cuyo teléfono tiene baja activa."""
    excluidas = claves_excluidas(db)
    leads = list(leads)
    if not excluidas:
        return leads
    return [l for l in leads if clave_telefono(getattr(l, "telefono", "")) not in excluidas]


def registrar_baja(db: Session, tel: str, lead_id: Optional[int] = None, canal: str = "",
                   texto: str = "") -> tuple[Optional[ExclusionComercial], bool]:
    """Registra (o reactiva) la baja. Devuelve (exclusión, ya_existia_activa)."""
    clave = clave_telefono(tel)
    if not clave:
        return None, False
    ex = db.query(ExclusionComercial).filter(ExclusionComercial.telefono_clave == clave).first()
    if ex and ex.activa:
        return ex, True
    if ex is None:
        ex = ExclusionComercial(telefono_clave=clave)
        db.add(ex)
    ex.telefono = (tel or "")[:30]
    ex.lead_id = lead_id
    ex.canal = (canal or "")[:30]
    ex.texto = (texto or "")[:300]
    ex.activa = True
    ex.reactivada_por = None
    ex.motivo_reactivacion = None
    db.commit()
    db.refresh(ex)
    return ex, False
