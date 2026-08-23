"""
YouTubeProvider — YouTube Data API v3.

IMPORTANTE antes de implementar:
  - Usar videos.insert con resumable upload para archivos grandes
  - El quota diario de la API es limitado — monitorear y gestionar
  - Documentación: https://developers.google.com/youtube/v3/docs/videos/insert

Estado: STUB — implementar en la fase de conectores.
"""

from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderRegistry,
)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@ProviderRegistry.register("youtube")
class YouTubeProvider(SocialProvider):

    platform_name = "youtube"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supported=[
            Capability.direct_publish,
            Capability.scheduling,
            Capability.video,
            Capability.short_video,
            Capability.custom_title,
            Capability.custom_caption,
            Capability.analytics,
            Capability.publication_status,
        ])

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        Google OAuth 2.0: POST /token con grant_type=authorization_code.
        TODO: implementar
        """
        raise NotImplementedError("YouTubeProvider.connect — pendiente")

    async def refresh_auth(self) -> tuple[str, str | None]:
        """POST /token con grant_type=refresh_token"""
        raise NotImplementedError("YouTubeProvider.refresh_auth — pendiente")

    async def get_channel_info(self) -> ChannelInfo:
        """GET /channels?part=snippet&mine=true"""
        raise NotImplementedError("YouTubeProvider.get_channel_info — pendiente")

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        # YouTube acepta MP4, MOV, AVI, WMV, FLV, MPEG, WebM
        allowed = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/mpeg"}
        if mime_type not in allowed:
            return False, f"Formato no soportado por YouTube: {mime_type}"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Resumable upload via POST /upload/youtube/v3/videos
        - Para Shorts: relación de aspecto 9:16, duración ≤60s, #Shorts en título/descripción
        TODO: implementar
        """
        raise NotImplementedError("YouTubeProvider.publish — pendiente")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """YouTube soporta privacyStatus=private + publishAt para programar."""
        raise NotImplementedError("YouTubeProvider.schedule_publication — pendiente")

    async def get_publication_status(self, remote_id: str) -> str:
        """GET /videos?part=status&id={remote_id}"""
        raise NotImplementedError("YouTubeProvider.get_publication_status — pendiente")

    async def get_metrics(self, remote_id: str) -> MetricsData:
        """YouTube Analytics API"""
        raise NotImplementedError("YouTubeProvider.get_metrics — pendiente")
