"""
API de publicaciones — el flujo principal de Viral Hub.

POST /publications             → crea Publication + N PublicationJobs + encola workers
GET  /publications             → historial con filtros
GET  /publications/{id}/jobs   → estado en tiempo real de cada job
POST /publications/jobs/{job_id}/retry  → reintento individual
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.models.user import User
from app.models.workspace import Membership
from app.models.channel import SocialChannel, ChannelGroup
from app.models.media import MediaAsset
from app.models.publication import Publication, PublicationJob, PublicationStatus
from app.workers.publish_task import publish_job, run_job_direct

router = APIRouter(prefix="/workspaces/{workspace_id}/publications", tags=["Publications"])


class CreatePublicationPayload(BaseModel):
    caption: str
    per_platform_captions: dict[str, str] | None = None
    asset_id: int | None = None
    channel_ids: list[int] | None = None
    group_ids: list[int] | None = None
    scheduled_at: str | None = None


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_publication(
    workspace_id: int,
    payload: CreatePublicationPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """
    Crea una Publication y encola N PublicationJobs.
    """
    # Verificar asset si se proporcionó
    asset = None
    if payload.asset_id:
        asset_result = await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == payload.asset_id,
                MediaAsset.workspace_id == workspace_id,
            )
        )
        asset = asset_result.scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="Asset no encontrado")

    # Resolver canales
    channel_ids = list(payload.channel_ids or [])
    all_channel_ids = set(channel_ids)

    if payload.group_ids:
        groups_result = await db.execute(
            select(ChannelGroup)
            .where(ChannelGroup.id.in_(payload.group_ids), ChannelGroup.workspace_id == workspace_id)
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

    # Construir captions dict en formato interno
    captions = {"default": payload.caption}
    if payload.per_platform_captions:
        captions.update(payload.per_platform_captions)

    # Crear Publication
    publication = Publication(
        workspace_id=workspace_id,
        media_asset_id=payload.asset_id,
        created_by_id=current_user.id,
        captions=captions,
        target_channel_ids=valid_channel_ids,
        scheduled_at=payload.scheduled_at,
        status=PublicationStatus.queued,
        total_jobs=len(valid_channel_ids),
        jobs_pending=len(valid_channel_ids),
    )
    db.add(publication)
    await db.flush()  # para obtener publication.id

    # Crear PublicationJobs
    created_jobs: list[PublicationJob] = []
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
        created_jobs.append(job)

    await db.commit()
    for job in created_jobs:
        await db.refresh(job)

    # Encolar en Celery — con fallback a FastAPI BackgroundTasks si no hay broker
    channel_map = {c.id: c for c in channels}
    for job in created_jobs:
        channel = channel_map.get(job.channel_id)
        if channel:
            celery_ok = False
            try:
                publish_job.apply_async(
                    args=[job.id],
                    queue=channel.platform.value,
                    task_id=f"job-{job.id}",
                )
                celery_ok = True
            except Exception:
                pass  # broker no disponible

            if not celery_ok:
                # Fallback: procesar directamente en el proceso FastAPI
                background_tasks.add_task(run_job_direct, job.id)

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
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Historial de publicaciones con filtros opcionales."""
    query = select(Publication).where(Publication.workspace_id == workspace_id)

    if status_filter:
        try:
            query = query.where(Publication.status == PublicationStatus(status_filter))
        except ValueError:
            pass

    query = query.order_by(Publication.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    publications = result.scalars().all()

    return {"publications": [_publication_to_dict(p) for p in publications]}


@router.get("/{publication_id}/jobs")
async def get_publication_jobs(
    workspace_id: int,
    publication_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Estado de cada job — para progreso en tiempo real (polling)."""
    result = await db.execute(
        select(PublicationJob)
        .where(PublicationJob.publication_id == publication_id)
        .options(selectinload(PublicationJob.channel))
    )
    jobs = result.scalars().all()
    return {"jobs": [_job_to_dict(j) for j in jobs]}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    workspace_id: int,
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Reintenta un job fallido manualmente."""
    result = await db.execute(
        select(PublicationJob)
        .where(PublicationJob.id == job_id)
        .options(selectinload(PublicationJob.channel))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    # Verificar que el job pertenece al workspace
    pub_result = await db.execute(
        select(Publication).where(
            Publication.id == job.publication_id,
            Publication.workspace_id == workspace_id,
        )
    )
    if not pub_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job no encontrado")

    if job.status == PublicationStatus.published:
        raise HTTPException(status_code=400, detail="El job ya fue publicado exitosamente")

    job.status = PublicationStatus.queued
    job.next_retry_at = None
    await db.commit()

    if job.channel:
        celery_ok = False
        try:
            publish_job.apply_async(args=[job.id], queue=job.channel.platform.value)
            celery_ok = True
        except Exception:
            pass  # broker no disponible
        if not celery_ok:
            background_tasks.add_task(run_job_direct, job.id)

    return {"message": "Job reencolado", "job_id": job_id}


def _publication_to_dict(p: Publication) -> dict:
    caption = ""
    if isinstance(p.captions, dict):
        caption = p.captions.get("default", "") or next(iter(p.captions.values()), "")

    return {
        "id": p.id,
        "status": p.status.value,
        "caption": caption,
        "total_jobs": p.total_jobs,
        "jobs_published": p.jobs_published,
        "jobs_failed": p.jobs_failed,
        "jobs_pending": p.jobs_pending,
        "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        # Métricas agregadas (actualizadas por worker_metrics)
        "total_views": getattr(p, "total_views", 0) or 0,
        "total_likes": getattr(p, "total_likes", 0) or 0,
        "total_shares": getattr(p, "total_shares", 0) or 0,
        "total_comments": getattr(p, "total_comments", 0) or 0,
    }


def _job_to_dict(j: PublicationJob) -> dict:
    return {
        "id": j.id,
        "publication_id": j.publication_id,
        "platform": j.channel.platform.value if j.channel else None,
        "status": j.status.value,
        "attempt_count": j.attempt_count,
        "remote_id": j.remote_publication_id,
        "remote_url": j.remote_url,
        "error_message": j.last_error,
        "error_type": j.error_type.value if j.error_type else None,
        "published_at": j.published_at.isoformat() if j.published_at else None,
    }
