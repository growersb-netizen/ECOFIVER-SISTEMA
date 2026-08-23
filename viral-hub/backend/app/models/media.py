"""
MediaAsset — archivo de video/imagen en la biblioteca.
Un mismo asset puede publicarse en N canales (PublicationJob) sin duplicar el archivo.
"""

import enum
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, BigInteger, ForeignKey, Enum, func, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MediaType(str, enum.Enum):
    video = "video"
    image = "image"


class AssetStatus(str, enum.Enum):
    uploading = "uploading"
    processing = "processing"   # generando thumbnail, extrayendo metadata
    ready = "ready"
    archived = "archived"
    error = "error"


class MediaAsset(Base):
    """
    Archivo original. Se sube una vez al storage (R2/S3).
    Todos los PublicationJobs referencian este asset — no se duplica el archivo.
    """
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Identificación
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"), nullable=False)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status"),
        default=AssetStatus.uploading,
        nullable=False,
    )

    # Storage
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)    # key en R2/S3
    storage_bucket: Mapped[str] = mapped_column(String(200), nullable=False)
    public_url: Mapped[str | None] = mapped_column(String(1000))
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))

    # Metadata técnica (video)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(50))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    aspect_ratio: Mapped[str | None] = mapped_column(String(20))  # "9:16", "16:9", etc.

    # Organización
    tags: Mapped[str | None] = mapped_column(String(500))          # CSV de tags
    folder: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    workspace: Mapped["Workspace"] = relationship(back_populates="media_assets")
    publications: Mapped[list["Publication"]] = relationship(back_populates="media_asset")
