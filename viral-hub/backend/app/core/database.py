"""
Configuración de SQLAlchemy async.
Cada request obtiene su propia sesión; se cierra al terminar.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=not settings.is_production,   # SQL logging en dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base para todos los modelos SQLAlchemy."""
    pass


async def get_db() -> AsyncSession:
    """Dependency de FastAPI: provee sesión DB y la cierra al terminar."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
