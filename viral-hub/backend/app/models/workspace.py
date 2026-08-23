"""
Workspace — tenant del SaaS. Cada workspace está aislado.
Membership — relación usuario↔workspace con rol.
Subscription — plan contratado del workspace.

Principio: los límites del plan se leen de plan_config (JSONB),
NO se hardcodean en la lógica del producto.
"""

import enum
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Enum, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MemberRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    editor = "editor"
    publisher = "publisher"
    analyst = "analyst"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    past_due = "past_due"
    cancelled = "cancelled"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="workspace", uselist=False)
    channels: Mapped[list["SocialChannel"]] = relationship(back_populates="workspace")
    groups: Mapped[list["ChannelGroup"]] = relationship(back_populates="workspace")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="workspace")
    publications: Mapped[list["Publication"]] = relationship(back_populates="workspace")


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role"), nullable=False, default=MemberRole.editor
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relaciones
    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), unique=True, nullable=False)
    plan_name: Mapped[str] = mapped_column(String(50), nullable=False)  # starter, creator, pro, agency, enterprise
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.trialing,
        nullable=False,
    )
    # Límites y features — configurable desde Admin, NUNCA hardcodeados
    plan_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: {
        "max_channels": 5,
        "max_users": 1,
        "max_storage_gb": 10,
        "max_publications_per_month": 100,
        "features": {
            "analytics": True,
            "api_access": False,
            "custom_groups": True,
        }
    })
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_subscription_id: Mapped[str | None] = mapped_column(String(200))  # Stripe, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="subscription")
