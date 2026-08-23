"""
InstagramProvider — Meta Graph API (Instagram Professional Accounts).

Requisitos para que funcione:
1. Crear app en developers.facebook.com
2. Agregar producto "Instagram Graph API"
3. Permisos: instagram_basic, instagram_content_publish, pages_read_engagement
4. Pasar revisión de Meta para levantar restricciones de publicación
5. Configurar META_APP_ID, META_APP_SECRET, META_REDIRECT_URI en .env

Flujo OAuth de Meta:
  GET https://www.facebook.com/v21.0/dialog/oauth?...  ← Frontend redirige acá
  → Facebook devuelve code al callback
  → Backend intercambia code por short-lived token
  → Backend intercambia short-lived por long-lived token (60 días)
  → Para publicar: usar el Page Access Token del token del usuario

Documentación:
  https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""

import httpx
from datetime import datetime, timezone, timedelta
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
OAUTH_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"
TOKEN_URL = f"{GRAPH_BASE}/oauth/access_token"

MAX_VIDEO_DURATION_SECONDS = 90
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

    @staticmethod
    def get_oauth_url(redirect_uri: str, state: str = "") -> str:
        """Genera la URL a la que el frontend debe redirigir al usuario."""
        params = {
            "client_id": settings.META_APP_ID,
            "redirect_uri": redirect_uri,
            "scope": "instagram_basic,instagram_content_publish,pages_read_engagement,pages_show_list",
            "response_type": "code",
            "state": state,
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{OAUTH_URL}?{qs}"

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        1. Intercambia code por short-lived token (1h)
        2. Intercambia por long-lived token (60 días)
        """
        async with httpx.AsyncClient(timeout=30) as client:
            # Short-lived token
            r = await client.get(TOKEN_URL, params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "redirect_uri": redirect_uri,
                "code": auth_code,
            })
            _check_meta_error(r)
            short_token = r.json()["access_token"]

            # Long-lived token
            r2 = await client.get(f"{GRAPH_BASE}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_token,
            })
            _check_meta_error(r2)
            data = r2.json()
            return data["access_token"], None  # Meta no devuelve refresh_token

    async def refresh_auth(self) -> tuple[str, str | None]:
        """Los long-lived tokens se renuevan con fb_exchange_token sobre sí mismos."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": self.access_token,
            })
            _check_meta_error(r)
            data = r.json()
            return data["access_token"], None

    async def get_channel_info(self) -> ChannelInfo:
        """Obtiene la cuenta IG profesional vinculada al usuario."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Primero obtenemos las páginas de Facebook del usuario
            r = await client.get(f"{GRAPH_BASE}/me/accounts", params={
                "access_token": self.access_token,
                "fields": "id,name,instagram_business_account{id,name,username,profile_picture_url}",
            })
            _check_meta_error(r)
            data = r.json()

            pages = data.get("data", [])
            ig_account = None
            for page in pages:
                ig = page.get("instagram_business_account")
                if ig:
                    ig_account = ig
                    break

            if not ig_account:
                raise ProviderAuthError(
                    "No se encontró una cuenta Instagram Business/Creator vinculada a esta cuenta de Facebook. "
                    "La cuenta debe ser Profesional y estar vinculada a una Página de Facebook."
                )

            return ChannelInfo(
                remote_id=ig_account["id"],
                remote_name=ig_account.get("name", ""),
                remote_username=ig_account.get("username"),
                avatar_url=ig_account.get("profile_picture_url"),
                platform_meta={"page_id": pages[0]["id"] if pages else None},
            )

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        if mime_type not in SUPPORTED_MIME_TYPES:
            return False, f"Instagram solo acepta MP4 o MOV. Formato recibido: {mime_type}"
        if file_size_bytes > 1_000_000_000:
            return False, "El archivo supera 1 GB (límite de Instagram)"
        if duration_seconds and duration_seconds > MAX_VIDEO_DURATION_SECONDS:
            return False, f"Duración {duration_seconds:.0f}s excede el máximo de {MAX_VIDEO_DURATION_SECONDS}s para Reels"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Publica un Reel en Instagram via Media Container + Media Publish.
        El video debe estar en una URL pública accesible por Meta.

        Flujo:
        1. POST /{ig-user-id}/media → container_id (estado: IN_PROGRESS)
        2. Polling GET /{container-id}?fields=status_code hasta FINISHED
        3. POST /{ig-user-id}/media_publish → publicación exitosa
        """
        ig_user_id = job_data.get("channel_remote_id")
        video_url = job_data.get("storage_url")
        caption = job_data.get("caption", "")

        if not ig_user_id or not video_url:
            return PublishResult(success=False, error_message="Faltan ig_user_id o video_url", error_type="invalid_content")

        async with httpx.AsyncClient(timeout=120) as client:
            # 1. Crear container
            r = await client.post(f"{GRAPH_BASE}/{ig_user_id}/media", params={
                "access_token": self.access_token,
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
            })
            _check_meta_error(r)
            container_id = r.json()["id"]

            # 2. Polling del estado del container (máx. 5 min)
            import asyncio
            for attempt in range(30):
                await asyncio.sleep(10)
                status_r = await client.get(f"{GRAPH_BASE}/{container_id}", params={
                    "access_token": self.access_token,
                    "fields": "status_code,status",
                })
                status_data = status_r.json()
                code = status_data.get("status_code")

                if code == "FINISHED":
                    break
                elif code == "ERROR":
                    return PublishResult(
                        success=False,
                        error_message=f"Meta rechazó el video: {status_data.get('status')}",
                        error_type="invalid_content",
                    )
                # IN_PROGRESS → seguir esperando

            else:
                return PublishResult(success=False, error_message="Timeout esperando que Meta procese el video", error_type="temporary")

            # 3. Publicar
            pub_r = await client.post(f"{GRAPH_BASE}/{ig_user_id}/media_publish", params={
                "access_token": self.access_token,
                "creation_id": container_id,
            })
            _check_meta_error(pub_r)
            pub_id = pub_r.json()["id"]

            return PublishResult(
                success=True,
                remote_id=pub_id,
                remote_url=f"https://www.instagram.com/p/{pub_id}/",
            )

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """Instagram no expone scheduling via API pública aún — publicar inmediatamente."""
        return await self.publish(job_data)

    async def get_publication_status(self, remote_id: str) -> str:
        """Consulta estado de una publicación."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/{remote_id}", params={
                "access_token": self.access_token,
                "fields": "id,timestamp",
            })
            if r.status_code == 200:
                return "published"
            return "failed"

    async def get_metrics(self, remote_id: str) -> MetricsData:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/{remote_id}/insights", params={
                "access_token": self.access_token,
                "metric": "plays,likes,comments,shares,reach",
                "period": "lifetime",
            })
            if r.status_code != 200:
                return MetricsData()
            data = r.json().get("data", [])
            metrics = {item["name"]: item.get("values", [{}])[-1].get("value", 0) for item in data}
            return MetricsData(
                views=metrics.get("plays"),
                likes=metrics.get("likes"),
                comments=metrics.get("comments"),
                shares=metrics.get("shares"),
                reach=metrics.get("reach"),
                raw_data=metrics,
            )


def _check_meta_error(response: httpx.Response):
    """Lanza excepción tipada según el error de Meta Graph API."""
    if response.status_code == 200:
        return
    try:
        error = response.json().get("error", {})
    except Exception:
        error = {}

    code = error.get("code", 0)
    msg = error.get("message", response.text)

    if code in (190, 102, 463, 467):
        raise ProviderAuthError(f"Token inválido o expirado: {msg}")
    if code == 32 or response.status_code == 429:
        raise ProviderRateLimitError(f"Rate limit: {msg}", retry_after=3600)
    if code in (100, 200, 10):
        raise ProviderContentError(f"Contenido rechazado: {msg}")
    raise ProviderTemporaryError(f"Error Meta API ({code}): {msg}")
