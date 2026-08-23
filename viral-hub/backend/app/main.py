"""
Punto de entrada de la aplicación FastAPI.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1 import router as api_v1_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y limpieza al arrancar/apagar la app."""
    # Importar providers para que se registren en ProviderRegistry
    import app.providers  # noqa: F401
    yield


app = FastAPI(
    title="Viral Hub API",
    version="1.0.0",
    description="Motor de distribución masiva de contenido corto",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rutas ────────────────────────────────────────────────────────────────────
app.include_router(api_v1_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "viral-hub-api"}
