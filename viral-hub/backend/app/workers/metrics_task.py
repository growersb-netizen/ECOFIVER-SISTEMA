"""
metrics_task — recolección periódica de métricas.

Corre cada hora via Celery Beat.
Solo procesa publicaciones con Capability.analytics activo.
"""

import logging
from datetime import datetime, timezone, timedelta
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_token
from app.models.publication import PublicationJob, PublicationStatus, AnalyticsSnapshot
from app.models.channel import SocialChannel
from app.providers import ProviderRegistry
from app.providers.base import Capability

logger = get_task_logger(__name__)


@celery_app.task(name="app.workers.metrics_task.collect_metrics")
def collect_metrics():
    import asyncio
    asyncio.run(_collect_metrics_async())


async def _collect_metrics_async():
    """
    Recorre jobs publicados en las últimas 72h y captura métricas.
    El intervalo puede ajustarse según el plan del workspace.
    """
    async with AsyncSessionLocal() as db:
        since = datetime.now(timezone.utc) - timedelta(hours=72)
        result = await db.execute(
            select(PublicationJob)
            .where(
                PublicationJob.status == PublicationStatus.published,
                PublicationJob.published_at >= since,
                PublicationJob.remote_publication_id.is_not(None),
            )
            .options(selectinload(PublicationJob.channel).selectinload(SocialChannel.credential))
            .limit(500)
        )
        jobs = result.scalars().all()

        for job in jobs:
            try:
                channel = job.channel
                ProviderClass = ProviderRegistry.get(channel.platform.value)
                capabilities = ProviderClass(access_token="").get_capabilities()

                if not capabilities.supports(Capability.analytics):
                    continue

                cred = channel.credential
                if not cred:
                    continue

                access_token = decrypt_token(cred.access_token_enc)
                provider = ProviderClass(access_token=access_token)
                metrics = await provider.get_metrics(job.remote_publication_id)

                snapshot = AnalyticsSnapshot(
                    job_id=job.id,
                    views=metrics.views,
                    likes=metrics.likes,
                    comments=metrics.comments,
                    shares=metrics.shares,
                    followers_gained=metrics.followers_gained,
                    reach=metrics.reach,
                    raw_data=metrics.raw_data,
                )
                db.add(snapshot)

            except NotImplementedError:
                pass  # provider no implementado aún
            except Exception as exc:
                logger.warning(f"Métricas job {job.id}: {exc}")

        await db.commit()
        logger.info(f"collect_metrics: procesados {len(jobs)} jobs")
