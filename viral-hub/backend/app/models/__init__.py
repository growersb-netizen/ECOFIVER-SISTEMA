"""
Importar todos los modelos para que Alembic los detecte en autogenerate.
"""

from app.models.user import User
from app.models.workspace import Workspace, Membership, Subscription
from app.models.channel import SocialChannel, OAuthCredential, ChannelGroup
from app.models.media import MediaAsset
from app.models.publication import Publication, PublicationJob, AnalyticsSnapshot, AuditLog

__all__ = [
    "User",
    "Workspace",
    "Membership",
    "Subscription",
    "SocialChannel",
    "OAuthCredential",
    "ChannelGroup",
    "MediaAsset",
    "Publication",
    "PublicationJob",
    "AnalyticsSnapshot",
    "AuditLog",
]
