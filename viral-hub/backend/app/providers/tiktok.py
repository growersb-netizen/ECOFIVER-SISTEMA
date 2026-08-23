"""
TikTokProvider — Content Posting API (Direct Post).

IMPORTANTE antes de implementar:
  - El scope video.publish requiere revisión de TikTok para levantar restricciones
  - Sin revisión: los videos pueden publicarse con visibilidad privada/limitada
  - Rate limits por access_token — implementar rate limiter por canal
  - Documentación oficial:
    https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post

Estado: STUB — implementar en la fase de conectores.
"""

from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderRegistry,
)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"

# Límites actuales (verificar en docs — pueden cambiar)
MAX_VIDEO_SIZE_BYTES = 4_000_000_000     # 4 GB
MAX_VIDEO_DURATION_SECONDS = 600         # 10 min (varía por cuenta)
MIN_VIDEO_DURATION_SECONDS = 3
SUPPORTED_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


@ProviderRegistry.register("tiktok")
class TikTokProvider(SocialProvider):

    platform_name = "tiktok"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supported=[
            Capability.direct_publish,
            Capability.short_video,
            Capability.video,
            Capability.custom_caption,
            Capability.custom_title,
            Capability.analytics,
            Capability.publication_status,
        ])

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        Flujo OAuth 2.0 de TikTok:
        POST https://open.tiktokapis.com/v2/oauth/token/
        TODO: implementar
        """
        raise NotImplementedError("TikTokProvider.connect — pendiente")

    async def refresh_auth(self) -> tuple[str, str | None]:
        """POST /v2/oauth/token/ con grant_type=refresh_token"""
        raise NotImplementedError("TikTokProvider.refresh_auth — pendiente")

    async def get_channel_info(self) -> ChannelInfo:
        """GET /v2/user/info/ con fields=open_id,display_name,avatar_url"""
        raise NotImplementedError("TikTokProvider.get_channel_info — pendiente")

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        if mime_type not in SUPPORTED_MIME_TYPES:
            return False, f"Formato no soportado: {mime_type}"
        if file_size_bytes > MAX_VIDEO_SIZE_BYTES:
            return False, "Archivo supera el límite de 4 GB de TikTok"
        if duration_seconds:
            if duration_seconds < MIN_VIDEO_DURATION_SECONDS:
                return False, f"Mínimo {MIN_VIDEO_DURATION_SECONDS}s de duración"
            if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
                return False, f"Máximo {MAX_VIDEO_DURATION_SECONDS}s de duración"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Flujo Direct Post (URL-based):
        1. POST /v2/post/publish/video/init/
        2. Upload via URL o chunk
        3. Polling de estado hasta PUBLISH_COMPLETE
        TODO: implementar
        """
        raise NotImplementedError("TikTokProvider.publish — pendiente")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        raise NotImplementedError("TikTok scheduling — pendiente")

    async def get_publication_status(self, remote_id: str) -> str:
        """GET /v2/post/publish/status/fetch/"""
        raise NotImplementedError("TikTokProvider.get_publication_status — pendiente")

    async def get_metrics(self, remote_id: str) -> MetricsData:
        raise NotImplementedError("TikTokProvider.get_metrics — pendiente")
