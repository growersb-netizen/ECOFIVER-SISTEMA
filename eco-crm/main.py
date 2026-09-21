import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Asegurar que los logs de módulos custom (audit ML, agentes, etc.) aparezcan
# en stdout de Railway. uvicorn no configura el root logger con handler por defecto.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
    force=True,  # reemplaza cualquier config previa (uvicorn, etc.)
)

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backup import run_backup
from routers.leads import rotar_leads_inactivos
from database.database import engine, get_db, run_migrations, _is_sqlite
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
    integraciones, redes_sociales, imagenes, ml_biblioteca, socios,
)
from routers import ml_audit

log = logging.getLogger(__name__)

# Schema setup: SQLite uses create_all + raw ALTERs; PostgreSQL uses Alembic
if _is_sqlite:
    Base.metadata.create_all(bind=engine)
    run_migrations()
else:
    from alembic.config import Config as _AlembicConfig
    from alembic import command as _alembic_command
    _alembic_cfg = _AlembicConfig("alembic.ini")
    _alembic_command.upgrade(_alembic_cfg, "head")

    # Auto-migrate SQLite data → PG once (idempotente via flag file)
    _MIGRATION_FLAG = Path("data/.sqlite_migrated")
    _SQLITE_SRC = Path("data/eco_crm.db")
    if not _MIGRATION_FLAG.exists() and _SQLITE_SRC.exists():
        log.info("Iniciando migración automática SQLite → PostgreSQL…")
        try:
            import subprocess, sys
            result = subprocess.run(
                [sys.executable, "migrate_sqlite_to_pg.py",
                 "--sqlite-path", str(_SQLITE_SRC)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                _MIGRATION_FLAG.touch()
                log.info("Migración SQLite→PG completada. Flag creado.")
            else:
                log.error(f"Migración falló:\n{result.stdout}\n{result.stderr}")
        except Exception as _exc:
            log.error(f"Error al correr migración: {_exc}")

# Ensure directories exist
Path("data/contratos").mkdir(parents=True, exist_ok=True)  # persistente (/app/data)
Path("data").mkdir(parents=True, exist_ok=True)
Path("data/backups").mkdir(parents=True, exist_ok=True)
Path("data/ecopost_videos").mkdir(parents=True, exist_ok=True)   # videos Ecopost (Reels/TikTok/YouTube)

# Seed initial data
seed_database()
seed_config_defaults()
seed_rr_defaults()

# Guías reales de la Biblioteca de contenidos del panel de socios (idempotente)
try:
    from database.database import SessionLocal
    from routers.socios import seed_biblioteca_socios, sincronizar_biblioteca_catalogo, sincronizar_biblioteca_marketing, seed_comision_config
    _db_seed = SessionLocal()
    try:
        seed_biblioteca_socios(_db_seed)
        sincronizar_biblioteca_catalogo(_db_seed)
        sincronizar_biblioteca_marketing(_db_seed)
        seed_comision_config(_db_seed)
    finally:
        _db_seed.close()
except Exception:
    log.exception("No se pudo sembrar la biblioteca de socios")

# Sincronizar en DB las claves de configuración que vienen de env vars (WA_TOKEN,
# WA_PHONE_ID, API keys de IA, etc.). Antes esto solo corría cuando un admin
# abría /configuracion manualmente, lo que dejaba wa_token/wa_phone_id vacíos en
# DB (y por lo tanto el envío de WhatsApp roto en silencio, ej: OTP de registro
# de socios) aunque las env vars estuvieran cargadas en Railway.
try:
    from database.database import SessionLocal as _SessionLocalCfg
    from routers.configuracion import auto_init_config
    _db_cfg = _SessionLocalCfg()
    try:
        auto_init_config(_db_cfg)

        # WA_TOKEN/WA_PHONE_ID: Railway (env var) es siempre la fuente de verdad.
        # auto_init_config() de arriba solo llena la clave si está VACÍA en DB, así
        # que si alguna vez quedó un token viejo/vencido guardado, un WA_TOKEN
        # nuevo en Railway nunca lo pisaba sin abrir /configuracion a mano. Acá
        # sí forzamos el overwrite en cada arranque para estas dos claves.
        import os as _os
        from database.encryption import encrypt_value as _encrypt_value
        from database.models import ConfiguracionSistema as _ConfigModel
        for _clave, _env_var, _es_secreto in (
            ("wa_token", "WA_TOKEN", True), ("wa_phone_id", "WA_PHONE_ID", False),
            ("smtp_host", "SMTP_HOST", False), ("smtp_port", "SMTP_PORT", False),
            ("smtp_user", "SMTP_USER", False), ("smtp_password", "SMTP_PASSWORD", True),
            ("smtp_from", "SMTP_FROM", False),
        ):
            _val = _os.getenv(_env_var, "")
            if not _val:
                continue
            _stored = _encrypt_value(_val) if _es_secreto else _val
            _entry = _db_cfg.query(_ConfigModel).filter(_ConfigModel.clave == _clave).first()
            if _entry:
                _entry.valor = _stored
                _entry.estado = "activa"
            else:
                _db_cfg.add(_ConfigModel(clave=_clave, valor=_stored, es_secreto=_es_secreto, categoria="whatsapp", estado="activa"))
        _db_cfg.commit()

        # Chequeo de salud: SMTP configurado?
        import os as _os2
        if not (_os2.getenv("SMTP_USER") and _os2.getenv("SMTP_PASSWORD")):
            log.warning(
                "[STARTUP] SMTP no configurado — los mails de verificación y "
                "bienvenida no se enviarán. Configurar SMTP_USER y SMTP_PASSWORD "
                "en las variables de entorno o desde /configuracion."
            )
    finally:
        _db_cfg.close()
except Exception:
    log.exception("No se pudo auto-inicializar la configuración desde env vars")

app = FastAPI(
    title="EcoFiver — CRM",
    description="Sistema de gestión comercial y operativo",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    # OJO: con allow_credentials=True no se puede usar "*" como origen.
    # Starlette solo refleja el origin exacto (en vez de "*") en preflight
    # (OPTIONS); en la respuesta real de un POST/GET sin cookie ya seteada
    # devuelve el "*" literal, y el navegador lo rechaza cuando el fetch
    # usa credentials:"include" (ver /api/public/socio-registro). Por eso
    # se lista de forma explícita cada origen habilitado.
    allow_origins=[
        "https://landing-aliados-ecofiver.vercel.app",
        "https://landing-financiacion.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_origin_regex=r"https://landing-aliados-ecofiver.*\.vercel\.app",
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
app.include_router(socios.router)           # Plataforma de Socios Comerciales (registro autoservicio)
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


@app.get("/pagos", include_in_schema=False)
async def pagos_landing(request: Request):
    """Landing pública de formas de pago — sin autenticación."""
    from routers.configuracion import get_config_value
    from database.database import SessionLocal
    db = SessionLocal()
    try:
        def _cfg(k):
            return get_config_value(k, db) or ""
        ctx = {
            "request": request,
            "cbu": _cfg("empresa_cbu"),
            "alias": _cfg("empresa_alias"),
            "mp_link": _cfg("empresa_mp_link"),
            "titular": _cfg("empresa_nombre") or "EcoFiver",
            "wa": (_cfg("empresa_wa_principal") or "").replace("+", "").replace(" ", ""),
        }
    finally:
        db.close()
    return templates_main.TemplateResponse("pagos.html", ctx)


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


_MENSAJES_COBRANZA = {
    3:  (
        "Hola {nombre}! 👋 Te recordamos que el *{fecha}* vence tu próxima cuota del plan EcoFiver. "
        "Ante cualquier consulta, estamos a tu disposición. ¡Muchas gracias!"
    ),
    0:  (
        "Hola {nombre}! 📅 Hoy es la fecha de vencimiento de tu cuota del plan EcoFiver. "
        "Si ya realizaste el pago, podés ignorar este mensaje. "
        "Si necesitás coordinar la forma de pago, no dudes en contactarnos."
    ),
    -2: (
        "Hola {nombre}! 👋 Tu cuota del plan EcoFiver aún no figura acreditada. "
        "Te pedimos que te comuniques con nosotros para coordinar el pago y mantener tu plan activo. ¡Gracias!"
    ),
}


async def _recordatorio_cobranza(dias_delta: int):
    """
    Envía recordatorios WA a clientes con cuota próxima o vencida.
      dias_delta =  3 → T-3 (alerta preventiva, 09:00 ART)
      dias_delta =  0 → día 0 de vencimiento (10:00 ART)
      dias_delta = -2 → T+2 post-vencimiento (11:00 ART)
    REGLA DE ORO: los mensajes no mencionan intereses ni recargos.
    """
    template = _MENSAJES_COBRANZA.get(dias_delta)
    if not template:
        return
    try:
        from database.database import SessionLocal
        from database.models import VentaFinanciada
        from routers.ventas_financiadas import calcular_proximo_vencimiento
        from utils.whatsapp import send_whatsapp_text
        from datetime import date as _date

        db = SessionLocal()
        hoy = _date.today()
        ventas = db.query(VentaFinanciada).filter(
            VentaFinanciada.estado_plan.in_(["ACTIVO", "ATRASADO"]),
            VentaFinanciada.cliente_telefono.isnot(None),
        ).all()

        enviados = 0
        for v in ventas:
            proximo = calcular_proximo_vencimiento(v)
            if not proximo:
                continue
            if (proximo.date() - hoy).days != dias_delta:
                continue
            telefono = (v.cliente_telefono or "").strip()
            if not telefono:
                continue
            nombre = (v.cliente_nombre or "Cliente").split()[0]
            fecha_str = proximo.strftime("%d/%m/%Y")
            mensaje = template.format(nombre=nombre, fecha=fecha_str)
            try:
                send_whatsapp_text(db, telefono, mensaje)
                enviados += 1
            except Exception as e_wa:
                log.warning(f"[COBRANZA-WA] Error enviando a venta {v.id}: {e_wa}")

        db.close()
        log.info(f"[COBRANZA-WA] delta={dias_delta:+d} — {enviados} mensajes enviados")
    except Exception as e:
        log.error(f"[COBRANZA-WA] Error en recordatorio (delta={dias_delta}): {e}")


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
    # Ecopost: publicar contenidos programados → cada 5 minutos
    scheduler.add_job(
        ecopost._auto_publicar_programados,
        trigger=CronTrigger(minute="*/5", timezone="America/Argentina/Buenos_Aires"),
        id="ecopost_programados",
        name="Ecopost — Publicar contenido programado",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # Cobranza: recordatorio T-3 → 09:00 ART
    scheduler.add_job(
        _recordatorio_cobranza,
        trigger=CronTrigger(hour=9, minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="cobranza_t_menos_3",
        name="Cobranza — Recordatorio T-3 días",
        args=[3],
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Cobranza: recordatorio día 0 → 10:00 ART
    scheduler.add_job(
        _recordatorio_cobranza,
        trigger=CronTrigger(hour=10, minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="cobranza_dia_0",
        name="Cobranza — Recordatorio día de vencimiento",
        args=[0],
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Cobranza: seguimiento T+2 → 11:00 ART
    scheduler.add_job(
        _recordatorio_cobranza,
        trigger=CronTrigger(hour=11, minute=0, timezone="America/Argentina/Buenos_Aires"),
        id="cobranza_t_mas_2",
        name="Cobranza — Seguimiento T+2 días",
        args=[-2],
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info(
        "[SCHEDULER] Backup 03:00 + Leads + Resumen 08:00 + ML Renovación 02:15 + "
        "Auto-responder /20min + Ecopost /5min + Cobranza WA 09/10/11hs — activos"
    )

    # Auditoría y optimización de publicaciones ML (corre una vez por versión).
    # Espera 5 min para que el app termine de inicializar y el token ML esté listo.
    import asyncio as _asyncio
    _asyncio.create_task(ml_audit._delayed_audit_job())


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
        "/panel-socio",             # Plataforma de Socios Comerciales (login/registro propio, JWT en cookie aparte)
        "/terminos-socios-comerciales",  # Términos y Condiciones del programa (pública, enlazada desde el registro)
        "/socio/confirmar/",        # cliente confirma su plan financiado por link, sin sesión
        "/socio/declaracion-jurada/",  # cliente confirma la declaración jurada por link, sin sesión
        "/api/public",              # endpoints públicos (landing, postulación aliado, portal)
        "/api/materiales/pedidos",  # POST público para pedidos del equipo
        "/operario/",               # panel operario por token (sin login)
        "/api/produccion/ordenes/", # operario registra etapas sin login
        "/api/health",              # Railway / Docker healthcheck
        "/pub/img/",                # imágenes Ecopost vía token público (Instagram/Meta las necesita sin auth)
        "/pub/video/",              # videos Ecopost vía token público (Reels/TikTok/YouTube)
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
