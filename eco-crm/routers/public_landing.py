"""
Endpoint público (sin API key) para recibir leads de landings de campaña
externas — por ejemplo landing-financiacion (Promo Mundial), que es un
sitio estático sin backend propio y no puede guardar la API key del CRM
de forma segura en el navegador.

Este router NO reemplaza /api/leads (que sigue siendo el endpoint
"oficial" con X-Api-Key para integraciones internas/agentes). Este es
un endpoint angosto, de un solo propósito, con rate limiting propio
porque no requiere autenticación.
"""
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Lead, Usuario
from routers.leads import asignar_asesor_round_robin, _notificar_asesor_lead_nuevo

log = logging.getLogger(__name__)
router = APIRouter()

# Rate limit simple en memoria (por IP): máx 5 envíos cada 10 minutos.
# Se reinicia en cada deploy — suficiente para frenar abuso de un
# formulario público sin agregar infraestructura nueva.
_RATE_LIMIT_WINDOW_SEG = 600
_RATE_LIMIT_MAX = 5
_hits: dict[str, list[float]] = defaultdict(list)


class LandingLeadIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    telefono: str = Field(..., min_length=6, max_length=40)
    localidad: str = Field("", max_length=120)
    interes: str = Field("", max_length=120)
    mensaje: str = Field("", max_length=1000)
    origen: str = Field("LANDING_PROMO_MUNDIAL", max_length=60)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/api/public/landing-lead")
async def crear_lead_landing(payload: LandingLeadIn, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < _RATE_LIMIT_WINDOW_SEG]
    if len(_hits[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(429, "Demasiados envíos desde esta conexión. Probá de nuevo en unos minutos.")
    _hits[ip].append(now)

    asesor_id = asignar_asesor_round_robin(db)

    lead = Lead(
        nombre=payload.nombre.strip(),
        telefono=payload.telefono.strip(),
        localidad=payload.localidad.strip(),
        producto_interes=payload.interes.strip() or "SIN_DEFINIR",
        forma_pago="SIN_DEFINIR",
        estado="NUEVO",
        asesor_apertura_id=asesor_id,
        origen=payload.origen.strip() or "LANDING_PROMO_MUNDIAL",
        notas=payload.mensaje.strip(),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    if asesor_id:
        asesor = db.query(Usuario).filter(Usuario.id == asesor_id).first()
        if asesor:
            try:
                _notificar_asesor_lead_nuevo(db, asesor, lead)
            except Exception:
                log.exception("No se pudo notificar al asesor del lead de landing (lead igual se creó)")

    return {"ok": True}
