"""
API de grupos de canales.
Un grupo permite publicar en múltiples canales con una sola selección.
El grupo "Todas" se crea automáticamente y no puede eliminarse.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.models.user import User
from app.models.workspace import Membership
from app.models.channel import ChannelGroup, SocialChannel

router = APIRouter(prefix="/workspaces/{workspace_id}/groups", tags=["Groups"])


class GroupCreate(BaseModel):
    name: str
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_groups(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(
        select(ChannelGroup)
        .where(ChannelGroup.workspace_id == workspace_id)
        .options(selectinload(ChannelGroup.channels))
        .order_by(ChannelGroup.is_system.desc(), ChannelGroup.name)
    )
    groups = result.scalars().all()
    return {"groups": [_group_to_dict(g) for g in groups]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_group(
    workspace_id: int,
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    group = ChannelGroup(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return _group_to_dict(group)


@router.patch("/{group_id}")
async def update_group(
    workspace_id: int,
    group_id: int,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(
        select(ChannelGroup).where(
            ChannelGroup.id == group_id,
            ChannelGroup.workspace_id == workspace_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if group.is_system:
        raise HTTPException(status_code=400, detail="El grupo 'Todas' no puede modificarse")

    if payload.name is not None:
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description

    await db.commit()
    return _group_to_dict(group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    workspace_id: int,
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(
        select(ChannelGroup).where(
            ChannelGroup.id == group_id,
            ChannelGroup.workspace_id == workspace_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if group.is_system:
        raise HTTPException(status_code=400, detail="El grupo 'Todas' no puede eliminarse")

    await db.delete(group)
    await db.commit()


@router.post("/{group_id}/channels")
async def add_channel_to_group(
    workspace_id: int,
    group_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Agrega un canal a un grupo. Body: {channel_id: int}"""
    channel_id = payload.get("channel_id")

    group_result = await db.execute(
        select(ChannelGroup)
        .where(ChannelGroup.id == group_id, ChannelGroup.workspace_id == workspace_id)
        .options(selectinload(ChannelGroup.channels))
    )
    group = group_result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    channel_result = await db.execute(
        select(SocialChannel).where(
            SocialChannel.id == channel_id,
            SocialChannel.workspace_id == workspace_id,
            SocialChannel.is_active == True,
        )
    )
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")

    if channel not in group.channels:
        group.channels.append(channel)
        await db.commit()

    return {"message": "Canal agregado al grupo"}


@router.delete("/{group_id}/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_from_group(
    workspace_id: int,
    group_id: int,
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(
        select(ChannelGroup)
        .where(ChannelGroup.id == group_id, ChannelGroup.workspace_id == workspace_id)
        .options(selectinload(ChannelGroup.channels))
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    group.channels = [c for c in group.channels if c.id != channel_id]
    await db.commit()


def _group_to_dict(g: ChannelGroup) -> dict:
    channels = g.channels if hasattr(g, "channels") and g.channels else []
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "is_system": g.is_system,
        "channel_count": len(channels),
        "channels": [{"id": c.id, "alias": c.alias, "platform": c.platform.value} for c in channels],
        "created_at": g.created_at.isoformat(),
    }
