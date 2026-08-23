"""
Importar todos los providers para que se registren en ProviderRegistry.
El orden no importa; cada @ProviderRegistry.register(...) se ejecuta al importar.
"""

from app.providers.base import ProviderRegistry, SocialProvider
from app.providers.instagram import InstagramProvider
from app.providers.facebook import FacebookProvider
from app.providers.tiktok import TikTokProvider
from app.providers.youtube import YouTubeProvider

__all__ = [
    "ProviderRegistry",
    "SocialProvider",
    "InstagramProvider",
    "FacebookProvider",
    "TikTokProvider",
    "YouTubeProvider",
]
