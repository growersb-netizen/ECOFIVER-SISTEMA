"""
Eco Módulos & Piscinas — Sistema Multiagente de Ventas por WhatsApp
Servidor principal FastAPI
"""
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import uvicorn

from config import APP_HOST, APP_PORT, DEBUG, validate_config
from database import (
    init_db, get_today_stats, get_all_conversations,
    get_all_leads, get_conversation_detail,
)
from webhook import router as webhook_router
from notifications import send_daily_summary, send_welcome_test
from rate_limit import limiter
from logger import get_logger

log = get_logger(__name__)


# ─── Job del scheduler ────────────────────────────────────────────────────────

async def daily_summary_job():
    """Job APScheduler: envía el resumen diario a las 20:00hs."""
    try:
        log.info("Enviando resumen diario...")
        stats = get_today_stats()
        await send_daily_summary(stats)
        log.info("Resumen diario enviado correctamente.")
    except Exception as e:
        log.error("Error enviando resumen diario: %s", e)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    validate_config()
    init_db()
    log.info("Base de datos inicializada.")

    scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")
    scheduler.add_job(daily_summary_job, CronTrigger(hour=20, minute=0))
    scheduler.start()
    log.info("Scheduler APScheduler activo — resumen diario a las 20:00hs ART.")

    await send_welcome_test()

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    log.info("Scheduler detenido.")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Eco Módulos & Piscinas — Agentes de Ventas",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Webhook de WhatsApp
app.include_router(webhook_router, prefix="", tags=["WhatsApp Webhook"])


# ─── API del Dashboard ────────────────────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    """Estadísticas del día."""
    return get_today_stats()


@app.get("/api/conversations")
async def api_conversations(agent: str = None, score: str = None, limit: int = 50):
    """Lista de conversaciones."""
    return get_all_conversations(limit=limit, agent=agent, score=score)


@app.get("/api/conversations/{conv_id}")
async def api_conversation_detail(conv_id: int):
    """Detalle de una conversación."""
    detail = get_conversation_detail(conv_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return detail


@app.get("/api/leads")
async def api_leads(score: str = None, agent: str = None, limit: int = 100):
    """Lista de leads."""
    return get_all_leads(limit=limit, score=score, agent=agent)


@app.get("/api/health")
async def health_check():
    """Health check para Fly.io."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ─── Dashboard (archivos estáticos) ───────────────────────────────────────────

app.mount("/static", StaticFiles(directory="dashboard"), name="dashboard")


@app.get("/")
async def dashboard():
    """Sirve el dashboard."""
    return FileResponse("dashboard/index.html")


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=DEBUG,
    )
