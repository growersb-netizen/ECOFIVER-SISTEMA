import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backup import run_backup
from routers.leads import rotar_leads_inactivos
from database.database import engine, get_db, run_migrations
from database.models import Base
from database.seed import seed_database, seed_config_defaults, seed_rr_defaults

from routers import (
    auth, leads, videollamadas, ventas_contado, ventas_financiadas,
    cobranzas, fabrica, logistica, contratos, personal, dashboard,
    catalogo, importar, agentes, configuracion, mercadolibre, ecopost, push,
    zapia, webhooks, materiales, produccion, flota, web_cms, gastos, envios_cargo,
    control_agentes, instalacion, panolero, asistencia_rapida, entrega_rapida,
    marketing, simulador, seguimiento, testimonial, inbox, public_landing,
    aliados, ml_publicaciones, negocio, whatsapp_business, cobranza_historica,
    integraciones, redes_sociales, imagenes, ml_biblioteca,
)

log = logging.getLogger(__name__)

# Create tables + migrate existing ones
Base.metadata.create_all(bind=engine)
run_migrations()

# Ensure directories exist
Path("data/contratos").mkdir(parents=True, exist_ok=True)  # persistente (/app/data)
Path("data").mkdir(parents=True, exist_ok=True)
Path("data/backups").mkdir(parents=True, exist_ok=True)

# Seed initial data
seed_database()
seed_config_defaults()
seed_rr_defaults()

app = FastAPI(
    title="EcoFiver — CRM",
    description="Sistema de gestión comercial y operativo",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Service Worker servido desde la raíz con scope correcto
@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )

# Include routers
app.include_router(auth.router)
app.include_router(agentes.router)   # antes de leads para que /sin-respuesta no colisione
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(videollamadas.router)
app.include_router(ventas_contado.router)
app.include_router(ventas_financiadas.router)
app.include_router(cobranzas.router)
app.include_router(fabrica.router)
app.include_router(logistica.router)
app.include_router(contratos.router)
app.include_router(personal.router)
app.include_router(catalogo.router)
app.include_router(importar.router)
app.include_router(configuracion.router)
app.include_router(mercadolibre.router)
app.include_router(ecopost.router)
app.include_router(push.router)
app.include_router(zapia.router)
app.include_router(webhooks.router)
app.include_router(materiales.router)
app.include_router(produccion.router)
app.include_router(flota.router)
app.include_router(web_cms.router)
app.include_router(gastos.router)
app.include_router(envios_cargo.router)
app.include_router(control_agentes.router)
app.include_router(instalacion.router)
app.include_router(panolero.router)
app.include_router(asistencia_rapida.router)
app.include_router(entrega_rapida.router)
app.include_router(marketing.router)
app.include_router(simulador.router)    # público: /api/simulador/cuotas
app.include_router(seguimiento.router)  # público: /seguimiento/{token}
app.include_router(testimonial.router)  # público: /testimonial/{token}
app.include_router(inbox.router)        # bandeja de entrada WhatsApp
app.include_router(public_landing.router)  # público, sin API key: /api/public/landing-lead
app.include_router(aliados.router)          # canal Aliados Comerciales (Franco)
app.include_router(cobranza_historica.router)  # Cobranza histórica Construsol — independiente de EcoFiver
app.include_router(ml_publicaciones.router) # MercadoLibre — cola de publicaciones
app.include_router(negocio.router)          # Configuración del negocio
app.include_router(whatsapp_business.router) # Perfil de WhatsApp Business
app.include_router(integraciones.router)     # Integración WhatsApp IA (Melanie + futuros)
app.include_router(redes_sociales.router)   # Panel unificado de redes sociales
app.include_router(imagenes.router)         # Generador de imágenes con IA
app.include_router(ml_biblioteca.router)    # ML — Biblioteca fotos, sets, renovación, auto-responder


# ─── MANUAL DE USO ────────────────────────────────────────────────────────────

templates_main = Jinja2Templates(directory="templates")

@app.get("/manual", include_in_schema=False)
async def manual_page(
    request: Request,
    current_user = Depends(auth.require_auth),
):
    from routers.auth import get_user_roles
    roles = get_user_roles(current_user)
    return templates_main.TemplateResponse("manual.html", {
        "request": request,
        "user": current_user,
        "roles": roles,
    })


# ─── SCHEDULER ────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")

async def _resumen_diario_rodrigo():
    """Consolidado 08:00 ART — envía WA a Rodrigo con estado del día."""
    try:
        from database.database import SessionLocal
        from database.models import (
            OrdenProduccion, PedidoMaterialCompras, AsignacionVehiculo,
            Lead, ConfiguracionSistema
        )
        from utils.whatsapp import send_whatsapp_text
        from datetime import date

        db = SessionLocal()
        hoy = date.today()

        # Órdenes de producción activas
        ops_activas = db.query(OrdenProduccion).filter(
            OrdenProduccion.estado.in_(["PENDIENTE", "EN_PROCESO", "CONTROL_CALIDAD"])
        ).count()
        ops_urgentes = db.query(OrdenProduccion).filter(
            OrdenProduccion.estado.in_(["PENDIENTE", "EN_PROCESO", "CONTROL_CALIDAD"]),
            OrdenProduccion.prioridad == "URGENTE"
        ).count()

        # Pedidos de materiales pendientes
        pedidos_pend = db.query(PedidoMaterialCompras).filter(
            PedidoMaterialCompras.estado == "PENDIENTE"
        ).count()
        pedidos_hoy = db.query(PedidoMaterialCompras).filter(
            PedidoMaterialCompras.estado == "PENDIENTE",
            PedidoMaterialCompras.urgencia == "HOY"
        ).count()

        # Asignaciones de flota hoy
        flota_hoy = db.query(AsignacionVehiculo).filter(
            AsignacionVehiculo.fecha == str(hoy),
            AsignacionVehiculo.estado.in_(["PROGRAMADA", "EN_VIAJE"])
        ).count()

        # Leads nuevos sin contactar (excluye base RELLAMADOS)
        from sqlalchemy import or_ as _or
        leads_nuevos = db.query(Lead).filter(
            Lead.estado.in_(["NUEVO", "INTENTADO"]),
            _or(Lead.en_rellamados.is_(None), Lead.en_rellamados == False),
        ).count()

        # Teléfono de Rodrigo
        tel_cfg = db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == "tel_rodrigo"
        ).first()
        tel_rodrigo = tel_cfg.valor if tel_cfg and tel_cfg.valor else None

        db.close()

        if not tel_rodrigo:
            log.warning("[RESUMEN 8AM] No hay tel_rodrigo configurado en ConfiguracionSistema")
            return

        lineas = [
            f"📋 *Resumen del día — {hoy.strftime('%d/%m/%Y')}*",
            "",
            f"⚙️ *Producción:* {ops_activas} OPs activas" + (f" ({ops_urgentes} urgentes ⚠️)" if ops_urgentes else ""),
            f"📦 *Materiales:* {pedidos_pend} pedidos pendientes" + (f" ({pedidos_hoy} para HOY 🔴)" if pedidos_hoy else ""),
            f"🚗 *Flota:* {flota_hoy} salidas programadas hoy",
            f"👥 *Leads:* {leads_nuevos} sin contactar",
            "",
            f"🔗 https://eco-crm-production.up.railway.app",
        ]
        mensaje = "\n".join(lineas)
        from database.database import SessionLocal as _SL
        _db2 = _SL()
        send_whatsapp_text(_db2, tel_rodrigo, mensaje)
        _db2.close()
        log.info("[RESUMEN 8AM] Enviado a Rodrigo OK")
    except Exception as e:
        log.error(f"[RESUMEN 8AM] Error: {e}")


@app.on_event("startup")
async def startup_event():
    # Generar claves VAPID si no existen
    try:
        from routers.push import generar_y_guardar_vapid
        from database.database import SessionLocal
        _db = SessionLocal()
        generar_y_guardar_vapid(_db)
        _db.close()
    except Exception as e:
        log.warning(f"[PUSH] No se pudieron generar claves VAPID: {e}")

    # Backup diario a las 03:00 ART
    scheduler.add_job(
        run_backup,
        trigger=CronTrigger(hour=3, minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="backup_diario",
        name="Backup diario SQLite",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Rotación automática de leads cada hora (solo activa si modo = ROTACION_24H)
    scheduler.add_job(
        rotar_leads_inactivos,
        trigger=CronTrigger(minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="rotacion_leads",
        name="Rotación leads inactivos",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    # Consolidado diario 08:00 ART → WA a Rodrigo
    scheduler.add_job(
        _resumen_diario_rodrigo,
        trigger=CronTrigger(hour=8, minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="resumen_diario_rodrigo",
        name="Resumen diario WA Rodrigo",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Renovación automática ML → 02:15 ART (antes del backup)
    scheduler.add_job(
        ml_biblioteca._renovar_vencimientos_core,
        trigger=CronTrigger(hour=2, minute=15, timezone="America/Argentina/Buenos_Aires"),
        id="ml_renovacion_automatica",
        name="ML — Renovación automática de publicaciones",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Auto-responder preguntas ML → cada 20 minutos
    scheduler.add_job(
        ml_biblioteca._auto_responder_preguntas_job,
        trigger=CronTrigger(minute="*/20", timezone="America/Argentina/Buenos_Aires"),
        id="ml_auto_responder",
        name="ML — Auto-responder preguntas con IA",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    log.info("[SCHEDULER] Backup 03:00 + Leads + Resumen 08:00 + ML Renovación 02:15 + Auto-responder /20min — activos")


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown(wait=False)


# ─── AUTH MIDDLEWARE ──────────────────────────────────────────────────────────

@app.middleware("http")
async def auth_redirect_middleware(request: Request, call_next):
    # Public paths
    public = [
        "/login", "/static", "/sw.js",
        "/api/auth", "/api/leads", "/api/push/vapid-public-key", "/api/ext",
        "/api/webhooks",
        "/api/inbox/entrante",   # multiagente notifica mensajes
        "/api/inbox/modo/",      # multiagente consulta modo de atención
        "/equipo/pedido",           # pública con código de equipo
        "/portal-aliado",           # portal de solo lectura del aliado (login por código+PIN)
        "/api/public",              # endpoints públicos (landing, postulación aliado, portal)
        "/api/materiales/pedidos",  # POST público para pedidos del equipo
        "/operario/",               # panel operario por token (sin login)
        "/api/produccion/ordenes/", # operario registra etapas sin login
        "/api/health",              # Railway / Docker healthcheck
        "/mercadolibre/notifications",  # webhook de MercadoLibre (sin sesión) — si falla, ML revoca la app
        "/api/integraciones/melanie/confirmacion",  # Melanie envía Bearer propio, sin cookie de sesión
        "/webhook/melanie",  # Webhook de Meta para la WABA de Melanie (verificación + mensajes)
    ]
    path = request.url.path

    if any(path.startswith(p) for p in public):
        return await call_next(request)

    # Check if HTML page request without cookie
    if not path.startswith("/api") and not path.startswith("/static"):
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "sistema": "EcoFiver CRM", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
