"""
publish_job — tarea central del motor de distribución.

Procesa un PublicationJob: obtiene el provider correcto, descifra el token,
valida idempotencia, llama a la API de la plataforma y actualiza el estado.

Errores clasificados:
  - ProviderAuthError     → estado needs_reconnect, no reintentar
  - ProviderRateLimitError → reintentar después de retry_after segundos
  - ProviderContentError   → failed definitivo, sin reintento
  - ProviderTemporaryError → backoff exponencial
  - Excepción genérica     → backoff exponencial, hasta max_retries
"""

import logging
from datetime import datetime, timezone, timedelta
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_token
from app.models.publication import PublicationJob, PublicationStatus, JobErrorType
from app.models.channel import SocialChannel, OAuthCredential
from app.models.media import MediaAsset
from app.providers import ProviderRegistry
from app.providers.base import (
    ProviderAuthError, ProviderRateLimitError,
    ProviderContentError, ProviderTemporaryError,
)

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.publish_task.publish_job",
    max_retries=5,
    default_retry_delay=60,
    acks_late=True,
)
def publish_job(self, job_id: int):
    """
    Publica un PublicationJob a su canal destino.

    Este task es síncrono porque Celery no soporta tasks async nativamente
    sin configuración extra. Para async, usar asgiref o un runner event loop.
    """
    import asyncio
    try:
        asyncio.run(_publish_job_async(self, job_id))
    except Exception as exc:
        logger.exception(f"publish_job [{job_id}] excepción no controlada: {exc}")
        raise


async def _publish_job_async(task, job_id: int):
    """Lógica async del publish job."""
    async with AsyncSessionLocal() as db:
        # Cargar job con relaciones necesarias
        result = await db.execute(
            select(PublicationJob)
            .where(PublicationJob.id == job_id)
            .options(
                selectinload(PublicationJob.channel).selectinload(SocialChannel.credential),
                selectinload(PublicationJob.publication).selectinload(
                    "media_asset"  # type: ignore
                ),
            )
        )
        job = result.scalar_one_or_none()

        if job is None:
            logger.error(f"PublicationJob {job_id} no encontrado")
            return

        # ── Idempotencia ──────────────────────────────────────────────────────
        if job.status == PublicationStatus.published:
            logger.info(f"Job {job_id} ya publicado — ignorar")
            return

        if job.status == PublicationStatus.cancelled:
            logger.info(f"Job {job_id} cancelado — ignorar")
            return

        # ── Marcar como procesando ────────────────────────────────────────────
        job.status = PublicationStatus.processing
        job.started_at = datetime.now(timezone.utc)
        job.attempt_count += 1
        await db.commit()

        channel = job.channel
        publication = job.publication

        try:
            # ── Obtener provider ──────────────────────────────────────────────
            ProviderClass = ProviderRegistry.get(channel.platform.value)

            cred = channel.credential
            if not cred:
                raise ProviderAuthError("Canal sin credenciales OAuth")

            access_token = decrypt_token(cred.access_token_enc)
            refresh_token = decrypt_token(cred.refresh_token_enc) if cred.refresh_token_enc else None

            provider = ProviderClass(access_token=access_token, refresh_token=refresh_token)

            # Caption específico para esta plataforma (o el genérico)
            platform_key = channel.platform.value
            caption = publication.captions.get(platform_key) or publication.captions.get("default", "")
            title = publication.platform_settings.get(platform_key, {}).get("title")

            job_data = {
                "idempotency_key": job.job_idempotency_key,
                "storage_url": publication.media_asset.public_url,
                "storage_key": publication.media_asset.storage_key,
                "caption": caption,
                "title": title,
                "platform_settings": publication.platform_settings.get(platform_key, {}),
                "media_type": publication.media_asset.media_type.value,
            }

            # ── Publicar ──────────────────────────────────────────────────────
            if publication.scheduled_at and publication.scheduled_at > datetime.now(timezone.utc):
                result = await provider.schedule_publication(
                    job_data, publication.scheduled_at.isoformat()
                )
            else:
                result = await provider.publish(job_data)

            # ── Procesar resultado ────────────────────────────────────────────
            if result.success:
                job.status = PublicationStatus.published
                job.remote_publication_id = result.remote_id
                job.remote_url = result.remote_url
                job.published_at = datetime.now(timezone.utc)
                logger.info(f"Job {job_id} publicado exitosamente — remote_id={result.remote_id}")
            else:
                _handle_failure(job, result.error_message or "Error desconocido", result.error_type)

        except ProviderAuthError as exc:
            job.status = PublicationStatus.needs_reconnect
            job.last_error = str(exc)
            job.error_type = JobErrorType.auth
            job.failed_at = datetime.now(timezone.utc)
            logger.warning(f"Job {job_id} — auth error: {exc}")

        except ProviderRateLimitError as exc:
            job.status = PublicationStatus.retrying
            job.last_error = str(exc)
            job.error_type = JobErrorType.rate_limit
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after)
            await db.commit()
            raise task.retry(exc=exc, countdown=exc.retry_after)

        except ProviderContentError as exc:
            job.status = PublicationStatus.failed
            job.last_error = str(exc)
            job.error_type = JobErrorType.invalid_content
            job.failed_at = datetime.now(timezone.utc)
            logger.error(f"Job {job_id} — contenido inválido: {exc}")

        except ProviderTemporaryError as exc:
            delay = _exponential_backoff(job.attempt_count)
            job.status = PublicationStatus.retrying
            job.last_error = str(exc)
            job.error_type = JobErrorType.temporary
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            await db.commit()
            raise task.retry(exc=exc, countdown=delay)

        except Exception as exc:
            delay = _exponential_backoff(job.attempt_count)
            job.status = PublicationStatus.retrying
            job.last_error = str(exc)
            job.error_type = JobErrorType.unknown
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            logger.exception(f"Job {job_id} — error inesperado: {exc}")
            await db.commit()
            raise task.retry(exc=exc, countdown=delay)

        await db.commit()

        # Actualizar contadores en Publication
        await _update_publication_counters(db, job.publication_id)


def _handle_failure(job: PublicationJob, error: str, error_type: str | None):
    job.status = PublicationStatus.failed
    job.last_error = error
    job.failed_at = datetime.now(timezone.utc)
    if error_type:
        try:
            job.error_type = JobErrorType(error_type)
        except ValueError:
            job.error_type = JobErrorType.unknown


def _exponential_backoff(attempt: int, base: int = 60, max_delay: int = 3600) -> int:
    """Backoff exponencial: 60, 120, 240, 480, 960... segundos."""
    return min(base * (2 ** (attempt - 1)), max_delay)


async def _update_publication_counters(db, publication_id: int):
    """Actualiza los contadores desnormalizados de Publication."""
    from sqlalchemy import func
    from app.models.publication import Publication
    result = await db.execute(
        select(
            func.count(PublicationJob.id).label("total"),
            func.count(PublicationJob.id).filter(
                PublicationJob.status == PublicationStatus.published
            ).label("published"),
            func.count(PublicationJob.id).filter(
                PublicationJob.status == PublicationStatus.failed
            ).label("failed"),
            func.count(PublicationJob.id).filter(
                PublicationJob.status.in_([PublicationStatus.queued, PublicationStatus.retrying, PublicationStatus.processing])
            ).label("pending"),
        ).where(PublicationJob.publication_id == publication_id)
    )
    row = result.one()
    await db.execute(
        Publication.__table__.update()
        .where(Publication.id == publication_id)
        .values(total_jobs=row.total, jobs_published=row.published, jobs_failed=row.failed, jobs_pending=row.pending)
    )
    await db.commit()


@celery_app.task(name="app.workers.publish_task.retry_failed_jobs")
def retry_failed_jobs():
    """
    Tarea periódica: toma jobs en estado retrying con next_retry_at <= ahora
    y los reencola al worker correspondiente.
    """
    import asyncio
    asyncio.run(_retry_failed_jobs_async())


async def _retry_failed_jobs_async():
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(PublicationJob)
            .where(
                PublicationJob.status == PublicationStatus.retrying,
                PublicationJob.next_retry_at <= now,
                PublicationJob.attempt_count < PublicationJob.max_attempts,
            )
            .options(selectinload(PublicationJob.channel))
            .limit(100)
        )
        jobs = result.scalars().all()
        for job in jobs:
            queue = job.channel.platform.value
            publish_job.apply_async(args=[job.id], queue=queue)
            logger.info(f"Reencolar job {job.id} en queue {queue}")
