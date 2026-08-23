"""
InstagramProvider — Meta Graph API.

IMPORTANTE antes de implementar:
  - Validar en developers.facebook.com los permisos requeridos para tu tipo de app
  - El proceso de revisión de Meta puede limitar capacidades hasta aprobación
  - Solo cuentas profesionales/Business/Creator tienen acceso a publicación via API
  - Documentación: https://developers.facebook.com/docs/instagram-api/guides/content-publishing

Estado: STUB — implementar en la fase de conectores.
"""

import httpx
from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderAuthError, ProviderRateLimitError, ProviderContentError, ProviderTemporaryError,
    ProviderRegistry,
)


GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Límites documentados (verificar en docs antes de ajustar)
MAX_VIDEO_SIZE_BYTES = 1_000_000_000  # 1 GB
MAX_VIDEO_DURATION_SECONDS = 90       # Reels
SUPPORTED_MIME_TYPES = {"video/mp4", "video/quicktime"}


@ProviderRegistry.register("instagram")
class InstagramProvider(SocialProvider):

    platform_name = "instagram"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supported=[
            Capability.direct_publish,
            Capability.short_video,
            Capability.video,
            Capability.image,
            Capability.custom_caption,
            Capability.analytics,
            Capability.publication_status,
        ])

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        Intercambia auth_code por long-lived token de Meta.
        TODO: implementar el flujo de Meta OAuth completo.
        """
        raise NotImplementedError("InstagramProvider.connect — pendiente de implementación")

    async def refresh_auth(self) -> tuple[str, str | None]:
        """Los long-lived tokens de Meta se renuevan con GET /oauth/access_token."""
        raise NotImplementedError("InstagramProvider.refresh_auth — pendiente")

    async def get_channel_info(self) -> ChannelInfo:
        """GET /me?fields=id,name,username,profile_picture_url"""
        raise NotImplementedError("InstagramProvider.get_channel_info — pendiente")

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        if mime_type not in SUPPORTED_MIME_TYPES:
            return False, f"Formato no soportado: {mime_type}. Usar MP4 o MOV."
        if file_size_bytes > MAX_VIDEO_SIZE_BYTES:
            return False, f"Archivo demasiado grande ({file_size_bytes / 1e9:.1f} GB). Máximo 1 GB."
        if duration_seconds and duration_seconds > MAX_VIDEO_DURATION_SECONDS:
            return False, f"Duración {duration_seconds}s excede el máximo de {MAX_VIDEO_DURATION_SECONDS}s para Reels."
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Flujo de publicación de Reels via Meta Graph API:
        1. POST /{ig-user-id}/media  → container_id
        2. POST /{ig-user-id}/media_publish  → published_id

        El video debe estar en una URL pública accesible por Meta.
        TODO: implementar
        """
        raise NotImplementedError("InstagramProvider.publish — pendiente de implementación")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        # Instagram no soporta scheduling via API directa aún
        raise NotImplementedError("Instagram scheduling no disponible via API")

    async def get_publication_status(self, remote_id: str) -> str:
        raise NotImplementedError("InstagramProvider.get_publication_status — pendiente")

    async def get_metrics(self, remote_id: str) -> MetricsData:
        raise NotImplementedError("InstagramProvider.get_metrics — pendiente")
