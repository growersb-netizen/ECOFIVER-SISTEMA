"""
Punto de entrada de la aplicación FastAPI.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1 import router as api_v1_router

settings = get_settings()
logger = logging.getLogger(__name__)


async def _seed_admin() -> None:
    """
    Crea el usuario administrador inicial si no existe.
    Idempotente: verifica antes de insertar.
    """
    try:
        from sqlalchemy import select, text
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from datetime import datetime, timezone
        import json

        from app.core.security import hash_password
        from app.models.user import User
        from app.models.workspace import Workspace, Membership, Subscription, MemberRole
        from app.models.channel import ChannelGroup

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        ADMIN_EMAIL = "admin@viralhub.io"
        ADMIN_PASSWORD = "F9@KAx3y9jjRPM!n"

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
            if result.scalar_one_or_none():
                logger.info("Admin %s ya existe — skip seed.", ADMIN_EMAIL)
                await engine.dispose()
                return

            logger.info("Creando usuario admin: %s", ADMIN_EMAIL)
            now = datetime.now(timezone.utc)

            user = User(
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                full_name="Administrador",
                is_active=True,
                is_superadmin=True,
            )
            session.add(user)
            await session.flush()

            workspace = Workspace(
                name="Viral Hub",
                slug="viral-hub",
                is_active=True,
            )
            session.add(workspace)
            await session.flush()

            membership = Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MemberRole.owner,
                is_active=True,
                joined_at=now,
            )
            session.add(membership)

            subscription = Subscription(
                workspace_id=workspace.id,
                plan_name="enterprise",
                plan_config={
                    "max_channels": 9999,
                    "max_users": 99,
                    "max_storage_gb": 9999,
                    "max_publications_per_month": 999999,
                    "features": {
                        "analytics": True,
                        "api_access": True,
                        "custom_groups": True,
                        "admin_panel": True,
                    }
                },
            )
            session.add(subscription)

            todos_group = ChannelGroup(
                workspace_id=workspace.id,
                name="Todas",
                description="Todos los canales conectados",
                is_system=True,
            )
            session.add(todos_group)

            await session.commit()
            logger.info("✅ Admin creado: %s / %s", ADMIN_EMAIL, ADMIN_PASSWORD)

        await engine.dispose()

    except Exception as exc:
        logger.error("Error en seed admin (no fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y limpieza al arrancar/apagar la app."""
    # Importar providers para que se registren en ProviderRegistry
    import app.providers  # noqa: F401

    # Seed admin inicial (idempotente)
    await _seed_admin()

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
