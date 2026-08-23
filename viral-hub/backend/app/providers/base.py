"""
Interfaz abstracta SocialProvider — sección 36 del blueprint.

Agregar una nueva red social = implementar esta interfaz + registrar en REGISTRY.
El core nunca habla directamente con Instagram/TikTok/YouTube/Facebook;
siempre pasa por este contrato.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


# ─── Capacidades declarables por cada provider ───────────────────────────────

class Capability(str, Enum):
    direct_publish = "direct_publish"       # puede publicar ahora
    scheduling = "scheduling"               # puede programar via API
    video = "video"                         # acepta video
    image = "image"                         # acepta imagen
    short_video = "short_video"             # video corto (<60s o similar)
    custom_caption = "custom_caption"       # acepta caption/descripción
    custom_title = "custom_title"           # acepta título separado
    analytics = "analytics"                 # expone métricas
    publication_status = "publication_status"  # permite consultar estado post-publicación


@dataclass
class ProviderCapabilities:
    """Capacidades de un provider. Se declaran al conectar el canal."""
    supported: list[Capability] = field(default_factory=list)

    def supports(self, cap: Capability) -> bool:
        return cap in self.supported


# ─── Tipos de resultado ───────────────────────────────────────────────────────

@dataclass
class PublishResult:
    success: bool
    remote_id: str | None = None          # ID de la publicación en la plataforma
    remote_url: str | None = None         # URL pública
    scheduled_at: str | None = None       # si fue programada
    error_message: str | None = None
    error_type: str | None = None         # JobErrorType value
    raw_response: dict | None = None      # respuesta cruda para debug


@dataclass
class ChannelInfo:
    """Información básica del canal recuperada al conectar."""
    remote_id: str
    remote_name: str
    remote_username: str | None
    avatar_url: str | None
    platform_meta: dict = field(default_factory=dict)


@dataclass
class MetricsData:
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    followers_gained: int | None = None
    reach: int | None = None
    raw_data: dict | None = None


# ─── Interfaz abstracta ───────────────────────────────────────────────────────

class SocialProvider(ABC):
    """
    Contrato que debe cumplir cada conector de plataforma.

    Uso típico:
        provider = InstagramProvider(credentials)
        result = await provider.publish(job)
    """

    platform_name: str = "base"  # sobreescribir en cada provider

    def __init__(self, access_token: str, refresh_token: str | None = None):
        self.access_token = access_token
        self.refresh_token = refresh_token

    @abstractmethod
    async def connect(self, auth_code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        Intercambia el auth_code por access_token (y refresh_token si aplica).
        Retorna (access_token, refresh_token).
        """
        ...

    @abstractmethod
    async def refresh_auth(self) -> tuple[str, str | None]:
        """
        Renueva el access_token usando el refresh_token.
        Retorna (new_access_token, new_refresh_token).
        Lanza ProviderAuthError si el refresh falló.
        """
        ...

    @abstractmethod
    async def get_channel_info(self) -> ChannelInfo:
        """
        Retorna información básica del canal (nombre, avatar, id remoto).
        Llamar justo después de connect() para poblar SocialChannel.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """
        Declara qué puede hacer este provider.
        Se llama una vez al conectar y se guarda en SocialChannel.capabilities.
        """
        ...

    @abstractmethod
    async def validate_media(self, media_type: str, file_size_bytes: int,
                              duration_seconds: float | None, mime_type: str) -> tuple[bool, str | None]:
        """
        Valida si el media es compatible con esta plataforma.
        Retorna (is_valid, error_message).
        """
        ...

    @abstractmethod
    async def publish(self, job_data: dict) -> PublishResult:
        """
        Publica el contenido ahora.
        job_data contiene: storage_url, caption, title, platform_settings, idempotency_key.
        DEBE ser idempotente — verificar idempotency_key si la plataforma lo permite.
        """
        ...

    @abstractmethod
    async def schedule_publication(self, job_data: dict, scheduled_at: str) -> PublishResult:
        """
        Programa la publicación para una fecha/hora específica (ISO 8601).
        Solo disponible si Capability.scheduling está en get_capabilities().
        """
        ...

    @abstractmethod
    async def get_publication_status(self, remote_id: str) -> str:
        """
        Consulta el estado de una publicación en la plataforma.
        Retorna un PublicationStatus value.
        """
        ...

    @abstractmethod
    async def get_metrics(self, remote_id: str) -> MetricsData:
        """
        Obtiene métricas de una publicación ya publicada.
        Solo disponible si Capability.analytics está en get_capabilities().
        """
        ...


# ─── Registro de providers ────────────────────────────────────────────────────

class ProviderRegistry:
    """
    Registro central de providers.
    El core pregunta aquí por el provider correspondiente a una plataforma.
    Agregar un provider nuevo = registrarlo acá.
    """
    _registry: dict[str, type[SocialProvider]] = {}

    @classmethod
    def register(cls, platform: str):
        """Decorator para registrar un provider."""
        def decorator(provider_class: type[SocialProvider]):
            cls._registry[platform] = provider_class
            return provider_class
        return decorator

    @classmethod
    def get(cls, platform: str) -> type[SocialProvider]:
        if platform not in cls._registry:
            raise ValueError(f"No hay provider registrado para la plataforma: {platform}")
        return cls._registry[platform]

    @classmethod
    def available_platforms(cls) -> list[str]:
        return list(cls._registry.keys())


# ─── Excepciones ──────────────────────────────────────────────────────────────

class ProviderError(Exception):
    """Error genérico de provider."""

class ProviderAuthError(ProviderError):
    """Token expirado, revocado o inválido."""

class ProviderRateLimitError(ProviderError):
    """Rate limit alcanzado. Incluir retry_after en segundos."""
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after

class ProviderContentError(ProviderError):
    """Contenido no válido para la plataforma (tamaño, formato, duración, etc.)."""

class ProviderTemporaryError(ProviderError):
    """Error temporal — reintentar con backoff."""
