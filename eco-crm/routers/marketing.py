"""
Panel de Marketing — Dashboard unificado de desempeño comercial y digital.
Agrega: Ecopost, MercadoLibre, Leads WhatsApp, Agentes IA.
Acceso: ADMIN | COORDINADOR_OPERATIVO
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ContenidoEcopost, Lead, PublicacionML, Usuario
from routers.auth import require_auth, get_user_roles
from utils.ai_client import ai_complete

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ROLES_MARKETING = ["ADMIN", "COORDINADOR_OPERATIVO"]


def _check(current_user: Usuario):
    roles = get_user_roles(current_user)
    if not any(r in roles for r in ROLES_MARKETING):
        from fastapi import HTTPException
        raise HTTPException(403, "Sin permisos para Marketing")
    return roles


# ─── PÁGINA ───────────────────────────────────────────────────────────────────

@router.get("/marketing", response_class=HTMLResponse)
async def marketing_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    roles = _check(current_user)
    return templates.TemplateResponse("marketing.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


# ─── API — DASHBOARD COMPLETO ─────────────────────────────────────────────────

@router.get("/api/marketing/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    _check(current_user)

    hoy   = datetime.now()
    ayer  = hoy - timedelta(days=1)
    s7    = hoy - timedelta(days=7)
    s30   = hoy - timedelta(days=30)

    # ── Ecopost ──────────────────────────────────────────────────────────────
    total_post    = db.query(ContenidoEcopost).count()
    publicados    = db.query(ContenidoEcopost).filter(ContenidoEcopost.estado == "publicado").count()
    aprobados     = db.query(ContenidoEcopost).filter(ContenidoEcopost.estado == "aprobado").count()
    borradores    = db.query(ContenidoEcopost).filter(ContenidoEcopost.estado == "borrador").count()
    posts_7d      = db.query(ContenidoEcopost).filter(ContenidoEcopost.created_at >= s7).count()
    posts_recientes = (
        db.query(ContenidoEcopost)
        .order_by(ContenidoEcopost.created_at.desc())
        .limit(5)
        .all()
    )

    # Por tipo
    tipos_raw = db.query(ContenidoEcopost.tipo).all()
    tipos_count = {}
    for (t,) in tipos_raw:
        tipos_count[t or "flyer"] = tipos_count.get(t or "flyer", 0) + 1

    # ── Leads WhatsApp ────────────────────────────────────────────────────────
    leads_total    = db.query(Lead).count()
    leads_hoy      = db.query(Lead).filter(Lead.created_at >= hoy.replace(hour=0, minute=0, second=0)).count()
    leads_7d       = db.query(Lead).filter(Lead.created_at >= s7).count()
    leads_30d      = db.query(Lead).filter(Lead.created_at >= s30).count()
    leads_ganados  = db.query(Lead).filter(Lead.estado == "CERRADO_GANADO").count()
    leads_activos  = db.query(Lead).filter(
        Lead.estado.in_(["NUEVO", "CONTACTADO", "EN_SEGUIMIENTO", "CALIFICADO",
                         "COTIZADO", "NEGOCIANDO", "VIDEOLLAMADA_AGENDADA"])
    ).count()
    leads_frios    = db.query(Lead).filter(
        Lead.estado.in_(["CONTACTADO", "EN_SEGUIMIENTO"]),
        Lead.updated_at <= ayer,
    ).count()

    # Leads por agente (últimos 30 días)
    from sqlalchemy import func as sqlfunc
    leads_por_agente_raw = (
        db.query(Lead.agente_asignado, sqlfunc.count(Lead.id))
        .filter(Lead.created_at >= s30)
        .group_by(Lead.agente_asignado)
        .all()
    )
    leads_por_agente = {a: c for a, c in leads_por_agente_raw}

    # Leads por producto (últimos 30 días)
    leads_por_producto_raw = (
        db.query(Lead.producto_interes, sqlfunc.count(Lead.id))
        .filter(Lead.created_at >= s30)
        .group_by(Lead.producto_interes)
        .all()
    )
    leads_por_producto = {p: c for p, c in leads_por_producto_raw}

    # Tasa conversión
    conversion_pct = round((leads_ganados / leads_total * 100), 1) if leads_total > 0 else 0

    # ── MercadoLibre (desde cache local) ─────────────────────────────────────
    pubs_activas  = db.query(PublicacionML).filter(PublicacionML.estado_ml == "active").count()
    pubs_total    = db.query(PublicacionML).count()

    # ── Tendencia de leads (últimos 30 días, por día) ─────────────────────────
    from sqlalchemy import cast, Date as SADate
    tendencia_raw = (
        db.query(
            cast(Lead.created_at, SADate).label("dia"),
            sqlfunc.count(Lead.id).label("qty"),
        )
        .filter(Lead.created_at >= s30)
        .group_by("dia")
        .order_by("dia")
        .all()
    )
    tendencia = [{"dia": str(d), "qty": q} for d, q in tendencia_raw]

    return {
        "ecopost": {
            "total": total_post,
            "publicados": publicados,
            "aprobados": aprobados,
            "borradores": borradores,
            "creados_7d": posts_7d,
            "por_tipo": tipos_count,
            "recientes": [
                {
                    "id": p.id,
                    "titulo": p.titulo or "(sin título)",
                    "tipo": p.tipo,
                    "estado": p.estado,
                    "producto": p.producto or "",
                    "created_at": p.created_at.isoformat() if p.created_at else "",
                }
                for p in posts_recientes
            ],
        },
        "leads": {
            "total": leads_total,
            "hoy": leads_hoy,
            "ultimos_7d": leads_7d,
            "ultimos_30d": leads_30d,
            "activos": leads_activos,
            "ganados": leads_ganados,
            "frios": leads_frios,
            "conversion_pct": conversion_pct,
            "por_agente": leads_por_agente,
            "por_producto": leads_por_producto,
            "tendencia_30d": tendencia,
        },
        "mercadolibre": {
            "publicaciones_activas": pubs_activas,
            "publicaciones_total": pubs_total,
        },
    }


# ─── API — GENERADOR DE BLOG ──────────────────────────────────────────────────

@router.post("/api/marketing/blog/generar")
async def generar_articulo_blog(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """
    Genera un artículo de blog con IA (Gemini) optimizado para SEO.
    Body: { tema, producto, palabras_clave, tono, longitud }
    Devuelve: { titulo, slug, contenido_markdown, meta_descripcion, palabras_clave }
    """
    from fastapi import HTTPException
    from database.models import ConfiguracionSistema
    _check(current_user)

    data = await request.json()
    tema = data.get("tema", "")
    producto = data.get("producto", "módulos habitacionales")
    palabras_clave = data.get("palabras_clave", [])
    tono = data.get("tono", "informativo y cercano")
    longitud = data.get("longitud", "media")  # corta | media | larga

    if not tema:
        raise HTTPException(400, "El tema es requerido")

    # IA unificada: Grok → Gemini → Claude
    from utils.ai_client import get_active_provider
    pname, api_key = get_active_provider(db)
    if not api_key:
        raise HTTPException(400, "No hay API key de IA configurada. Configurar Grok, Gemini o Claude en Configuración → API Keys.")

    palabras_str = ", ".join(palabras_clave) if palabras_clave else "piscinas Argentina, módulos habitacionales, Eco Módulos"
    palabras_count = {"corta": "500-700", "media": "900-1200", "larga": "1500-2000"}.get(longitud, "900-1200")

    prompt = f"""Sos redactor SEO experto en construcción y diseño de hogares, especializado en Eco Módulos & Piscinas.
Empresa: Eco Módulos & Piscinas — fabricamos e instalamos piscinas de fibra y módulos habitacionales.
Ubicados en Zárate, Buenos Aires. Ofrecemos financiación propia, instalación incluida en todo el país.

IDIOMA Y TONO OBLIGATORIO: escribís siempre en castellano de Argentina — no en español neutro ni latinoamericano genérico.
Usás "vos", "acá", "querés", "podés", "tenés" y demás formas rioplatenses de forma natural.
El tono es cálido, cercano y profesional: como un experto que le habla de igual a igual al lector, genera confianza y lo invita a dar el paso, sin ser informal ni usar lunfardo.

Escribí un artículo de blog completo sobre: "{tema}"
Producto relacionado: {producto}
Palabras clave a incluir naturalmente: {palabras_str}
Tono: {tono}
Extensión objetivo: {palabras_count} palabras

ESTRUCTURA DEL ARTÍCULO:
1. Título SEO atractivo (con la palabra clave principal)
2. Meta descripción (155 caracteres máximo)
3. Cuerpo del artículo en Markdown con:
   - Introducción enganchadora
   - Al menos 3 subtítulos H2
   - Lista de beneficios o puntos clave
   - Datos o estadísticas si aplican
   - Llamado a la acción al final (mencionar contacto WhatsApp)
4. Slug URL sugerido (formato: palabras-con-guiones)

Responde en formato JSON:
{{
  "titulo": "...",
  "slug": "...",
  "meta_descripcion": "...",
  "contenido_markdown": "...",
  "palabras_clave_usadas": ["..."]
}}"""

    try:
        text = await ai_complete(db, prompt, max_tokens=2500, temperature=0.7)

        # Extraer JSON del response
        import json, re
        json_match = re.search(r'\{[\s\S]+\}', text)
        if json_match:
            resultado = json.loads(json_match.group())
        else:
            resultado = {
                "titulo": f"Artículo sobre {tema}",
                "slug": tema.lower().replace(" ", "-"),
                "meta_descripcion": "",
                "contenido_markdown": text,
                "palabras_clave_usadas": palabras_clave,
            }

        return {"ok": True, "articulo": resultado}

    except Exception as e:
        raise HTTPException(502, f"Error generando artículo: {e}")


@router.get("/api/marketing/utm-stats")
async def get_utm_stats(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_auth),
):
    """Estadísticas de leads por UTM source/medium/campaign."""
    from fastapi import HTTPException
    from sqlalchemy import func as sqlfunc
    _check(current_user)

    hace_30 = datetime.now() - timedelta(days=30)

    por_source = db.query(Lead.utm_source, sqlfunc.count(Lead.id)).filter(
        Lead.created_at >= hace_30,
        Lead.utm_source.isnot(None)
    ).group_by(Lead.utm_source).all()

    por_medium = db.query(Lead.utm_medium, sqlfunc.count(Lead.id)).filter(
        Lead.created_at >= hace_30,
        Lead.utm_medium.isnot(None)
    ).group_by(Lead.utm_medium).all()

    por_campaign = db.query(Lead.utm_campaign, sqlfunc.count(Lead.id)).filter(
        Lead.created_at >= hace_30,
        Lead.utm_campaign.isnot(None)
    ).group_by(Lead.utm_campaign).all()

    return {
        "periodo": "últimos 30 días",
        "por_source": {s: c for s, c in por_source},
        "por_medium": {m: c for m, c in por_medium},
        "por_campaign": {camp: c for camp, c in por_campaign},
    }
