"""
FacebookProvider — Meta Graph API (Pages - Videos).

Requisitos:
1. Misma app de Meta que Instagram (developers.facebook.com)
2. Permisos: pages_manage_posts, pages_read_engagement, pages_show_list
3. El canal es una Página de Facebook, no un perfil personal
4. Configurar META_APP_ID, META_APP_SECRET en .env (comparte con Instagram)

Nota: los tokens son los mismos que Instagram (misma app Meta).
El canal Facebook usa el Page Access Token, no el User Token.

Documentación:
  https://developers.facebook.com/docs/graph-api/reference/page/videos/
"""

import asyncio
import httpx
from app.core.config import get_settings
from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderAuthError, ProviderRateLimitError, ProviderContentError, ProviderTemporaryError,
    ProviderRegistry,
)

settings = get_settings()

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

SUPPORTED_MIME_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}
MAX_VIDEO_SIZE_BYTES = 10_000_000_000  # 10 GB (Facebook Pages)


@ProviderRegistry.register("facebook")
class FacebookProvider(SocialProvider):
    platform_name = "facebook"

    # El token guardado es el Page Access Token (obtenido via get_page_token)
    def __init__(self, access_token: str, refresh_token: str | None = None,
                 page_id: str | None = None):
        super().__init__(access_token, refresh_token)
        self.page_id = page_id  # se carga desde platform_meta al publicar

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

    @staticmethod
    def get_oauth_url(redirect_uri: str, state: str = "") -> str:
        """Misma URL que Instagram (misma app Meta)."""
        from app.providers.instagram import InstagramProvider
        return InstagramProvider.get_oauth_url(redirect_uri, state)

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """Mismo flujo que Instagram: short-lived → long-lived token."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/oauth/access_token", params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "redirect_uri": redirect_uri,
                "code": auth_code,
            })
            _check_meta_error(r)
            short_token = r.json()["access_token"]

            r2 = await client.get(f"{GRAPH_BASE}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_token,
            })
            _check_meta_error(r2)
            return r2.json()["access_token"], None

    async def refresh_auth(self) -> tuple[str, str | None]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": self.access_token,
            })
            _check_meta_error(r)
            return r.json()["access_token"], None

    async def get_channel_info(self) -> ChannelInfo:
        """
        Retorna la primera Página de Facebook administrada por el usuario.
        Cada página es un canal independiente.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/me/accounts", params={
                "access_token": self.access_token,
                "fields": "id,name,picture,category,access_token",
            })
            _check_meta_error(r)
            pages = r.json().get("data", [])
            if not pages:
                raise ProviderAuthError(
                    "No se encontraron Páginas de Facebook administradas por este usuario. "
                    "Se requiere rol de administrador o editor en al menos una Página."
                )
            page = pages[0]
            return ChannelInfo(
                remote_id=page["id"],
                remote_name=page.get("name", ""),
                remote_username=None,
                avatar_url=page.get("picture", {}).get("data", {}).get("url"),
                platform_meta={
                    "page_access_token": page.get("access_token"),
                    "category": page.get("category"),
                    "all_pages": [{"id": p["id"], "name": p["name"]} for p in pages],
                },
            )

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        if mime_type not in SUPPORTED_MIME_TYPES:
            return False, f"Facebook no acepta {mime_type}"
        if file_size_bytes > MAX_VIDEO_SIZE_BYTES:
            return False, "Supera el límite de 10 GB de Facebook Pages"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Publica video en una Página de Facebook via URL-based upload.
        POST /{page-id}/videos con file_url (el video debe ser URL pública).
        Usa el Page Access Token almacenado en platform_meta.
        """
        page_id = job_data.get("page_id") or self.page_id
        page_token = job_data.get("page_access_token") or self.access_token
        video_url = job_data.get("storage_url")
        description = job_data.get("caption", "")

        if not page_id or not video_url:
            return PublishResult(success=False, error_message="Falta page_id o video_url", error_type="invalid_content")

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{GRAPH_BASE}/{page_id}/videos", params={
                "access_token": page_token,
                "file_url": video_url,
                "description": description,
            })
            _check_meta_error(r)
            data = r.json()
            video_id = data.get("id")
            return PublishResult(
                success=True,
                remote_id=video_id,
                remote_url=f"https://www.facebook.com/{page_id}/videos/{video_id}/",
            )

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """
        Facebook Pages soporta scheduled_publish_time (epoch) + published=false.
        """
        from datetime import datetime, timezone
        import calendar
        page_id = job_data.get("page_id") or self.page_id
        page_token = job_data.get("page_access_token") or self.access_token
        video_url = job_data.get("storage_url")
        description = job_data.get("caption", "")

        scheduled_dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        epoch = calendar.timegm(scheduled_dt.utctimetuple())

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{GRAPH_BASE}/{page_id}/videos", params={
                "access_token": page_token,
                "file_url": video_url,
                "description": description,
                "published": "false",
                "scheduled_publish_time": epoch,
            })
            _check_meta_error(r)
            data = r.json()
            return PublishResult(
                success=True,
                remote_id=data.get("id"),
                scheduled_at=scheduled_at,
            )

    async def get_publication_status(self, remote_id: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/{remote_id}", params={
                "access_token": self.access_token,
                "fields": "id,status",
            })
            return "published" if r.status_code == 200 else "failed"

    async def get_metrics(self, remote_id: str) -> MetricsData:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/{remote_id}/video_insights", params={
                "access_token": self.access_token,
                "metric": "total_video_views,total_video_likes,post_activity_by_action_type",
                "period": "lifetime",
            })
            if r.status_code != 200:
                return MetricsData()
            data = r.json().get("data", [])
            metrics = {}
            for item in data:
                name = item["name"]
                values = item.get("values", [{}])
                metrics[name] = values[-1].get("value", 0) if values else 0
            return MetricsData(
                views=metrics.get("total_video_views"),
                likes=metrics.get("total_video_likes"),
                raw_data=metrics,
            )


def _check_meta_error(response: httpx.Response):
    if response.status_code == 200:
        return
    try:
        error = response.json().get("error", {})
    except Exception:
        error = {}
    code = error.get("code", 0)
    msg = error.get("message", response.text[:200])
    if code in (190, 102, 463, 467):
        raise ProviderAuthError(f"Facebook token inválido: {msg}")
    if code == 32 or response.status_code == 429:
        raise ProviderRateLimitError(msg, retry_after=3600)
    if code in (100, 200, 10):
        raise ProviderContentError(msg)
    raise ProviderTemporaryError(f"Facebook API ({code}): {msg}")
