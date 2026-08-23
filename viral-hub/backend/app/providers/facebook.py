"""
FacebookProvider — Meta Graph API (Pages).

IMPORTANTE:
  - Requiere cuenta Business y Page con permisos pages_manage_posts, pages_read_engagement
  - El video debe ser accesible por URL pública durante la subida
  - Documentación: https://developers.facebook.com/docs/graph-api/reference/page/videos/

Estado: STUB — implementar en la fase de conectores.
"""

from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderRegistry,
)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@ProviderRegistry.register("facebook")
class FacebookProvider(SocialProvider):

    platform_name = "facebook"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supported=[
            Capability.direct_publish,
            Capability.scheduling,
            Capability.video,
            Capability.short_video,
            Capability.image,
            Capability.custom_caption,
            Capability.analytics,
            Capability.publication_status,
        ])

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        raise NotImplementedError("FacebookProvider.connect — pendiente")

    async def refresh_auth(self) -> tuple[str, str | None]:
        raise NotImplementedError("FacebookProvider.refresh_auth — pendiente")

    async def get_channel_info(self) -> ChannelInfo:
        """GET /{page-id}?fields=id,name,picture"""
        raise NotImplementedError("FacebookProvider.get_channel_info — pendiente")

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        return True, None  # TODO: validar límites de Facebook Pages

    async def publish(self, job_data: dict) -> PublishResult:
        """POST /{page-id}/videos con file_url y description"""
        raise NotImplementedError("FacebookProvider.publish — pendiente")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """POST /{page-id}/videos con published=false y scheduled_publish_time"""
        raise NotImplementedError("FacebookProvider.schedule_publication — pendiente")

    async def get_publication_status(self, remote_id: str) -> str:
        raise NotImplementedError("FacebookProvider.get_publication_status — pendiente")

    async def get_metrics(self, remote_id: str) -> MetricsData:
        raise NotImplementedError("FacebookProvider.get_metrics — pendiente")
