"""
Endpoints de canales sociales.
La conexión OAuth se inicia desde el frontend (redirect a la plataforma)
y el callback llega acá para completar el intercambio de tokens.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.core.security import encrypt_token
from app.models.user import User
from app.models.workspace import Membership
from app.models.channel import SocialChannel, OAuthCredential, ChannelStatus
from app.providers import ProviderRegistry
from app.providers.base import ProviderAuthError

router = APIRouter(prefix="/workspaces/{workspace_id}/channels", tags=["Channels"])


@router.get("")
async def list_channels(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Lista todos los canales del workspace."""
    result = await db.execute(
        select(SocialChannel).where(
            SocialChannel.workspace_id == workspace_id,
            SocialChannel.is_active == True,
        ).order_by(SocialChannel.alias)
    )
    channels = result.scalars().all()
    return {"channels": [_channel_to_dict(c) for c in channels]}


@router.post("/oauth/{platform}/callback")
async def oauth_callback(
    workspace_id: int,
    platform: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """
    Recibe el auth_code del OAuth callback y completa la conexión del canal.
    El frontend redirige al usuario a la plataforma, esta devuelve el code,
    el frontend lo envía acá.
    """
    auth_code = payload.get("code")
    redirect_uri = payload.get("redirect_uri")

    if not auth_code:
        raise HTTPException(status_code=400, detail="Falta el código de autorización")

    try:
        ProviderClass = ProviderRegistry.get(platform)
        # Tokens temporales para el intercambio (sin credenciales aún)
        provider = ProviderClass(access_token="")
        access_token, refresh_token = await provider.connect(auth_code, redirect_uri)

        # Obtener info del canal
        provider_with_token = ProviderClass(access_token=access_token, refresh_token=refresh_token)
        channel_info = await provider_with_token.get_channel_info()
        capabilities = provider_with_token.get_capabilities()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProviderAuthError as e:
        raise HTTPException(status_code=401, detail=f"Error de autorización: {e}")
    except NotImplementedError:
        raise HTTPException(status_code=501, detail=f"Conector {platform} aún no implementado")

    # Verificar si ya existe un canal con este remote_id
    existing = await db.execute(
        select(SocialChannel).where(
            SocialChannel.workspace_id == workspace_id,
            SocialChannel.platform == platform,
            SocialChannel.remote_id == channel_info.remote_id,
        )
    )
    channel = existing.scalar_one_or_none()

    if channel:
        # Reconexión: actualizar tokens
        channel.status = ChannelStatus.connected
        channel.avatar_url = channel_info.avatar_url
        channel.capabilities = [c.value for c in capabilities.supported]
    else:
        # Canal nuevo
        channel = SocialChannel(
            workspace_id=workspace_id,
            platform=platform,
            alias=channel_info.remote_name or channel_info.remote_username or channel_info.remote_id,
            remote_id=channel_info.remote_id,
            remote_name=channel_info.remote_name,
            remote_username=channel_info.remote_username,
            avatar_url=channel_info.avatar_url,
            platform_meta=channel_info.platform_meta,
            capabilities=[c.value for c in capabilities.supported],
        )
        db.add(channel)
        await db.flush()

    # Guardar/actualizar credenciales cifradas
    cred_result = await db.execute(
        select(OAuthCredential).where(OAuthCredential.channel_id == channel.id)
    )
    cred = cred_result.scalar_one_or_none()

    if not cred:
        cred = OAuthCredential(channel_id=channel.id)
        db.add(cred)

    cred.access_token_enc = encrypt_token(access_token)
    cred.refresh_token_enc = encrypt_token(refresh_token) if refresh_token else None

    await db.commit()
    return {"channel": _channel_to_dict(channel), "message": "Canal conectado exitosamente"}


@router.patch("/{channel_id}")
async def update_channel(
    workspace_id: int,
    channel_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Renombrar alias del canal."""
    result = await db.execute(
        select(SocialChannel).where(
            SocialChannel.id == channel_id,
            SocialChannel.workspace_id == workspace_id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")

    if "alias" in payload:
        channel.alias = payload["alias"]

    await db.commit()
    return _channel_to_dict(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_channel(
    workspace_id: int,
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Desconecta (soft-delete) un canal y elimina sus credenciales."""
    result = await db.execute(
        select(SocialChannel).where(
            SocialChannel.id == channel_id,
            SocialChannel.workspace_id == workspace_id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")

    channel.is_active = False
    # La credencial se elimina en cascada (cascade="all, delete-orphan")
    await db.commit()


def _channel_to_dict(c: SocialChannel) -> dict:
    return {
        "id": c.id,
        "platform": c.platform.value,
        "alias": c.alias,
        "remote_username": c.remote_username,
        "avatar_url": c.avatar_url,
        "status": c.status.value,
        "capabilities": c.capabilities,
        "connected_at": c.connected_at.isoformat(),
    }
