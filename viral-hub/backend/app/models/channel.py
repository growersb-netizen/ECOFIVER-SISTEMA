"""
SocialChannel — canal social conectado (una cuenta/perfil/página).
OAuthCredential — tokens cifrados. Separado del canal para seguridad.
ChannelGroup / GroupChannel — agrupación lógica de canales.
"""

import enum
from datetime import datetime
from sqlalchemy import (
    String, Boolean, DateTime, Integer, ForeignKey,
    Enum, func, JSON, Table, Column
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Platform(str, enum.Enum):
    instagram = "instagram"
    facebook = "facebook"
    tiktok = "tiktok"
    youtube = "youtube"


class ChannelStatus(str, enum.Enum):
    connected = "connected"
    requires_reconnect = "requires_reconnect"
    revoked = "revoked"
    error = "error"


# Tabla de asociación grupo↔canal (M:N)
group_channel_table = Table(
    "group_channels",
    Base.metadata,
    Column("group_id", ForeignKey("channel_groups.id"), primary_key=True),
    Column("channel_id", ForeignKey("social_channels.id"), primary_key=True),
)


class SocialChannel(Base):
    """
    Cada perfil/cuenta/página social es un canal independiente.
    Un workspace puede tener N canales del mismo provider.
    """
    __tablename__ = "social_channels"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(200), nullable=False)          # nombre interno editable
    remote_id: Mapped[str] = mapped_column(String(200), nullable=False)       # ID en la plataforma
    remote_name: Mapped[str | None] = mapped_column(String(200))              # nombre en la plataforma
    remote_username: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, name="channel_status"),
        default=ChannelStatus.connected,
        nullable=False,
    )
    # Capacidades declaradas por el provider al conectar
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Metadata extra de la plataforma (page_type, account_type, etc.)
    platform_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    workspace: Mapped["Workspace"] = relationship(back_populates="channels")
    credential: Mapped["OAuthCredential | None"] = relationship(
        back_populates="channel", uselist=False, cascade="all, delete-orphan"
    )
    groups: Mapped[list["ChannelGroup"]] = relationship(
        secondary=group_channel_table, back_populates="channels"
    )
    publication_jobs: Mapped[list["PublicationJob"]] = relationship(back_populates="channel")


class OAuthCredential(Base):
    """
    Tokens OAuth cifrados. NUNCA se almacenan en texto plano.
    Usar security.encrypt_token / decrypt_token.
    """
    __tablename__ = "oauth_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("social_channels.id"), unique=True, nullable=False)
    access_token_enc: Mapped[str] = mapped_column(String(2000), nullable=False)   # cifrado
    refresh_token_enc: Mapped[str | None] = mapped_column(String(2000))            # cifrado
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer")
    scope: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped["SocialChannel"] = relationship(back_populates="credential")


class ChannelGroup(Base):
    """
    Agrupa canales para publicación masiva.
    Un canal puede estar en N grupos.
    """
    __tablename__ = "channel_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # True = grupo "Todas" auto
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="groups")
    channels: Mapped[list["SocialChannel"]] = relationship(
        secondary=group_channel_table, back_populates="groups"
    )
