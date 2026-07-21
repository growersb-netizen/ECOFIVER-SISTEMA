"""
Testimonios públicos — formulario para que el cliente deje su reseña.
URL: /testimonial/{token}
POST /api/testimonial/{token}

El token es el mismo que el de seguimiento (Lead.seguimiento_token).
La reseña se guarda en el CRM y se puede usar para la web.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Lead, ConfiguracionSistema

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_lead_by_token(token: str, db: Session) -> Lead:
    lead = db.query(Lead).filter(Lead.seguimiento_token == token).first()
    if not lead:
        raise HTTPException(404, "Token inválido o expirado")
    return lead


@router.get("/testimonial/{token}", response_class=HTMLResponse)
async def testimonial_page(token: str, request: Request, db: Session = Depends(get_db)):
    """Formulario público para dejar testimonio."""
    lead = _get_lead_by_token(token, db)
    ya_dejo = bool(lead.notas and "[TESTIMONIO]" in lead.notas)
    return templates.TemplateResponse("testimonial.html", {
        "request": request,
        "nombre": lead.nombre,
        "producto": lead.modelo_especifico or lead.producto_interes or "",
        "token": token,
        "ya_dejo": ya_dejo,
    })


@router.post("/api/testimonial/{token}")
async def guardar_testimonial(token: str, request: Request, db: Session = Depends(get_db)):
    """Guarda la reseña del cliente en el lead."""
    lead = _get_lead_by_token(token, db)

    data = await request.json()
    estrellas = int(data.get("estrellas", 5))
    comentario = data.get("comentario", "").strip()
    nombre_publico = data.get("nombre_publico", lead.nombre).strip()
    localidad = data.get("localidad", lead.localidad or "").strip()

    if not comentario:
        raise HTTPException(400, "El comentario es requerido")

    if estrellas < 1 or estrellas > 5:
        estrellas = 5

    # Guardar en notas del lead
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    nota_testimonial = (
        f"\n[TESTIMONIO {ts}]\n"
        f"⭐ {'★' * estrellas}\n"
        f"Nombre: {nombre_publico}\n"
        f"Localidad: {localidad}\n"
        f"Comentario: {comentario}"
    )
    lead.notas = (lead.notas or "") + nota_testimonial
    db.commit()

    # Guardar también en ConfiguracionSistema como colección de testimonios
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "testimonios_clientes"
    ).first()

    testimonios = []
    if cfg:
        try:
            testimonios = json.loads(cfg.valor or "[]")
        except Exception:
            testimonios = []

    testimonios.append({
        "fecha": ts,
        "nombre": nombre_publico,
        "localidad": localidad,
        "producto": lead.modelo_especifico or lead.producto_interes or "",
        "estrellas": estrellas,
        "comentario": comentario,
        "aprobado": False,  # se aprueba manualmente para publicar en web
    })

    nuevo_valor = json.dumps(testimonios, ensure_ascii=False)
    if cfg:
        cfg.valor = nuevo_valor
    else:
        db.add(ConfiguracionSistema(clave="testimonios_clientes", valor=nuevo_valor))
    db.commit()

    return {"ok": True, "mensaje": "¡Gracias por tu reseña! 🎉"}


@router.get("/api/testimonios/publicos")
async def get_testimonios_publicos(db: Session = Depends(get_db)):
    """Lista de testimonios aprobados — para la web pública."""
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "testimonios_clientes"
    ).first()
    if not cfg:
        return {"testimonios": []}
    try:
        todos = json.loads(cfg.valor or "[]")
        aprobados = [t for t in todos if t.get("aprobado", False)]
        return {"testimonios": aprobados}
    except Exception:
        return {"testimonios": []}


@router.get("/api/testimonios/admin")
async def get_testimonios_admin(db: Session = Depends(get_db), request: Request = None):
    """Lista COMPLETA de testimonios — para el panel de admin."""
    from routers.auth import require_auth, get_user_roles
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "testimonios_clientes"
    ).first()
    if not cfg:
        return {"testimonios": []}
    try:
        todos = json.loads(cfg.valor or "[]")
        return {"testimonios": todos, "total": len(todos), "pendientes": sum(1 for t in todos if not t.get("aprobado"))}
    except Exception:
        return {"testimonios": []}


@router.post("/api/testimonios/{idx}/aprobar")
async def aprobar_testimonio(idx: int, db: Session = Depends(get_db)):
    """Aprueba un testimonio para que aparezca en la web."""
    cfg = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == "testimonios_clientes"
    ).first()
    if not cfg:
        raise HTTPException(404, "No hay testimonios")
    testimonios = json.loads(cfg.valor or "[]")
    if idx >= len(testimonios):
        raise HTTPException(404, "Testimonio no encontrado")
    testimonios[idx]["aprobado"] = True
    cfg.valor = json.dumps(testimonios, ensure_ascii=False)
    db.commit()
    return {"ok": True}
