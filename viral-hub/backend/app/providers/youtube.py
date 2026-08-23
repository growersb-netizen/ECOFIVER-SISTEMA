"""
YouTubeProvider — YouTube Data API v3 (Resumable Upload).

Requisitos:
1. Crear proyecto en console.cloud.google.com
2. Habilitar YouTube Data API v3
3. Crear credenciales OAuth 2.0 (tipo "Web Application")
4. Agregar redirect URI en la consola
5. Configurar GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI en .env

Nota sobre Shorts:
  Para que un video sea detectado como Short:
  - Duración ≤ 60 segundos Y relación de aspecto vertical (9:16 ideal)
  - Agregar #Shorts en el título o descripción
  No hay un parámetro especial de la API para Shorts — se clasifica automáticamente.

Documentación:
  https://developers.google.com/youtube/v3/docs/videos/insert
"""

import httpx
import asyncio
from app.core.config import get_settings
from app.providers.base import (
    SocialProvider, ProviderCapabilities, Capability,
    PublishResult, ChannelInfo, MetricsData,
    ProviderAuthError, ProviderRateLimitError, ProviderContentError, ProviderTemporaryError,
    ProviderRegistry,
)

settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_API_BASE = "https://www.googleapis.com/youtube/v3"
YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


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

    @staticmethod
    def get_oauth_url(redirect_uri: str, state: str = "") -> str:
        import urllib.parse
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "response_type": "code",
            "access_type": "offline",   # para obtener refresh_token
            "prompt": "consent",         # forzar para obtener refresh siempre
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })
            _check_google_error(r)
            data = r.json()
            return data["access_token"], data.get("refresh_token")

    async def refresh_auth(self) -> tuple[str, str | None]:
        if not self.refresh_token:
            raise ProviderAuthError("Sin refresh_token — el usuario debe reconectar su canal de YouTube")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            })
            _check_google_error(r)
            data = r.json()
            return data["access_token"], self.refresh_token  # refresh_token no cambia

    async def get_channel_info(self) -> ChannelInfo:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{YT_API_BASE}/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            _check_google_error(r)
            items = r.json().get("items", [])
            if not items:
                raise ProviderAuthError("No se encontró canal de YouTube para este usuario")
            ch = items[0]
            snippet = ch.get("snippet", {})
            thumbnail = snippet.get("thumbnails", {}).get("default", {}).get("url")
            return ChannelInfo(
                remote_id=ch["id"],
                remote_name=snippet.get("title", ""),
                remote_username=snippet.get("customUrl"),
                avatar_url=thumbnail,
                platform_meta={"description": snippet.get("description", "")[:200]},
            )

    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        allowed = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/mpeg", "video/3gpp"}
        if mime_type not in allowed:
            return False, f"YouTube no acepta {mime_type}"
        if file_size_bytes > 256 * 1024 * 1024 * 1024:  # 256 GB
            return False, "Supera el límite de 256 GB de YouTube"
        return True, None

    async def publish(self, job_data: dict) -> PublishResult:
        """
        Sube un video a YouTube usando Resumable Upload.
        El video se descarga desde la URL pública y se sube a YouTube.

        Para Shorts: el título debe incluir #Shorts si el video es vertical y ≤60s.
        """
        video_url = job_data.get("storage_url")
        title = job_data.get("title") or job_data.get("caption", "")[:100] or "Video"
        description = job_data.get("caption", "")
        duration = job_data.get("duration_seconds", 0)
        width = job_data.get("width", 1920)
        height = job_data.get("height", 1080)

        # Detectar si es Short
        is_short = duration and duration <= 60 and height > width
        if is_short and "#Shorts" not in title and "#Shorts" not in description:
            description = f"{description}\n\n#Shorts".strip()

        snippet = {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": "22",  # People & Blogs (genérico)
        }
        status_body = {"privacyStatus": "public"}

        if job_data.get("platform_settings", {}).get("privacy"):
            status_body["privacyStatus"] = job_data["platform_settings"]["privacy"]

        async with httpx.AsyncClient(timeout=60) as client:
            # Inicializar resumable upload
            init_r = await client.post(
                YT_UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                json={"snippet": snippet, "status": status_body},
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "X-Upload-Content-Type": "video/*",
                },
            )
            _check_google_error(init_r)
            upload_url = init_r.headers.get("Location")
            if not upload_url:
                return PublishResult(success=False, error_message="YouTube no devolvió URL de upload", error_type="temporary")

            # Descargar y subir el video
            async with httpx.AsyncClient(timeout=600) as upload_client:
                download_r = await upload_client.get(video_url)
                download_r.raise_for_status()
                video_bytes = download_r.content
                file_size = len(video_bytes)

                upload_r = await upload_client.put(
                    upload_url,
                    content=video_bytes,
                    headers={
                        "Content-Type": "video/*",
                        "Content-Length": str(file_size),
                    },
                )

                if upload_r.status_code in (200, 201):
                    video_data = upload_r.json()
                    video_id = video_data["id"]
                    return PublishResult(
                        success=True,
                        remote_id=video_id,
                        remote_url=f"https://www.youtube.com/watch?v={video_id}",
                        raw_response=video_data,
                    )

                _check_google_error(upload_r)
                return PublishResult(success=False, error_message=f"Upload falló: HTTP {upload_r.status_code}", error_type="temporary")

    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """
        YouTube soporta scheduling: privacyStatus=private + publishAt.
        publishAt debe ser una fecha futura en formato RFC 3339.
        """
        job_data_with_settings = {**job_data}
        job_data_with_settings.setdefault("platform_settings", {})["privacy"] = "private"
        job_data_with_settings["scheduled_publish_at"] = scheduled_at
        return await self.publish(job_data_with_settings)

    async def get_publication_status(self, remote_id: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{YT_API_BASE}/videos",
                params={"part": "status", "id": remote_id},
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            if r.status_code != 200:
                return "failed"
            items = r.json().get("items", [])
            if not items:
                return "failed"
            upload_status = items[0].get("status", {}).get("uploadStatus", "")
            return "published" if upload_status == "processed" else "processing"

    async def get_metrics(self, remote_id: str) -> MetricsData:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{YT_API_BASE}/videos",
                params={"part": "statistics", "id": remote_id},
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            if r.status_code != 200:
                return MetricsData()
            items = r.json().get("items", [])
            if not items:
                return MetricsData()
            stats = items[0].get("statistics", {})
            return MetricsData(
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                shares=None,
                raw_data=stats,
            )


def _check_google_error(response: httpx.Response):
    if response.status_code in (200, 201):
        return
    try:
        error = response.json().get("error", {})
    except Exception:
        error = {}
    code = response.status_code
    msg = error.get("message", response.text[:200])
    errors = error.get("errors", [])
    reason = errors[0].get("reason", "") if errors else ""

    if code in (401, 403) or reason in ("authError", "forbidden"):
        raise ProviderAuthError(f"YouTube auth error: {msg}")
    if code == 429 or reason == "rateLimitExceeded":
        raise ProviderRateLimitError(msg, retry_after=3600)
    if reason in ("invalidVideoMetadata", "uploadLimitExceeded", "videoNotFound"):
        raise ProviderContentError(msg)
    raise ProviderTemporaryError(f"YouTube API ({code}): {msg}")
