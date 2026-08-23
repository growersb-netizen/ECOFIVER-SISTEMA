"""
API de publicaciones — el flujo principal de Viral Hub.

POST /publications  → crea Publication + N PublicationJobs + encola workers
GET  /publications  → historial con filtros
GET  /publications/{id}/jobs → estado en tiempo real de cada job
POST /publications/{id}/jobs/{job_id}/retry → reintento individual
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.models.user import User
from app.models.workspace import Membership
from app.models.channel import SocialChannel, ChannelGroup
from app.models.media import MediaAsset
from app.models.publication import Publication, PublicationJob, PublicationStatus
from app.workers.publish_task import publish_job

router = APIRouter(prefix="/workspaces/{workspace_id}/publications", tags=["Publications"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_publication(
    workspace_id: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """
    Crea una Publication y encola N PublicationJobs.

    Body esperado:
    {
      "media_asset_id": 1,
      "captions": {"default": "...", "instagram": "...", "tiktok": "..."},
      "platform_settings": {"youtube": {"title": "...", "privacy": "public"}},
      "channel_ids": [1, 2, 3],         # canales individuales
      "group_ids": [1, 2],              # grupos (se expanden a canales)
      "scheduled_at": "2025-01-15T20:00:00Z"  # opcional
    }
    """
    media_asset_id = payload.get("media_asset_id")
    channel_ids: list[int] = payload.get("channel_ids", [])
    group_ids: list[int] = payload.get("group_ids", [])

    # Verificar asset
    asset_result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == media_asset_id,
            MediaAsset.workspace_id == workspace_id,
        )
    )
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset no encontrado")

    # Resolver canales desde grupos
    all_channel_ids = set(channel_ids)
    if group_ids:
        groups_result = await db.execute(
            select(ChannelGroup)
            .where(ChannelGroup.id.in_(group_ids), ChannelGroup.workspace_id == workspace_id)
            .options(selectinload(ChannelGroup.channels))
        )
        for group in groups_result.scalars():
            all_channel_ids.update(c.id for c in group.channels if c.is_active)

    if not all_channel_ids:
        raise HTTPException(status_code=400, detail="No hay canales destino seleccionados")

    # Verificar que los canales pertenecen al workspace
    channels_result = await db.execute(
        select(SocialChannel).where(
            SocialChannel.id.in_(all_channel_ids),
            SocialChannel.workspace_id == workspace_id,
            SocialChannel.is_active == True,
        )
    )
    channels = channels_result.scalars().all()
    valid_channel_ids = [c.id for c in channels]

    if not valid_channel_ids:
        raise HTTPException(status_code=400, detail="Ningún canal activo disponible")

    # Crear Publication
    publication = Publication(
        workspace_id=workspace_id,
        media_asset_id=media_asset_id,
        created_by_id=current_user.id,
        captions=payload.get("captions", {}),
        platform_settings=payload.get("platform_settings", {}),
        target_channel_ids=valid_channel_ids,
        scheduled_at=payload.get("scheduled_at"),
        status=PublicationStatus.queued,
        total_jobs=len(valid_channel_ids),
        jobs_pending=len(valid_channel_ids),
    )
    db.add(publication)
    await db.flush()  # para obtener publication.id

    # Crear un PublicationJob por cada canal destino
    jobs = []
    for channel_id in valid_channel_ids:
        idempotency_key = f"pub-{publication.id}-ch-{channel_id}-{uuid.uuid4().hex[:8]}"
        job = PublicationJob(
            publication_id=publication.id,
            channel_id=channel_id,
            job_idempotency_key=idempotency_key,
            status=PublicationStatus.queued,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        jobs.append((channel_id, idempotency_key))

    await db.commit()

    # Encolar en Celery por plataforma (fuera de la transacción)
    for job_obj in publication.jobs if hasattr(publication, 'jobs') else []:
        channel = next((c for c in channels if c.id == job_obj.channel_id), None)
        if channel:
            publish_job.apply_async(
                args=[job_obj.id],
                queue=channel.platform.value,
                task_id=f"job-{job_obj.id}",
            )

    return {
        "publication_id": publication.id,
        "total_jobs": len(valid_channel_ids),
        "status": "queued",
        "message": f"Se encolaron {len(valid_channel_ids)} publicaciones",
    }


@router.get("")
async def list_publications(
    workspace_id: int,
    status_filter: str | None = Query(None, alias="status"),
    platform: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Historial de publicaciones con filtros opcionales."""
    query = select(Publication).where(Publication.workspace_id == workspace_id)

    if status_filter:
        query = query.where(Publication.status == PublicationStatus(status_filter))

    query = query.order_by(Publication.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    publications = result.scalars().all()

    return {"items": [_publication_to_dict(p) for p in publications], "page": page, "per_page": per_page}


@router.get("/{publication_id}/jobs")
async def get_publication_jobs(
    workspace_id: int,
    publication_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Estado de cada job — para progreso en tiempo real (polling o SSE)."""
    result = await db.execute(
        select(PublicationJob)
        .where(PublicationJob.publication_id == publication_id)
        .options(selectinload(PublicationJob.channel))
    )
    jobs = result.scalars().all()
    return {"jobs": [_job_to_dict(j) for j in jobs]}


@router.post("/{publication_id}/jobs/{job_id}/retry")
async def retry_job(
    workspace_id: int,
    publication_id: int,
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Reintenta un job fallido manualmente."""
    result = await db.execute(
        select(PublicationJob)
        .where(PublicationJob.id == job_id, PublicationJob.publication_id == publication_id)
        .options(selectinload(PublicationJob.channel))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    if job.status == PublicationStatus.published:
        raise HTTPException(status_code=400, detail="El job ya fue publicado exitosamente")

    job.status = PublicationStatus.queued
    job.next_retry_at = None
    await db.commit()

    publish_job.apply_async(args=[job.id], queue=job.channel.platform.value)
    return {"message": "Job reencolado", "job_id": job_id}


def _publication_to_dict(p: Publication) -> dict:
    return {
        "id": p.id,
        "status": p.status.value,
        "total_jobs": p.total_jobs,
        "jobs_published": p.jobs_published,
        "jobs_failed": p.jobs_failed,
        "jobs_pending": p.jobs_pending,
        "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
        "created_at": p.created_at.isoformat(),
    }


def _job_to_dict(j: PublicationJob) -> dict:
    return {
        "id": j.id,
        "channel_id": j.channel_id,
        "channel_name": j.channel.alias if j.channel else None,
        "platform": j.channel.platform.value if j.channel else None,
        "status": j.status.value,
        "attempt_count": j.attempt_count,
        "remote_url": j.remote_url,
        "last_error": j.last_error,
        "published_at": j.published_at.isoformat() if j.published_at else None,
    }
