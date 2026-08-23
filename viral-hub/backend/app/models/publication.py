"""
Publication  — intención de publicar un asset en N canales.
PublicationJob — ejecución de una publicación a un canal específico.
               Un Publication genera N PublicationJobs (uno por canal destino).

El motor de distribución (sección 13 del blueprint):
  Publication → resolver canales → crear Jobs → Queue → Worker → API → resultado
"""

import enum
from datetime import datetime
from sqlalchemy import (
    String, Boolean, DateTime, Integer, ForeignKey,
    Enum, func, JSON, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PublicationStatus(str, enum.Enum):
    draft = "draft"
    queued = "queued"
    processing = "processing"
    published = "published"
    scheduled = "scheduled"
    retrying = "retrying"
    failed = "failed"
    needs_reconnect = "needs_reconnect"
    cancelled = "cancelled"


class JobErrorType(str, enum.Enum):
    temporary = "temporary"
    rate_limit = "rate_limit"
    auth = "auth"
    invalid_content = "invalid_content"
    platform = "platform"
    unknown = "unknown"


class Publication(Base):
    """
    Representa la intención del usuario de publicar un asset.
    Puede targetear múltiples canales/grupos — se generan N PublicationJobs.
    """
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    media_asset_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Captions/títulos por plataforma (JSON: {instagram: "...", tiktok: "...", ...})
    captions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Configuraciones específicas por plataforma (privacidad, etc.)
    platform_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Programación
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Estado general de la campaña
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status"),
        default=PublicationStatus.draft,
        nullable=False,
        index=True,
    )

    # IDs de los canales destino seleccionados al crear la publicación
    target_channel_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Totales (desnormalizados para el dashboard)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    jobs_published: Mapped[int] = mapped_column(Integer, default=0)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_pending: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    workspace: Mapped["Workspace"] = relationship(back_populates="publications")
    media_asset: Mapped["MediaAsset"] = relationship(back_populates="publications")
    jobs: Mapped[list["PublicationJob"]] = relationship(back_populates="publication", cascade="all, delete-orphan")


class PublicationJob(Base):
    """
    Ejecución de una publicación a un canal específico.
    Unidad atómica del motor de distribución.
    Debe ser idempotente: verificar job_idempotency_key antes de procesar.
    """
    __tablename__ = "publication_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("social_channels.id"), nullable=False, index=True)

    # Idempotencia: nunca procesar el mismo job dos veces
    job_idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)

    # ID asignado por Celery al encolar
    celery_task_id: Mapped[str | None] = mapped_column(String(200), index=True)

    # ID remoto de la publicación en la plataforma (cuando existe)
    remote_publication_id: Mapped[str | None] = mapped_column(String(200))
    remote_url: Mapped[str | None] = mapped_column(String(1000))

    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_job_status"),
        default=PublicationStatus.queued,
        nullable=False,
        index=True,
    )

    # Reintentos
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[JobErrorType | None] = mapped_column(Enum(JobErrorType, name="job_error_type"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps de transiciones
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    publication: Mapped["Publication"] = relationship(back_populates="jobs")
    channel: Mapped["SocialChannel"] = relationship(back_populates="publication_jobs")
    analytics: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="job")


class AnalyticsSnapshot(Base):
    """
    Snapshot periódico de métricas de una publicación en una plataforma.
    El modelo de datos soporta analytics avanzado; la UI inicial es básica.
    """
    __tablename__ = "analytics_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("publication_jobs.id"), nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    followers_gained: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)

    # Datos crudos por si la plataforma devuelve más campos
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    job: Mapped["PublicationJob"] = relationship(back_populates="analytics")


class AuditLog(Base):
    """Registro de acciones importantes. Quién hizo qué y cuándo."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[int | None] = mapped_column(Integer)
    metadata: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
