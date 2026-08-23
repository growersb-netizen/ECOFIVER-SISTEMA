"""
API de workspace — stats del dashboard y configuración del workspace.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.models.user import User
from app.models.workspace import Workspace, Membership, Subscription
from app.models.channel import SocialChannel
from app.models.publication import Publication, PublicationJob, PublicationStatus

router = APIRouter(prefix="/workspaces", tags=["Workspace"])


class UpdateWorkspacePayload(BaseModel):
    name: str | None = None
    logo_url: str | None = None


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(
        select(Workspace, Subscription)
        .outerjoin(Subscription, Subscription.workspace_id == Workspace.id)
        .where(Workspace.id == workspace_id)
    )
    row = result.first()
    if not row:
        return {"error": "Workspace no encontrado"}

    ws, sub = row
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "logo_url": ws.logo_url,
        "plan": sub.plan_name if sub else "free",
        "plan_config": sub.plan_config if sub else {},
        "subscription_status": sub.status.value if sub else None,
    }


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: int,
    payload: UpdateWorkspacePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace no encontrado")
    if payload.name is not None:
        ws.name = payload.name
    if payload.logo_url is not None:
        ws.logo_url = payload.logo_url
    await db.commit()
    await db.refresh(ws)
    return {"id": ws.id, "name": ws.name, "slug": ws.slug, "logo_url": ws.logo_url}


@router.get("/{workspace_id}/stats")
async def get_dashboard_stats(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Stats para el dashboard: canales, publicaciones, cola, errores."""
    from datetime import date, timezone, datetime

    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    # Canales activos
    channels_count = await db.scalar(
        select(func.count(SocialChannel.id)).where(
            SocialChannel.workspace_id == workspace_id,
            SocialChannel.is_active == True,
        )
    )

    # Publicaciones de hoy (jobs publicados hoy)
    published_today = await db.scalar(
        select(func.count(PublicationJob.id))
        .join(Publication, PublicationJob.publication_id == Publication.id)
        .where(
            Publication.workspace_id == workspace_id,
            PublicationJob.status == PublicationStatus.published,
            PublicationJob.published_at >= today_start,
        )
    )

    # En cola (queued + processing + retrying)
    in_queue = await db.scalar(
        select(func.count(PublicationJob.id))
        .join(Publication, PublicationJob.publication_id == Publication.id)
        .where(
            Publication.workspace_id == workspace_id,
            PublicationJob.status.in_([
                PublicationStatus.queued,
                PublicationStatus.processing,
                PublicationStatus.retrying,
            ]),
        )
    )

    # Con error
    with_errors = await db.scalar(
        select(func.count(PublicationJob.id))
        .join(Publication, PublicationJob.publication_id == Publication.id)
        .where(
            Publication.workspace_id == workspace_id,
            PublicationJob.status.in_([
                PublicationStatus.failed,
                PublicationStatus.needs_reconnect,
            ]),
        )
    )

    # Últimas 5 publicaciones
    recent_result = await db.execute(
        select(Publication)
        .where(Publication.workspace_id == workspace_id)
        .order_by(Publication.created_at.desc())
        .limit(5)
    )
    recent = recent_result.scalars().all()

    return {
        "channels_connected": channels_count or 0,
        "published_today": published_today or 0,
        "in_queue": in_queue or 0,
        "with_errors": with_errors or 0,
        "recent_publications": [
            {
                "id": p.id,
                "total_jobs": p.total_jobs,
                "jobs_published": p.jobs_published,
                "jobs_failed": p.jobs_failed,
                "status": p.status.value,
                "created_at": p.created_at.isoformat(),
            }
            for p in recent
        ],
    }


@router.get("")
async def list_my_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los workspaces a los que pertenece el usuario autenticado."""
    result = await db.execute(
        select(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == current_user.id, Membership.is_active == True)
        .order_by(Membership.joined_at)
    )
    rows = result.all()
    return {
        "workspaces": [
            {
                "id": ws.id,
                "name": ws.name,
                "slug": ws.slug,
                "logo_url": ws.logo_url,
                "role": m.role.value,
            }
            for ws, m in rows
        ]
    }
