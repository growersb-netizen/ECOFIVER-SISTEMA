"""
Seguimiento público de entrega — acceso sin login.
URL: /seguimiento/{token}

El token se genera en el lead cuando la entrega pasa a estado INSTALADA.
El cliente puede ver el estado de su instalación y dejar una reseña.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Lead, Entrega, VentaContado

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_lead_by_token(token: str, db: Session) -> Lead:
    lead = db.query(Lead).filter(Lead.seguimiento_token == token).first()
    if not lead:
        raise HTTPException(404, "Token de seguimiento inválido o expirado")
    return lead


@router.get("/seguimiento/{token}", response_class=HTMLResponse)
async def seguimiento_page(token: str, request: Request, db: Session = Depends(get_db)):
    """Página pública de seguimiento de entrega del cliente."""
    lead = _get_lead_by_token(token, db)

    # Buscar entrega asociada por teléfono
    entrega_info = None
    if lead.telefono:
        vc = db.query(VentaContado).filter(
            VentaContado.cliente_telefono == lead.telefono
        ).order_by(VentaContado.id.desc()).first()
        if vc:
            entrega = db.query(Entrega).filter(
                Entrega.venta_contado_id == vc.id
            ).order_by(Entrega.id.desc()).first()
            if entrega:
                entrega_info = {
                    "estado": entrega.estado or "COORDINADA",
                    "producto": entrega.producto or lead.modelo_especifico or "",
                    "fecha_instalacion": entrega.fecha_instalacion.strftime("%d/%m/%Y") if entrega.fecha_instalacion else None,
                    "rango_horario": entrega.rango_horario or "",
                    "equipo_asignado": entrega.equipo_asignado or "",
                    "localidad": entrega.cliente_localidad or lead.localidad or "",
                }

    return templates.TemplateResponse("seguimiento.html", {
        "request": request,
        "lead": {
            "nombre": lead.nombre,
            "producto": lead.producto_interes,
            "modelo": lead.modelo_especifico or "",
            "localidad": lead.localidad or "",
        },
        "entrega": entrega_info,
        "token": token,
    })


@router.get("/api/seguimiento/{token}")
async def get_seguimiento_data(token: str, db: Session = Depends(get_db)):
    """API pública para obtener datos de seguimiento (usado por el JS de la página)."""
    lead = _get_lead_by_token(token, db)

    entrega_info = None
    if lead.telefono:
        vc = db.query(VentaContado).filter(
            VentaContado.cliente_telefono == lead.telefono
        ).order_by(VentaContado.id.desc()).first()
        if vc:
            entrega = db.query(Entrega).filter(
                Entrega.venta_contado_id == vc.id
            ).order_by(Entrega.id.desc()).first()
            if entrega:
                entrega_info = {
                    "estado": entrega.estado or "COORDINADA",
                    "producto": entrega.producto or "",
                    "fecha_instalacion": entrega.fecha_instalacion.isoformat() if entrega.fecha_instalacion else None,
                    "rango_horario": entrega.rango_horario or "",
                    "equipo_asignado": entrega.equipo_asignado or "",
                    "localidad": entrega.cliente_localidad or "",
                    "notas_cliente": entrega.notas or "",
                }

    return {
        "nombre": lead.nombre,
        "producto": lead.producto_interes,
        "modelo": lead.modelo_especifico or "",
        "localidad": lead.localidad or "",
        "entrega": entrega_info,
    }
