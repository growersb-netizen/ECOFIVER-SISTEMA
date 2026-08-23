"""
TikTokProvider — Content Posting API (Direct Post / URL-based).

Requisitos:
1. Crear app en developers.tiktok.com
2. Agregar producto "Content Posting API"
3. Activar scope: video.publish, video.upload, user.info.basic
4. Pasar revisión de TikTok para levantar restricción de visibilidad
   (sin revisión: videos se publican como SELF_ONLY o MUTUAL_FOLLOW_FRIENDS)
5. Configurar TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI en .env

Documentación:
  https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
  https://developers.tiktok.com/docs/en/content-posting-api-get-started
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

API_BASE = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = f"{API_BASE}/oauth/token/"

MAX_VIDEO_SIZE_BYTES = 4_000_000_000
MIN_DURATION = 3
MAX_DURATION = 600


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

    @staticmethod
    def get_oauth_url(redirect_uri: str, state: str = "") -> str:
        import urllib.parse
        params = {
            "client_key": settings.TIKTOK_CLIENT_KEY,
            "redirect_uri": redirect_uri,
            "scope": "user.info.basic,video.publish,video.upload",
            "response_type": "code",
            "state": state,
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(TOKEN_URL, data={
                "client_key": settings.TIKTOK_CLIENT_KEY,
                "client_secret": settings.TIKTOK_CLIENT_SECRET,
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            _check_tiktok_error(r)
            data = r.json()["data"]
            return data["access_token"], data.get("refresh_token")

    async def refresh_auth(self) -> tuple[str, str | None]:
        if not self.refresh_token:
            raise ProviderAuthError("Sin refresh_token disponible")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(TOKEN_URL, data={
                "client_key": settings.TIKTOK_CLIENT_KEY,
                "client_secret": settings.TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            _check_tiktok_error(r)
            data = r.json()["data"]
            return data["access_token"], data.get("refresh_token")

    async def get_channel_info(self) -> ChannelInfo:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{API_BASE}/user/info/",
                params={"fields": "open_id,display_name,avatar_url,username"},
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            _check_tiktok_error(r)
            user = r.json()["data"]["user"]
            return ChannelInfo(
                remote_id=user["open_id"],
                remote_name=user.get("display_name", ""),
                remote_username=user.get("username"),
                avatar_url=user.get("avatar_url"),
            )

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        allowed = {"video/mp4", "video/quicktime", "video/webm"}
        if mime_type not in allowed:
            return False, f"TikTok no acepta {mime_type}. Usar MP4, MOV o WebM."
        if file_size_bytes > MAX_VIDEO_SIZE_BYTES:
            return False, "Supera límite de 4 GB de TikTok"
        if duration_seconds:
            if duration_seconds < MIN_DURATION:
                return False, f"Mínimo {MIN_DURATION}s de duración"
            if duration_seconds > MAX_DURATION:
                return False, f"Máximo {MAX_DURATION}s de duración"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Flujo URL-based (Direct Post):
        1. POST /post/publish/video/init/  → publish_id + upload_url
        2. PUT upload_url con el video
        3. Polling GET /post/publish/status/fetch/ hasta PUBLISH_COMPLETE
        """
        video_url = job_data.get("storage_url")
        caption = job_data.get("caption", "")
        file_size = job_data.get("file_size_bytes", 0)
        duration = job_data.get("duration_seconds", 0)

        async with httpx.AsyncClient(timeout=120) as client:
            # 1. Inicializar publicación
            init_r = await client.post(
                f"{API_BASE}/post/publish/video/init/",
                json={
                    "post_info": {
                        "title": caption[:150] if caption else "",
                        "privacy_level": "PUBLIC_TO_EVERYONE",  # requiere revisión
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                        "video_cover_timestamp_ms": 1000,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": min(file_size, 64 * 1024 * 1024),  # 64 MB chunks
                        "total_chunk_count": 1 if file_size <= 64 * 1024 * 1024 else -1,
                    },
                },
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            _check_tiktok_error(init_r)
            init_data = init_r.json()["data"]
            publish_id = init_data["publish_id"]
            upload_url = init_data["upload_url"]

            # 2. Subir el video desde la URL pública
            # Descargamos el stream y lo subimos a TikTok
            async with httpx.AsyncClient(timeout=300) as upload_client:
                download_r = await upload_client.get(video_url)
                download_r.raise_for_status()

                upload_r = await upload_client.put(
                    upload_url,
                    content=download_r.content,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes 0-{len(download_r.content)-1}/{len(download_r.content)}",
                    },
                )
                if upload_r.status_code not in (200, 201, 204):
                    return PublishResult(
                        success=False,
                        error_message=f"Error subiendo video a TikTok: {upload_r.status_code}",
                        error_type="temporary",
                    )

            # 3. Polling del estado
            for attempt in range(24):  # máx. 4 min
                await asyncio.sleep(10)
                status_r = await client.post(
                    f"{API_BASE}/post/publish/status/fetch/",
                    json={"publish_id": publish_id},
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                if status_r.status_code != 200:
                    continue
                status_data = status_r.json().get("data", {})
                status = status_data.get("status")

                if status == "PUBLISH_COMPLETE":
                    return PublishResult(
                        success=True,
                        remote_id=publish_id,
                        remote_url=f"https://www.tiktok.com/@user/video/{publish_id}",
                    )
                elif status in ("FAILED", "PUBLISH_FAILED"):
                    fail_reason = status_data.get("fail_reason", "desconocido")
                    return PublishResult(
                        success=False,
                        error_message=f"TikTok rechazó el video: {fail_reason}",
                        error_type="invalid_content",
                    )

            return PublishResult(success=False, error_message="Timeout esperando publicación en TikTok", error_type="temporary")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """TikTok no expone scheduling via API — publicar inmediatamente."""
        return await self.publish(job_data)

    async def get_publication_status(self, remote_id: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{API_BASE}/post/publish/status/fetch/",
                json={"publish_id": remote_id},
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            if r.status_code != 200:
                return "failed"
            status = r.json().get("data", {}).get("status", "")
            return "published" if status == "PUBLISH_COMPLETE" else "processing"

    async def get_metrics(self, remote_id: str) -> MetricsData:
        """TikTok Business API para métricas."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{API_BASE}/research/video/query/",
                params={
                    "fields": "like_count,comment_count,share_count,view_count",
                    "filters": f'{{"video_ids":["{remote_id}"]}}',
                },
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            if r.status_code != 200:
                return MetricsData()
            videos = r.json().get("data", {}).get("videos", [])
            if not videos:
                return MetricsData()
            v = videos[0]
            return MetricsData(
                views=v.get("view_count"),
                likes=v.get("like_count"),
                comments=v.get("comment_count"),
                shares=v.get("share_count"),
                raw_data=v,
            )


def _check_tiktok_error(response: httpx.Response):
    if response.status_code in (200, 201):
        data = response.json()
        error = data.get("error", {})
        code = error.get("code", "ok")
        if code in ("ok", "success", ""):
            return
        msg = error.get("message", str(data))
        if "access_token" in msg.lower() or "unauthorized" in msg.lower():
            raise ProviderAuthError(f"TikTok auth error: {msg}")
        if "rate" in msg.lower():
            raise ProviderRateLimitError(msg, retry_after=3600)
        raise ProviderTemporaryError(f"TikTok API: {msg}")
    if response.status_code in (401, 403):
        raise ProviderAuthError(f"TikTok: no autorizado ({response.status_code})")
    if response.status_code == 429:
        raise ProviderRateLimitError("TikTok rate limit", retry_after=3600)
    raise ProviderTemporaryError(f"TikTok HTTP {response.status_code}: {response.text[:200]}")
