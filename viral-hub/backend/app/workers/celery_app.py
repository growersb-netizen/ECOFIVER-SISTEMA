"""
Configuración de Celery.

Cada plataforma tiene su propia queue para poder escalar workers independientemente.
El beat_schedule corre la tarea de chequeo de métricas cada hora.
"""

from celery import Celery
from celery.utils.log import get_task_logger
from kombu import Queue

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "viralhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.publish_task",
        "app.workers.metrics_task",
    ],
)

# ─── Queues por plataforma ────────────────────────────────────────────────────
# El docker-compose levanta un worker por cada queue.
# En prod se pueden escalar de forma independiente según carga.
QUEUES = ("instagram", "tiktok", "youtube", "facebook", "metrics", "default")

celery_app.conf.task_queues = [Queue(q) for q in QUEUES]
celery_app.conf.task_default_queue = "default"

# ─── Comportamiento ───────────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialización
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Tiempo
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    # Reintentos
    task_acks_late=True,                    # confirmar solo cuando termina (no cuando toma el mensaje)
    task_reject_on_worker_lost=True,        # reintentar si el worker muere
    task_track_started=True,
    # Resultados
    result_expires=86400,                   # 24h
    # Rate limits globales (cada task puede sobreescribir por plataforma)
    task_default_rate_limit="100/m",
    # Dead letter (si el job agota reintentos, va acá para inspección)
    task_annotations={
        "app.workers.publish_task.publish_job": {
            "max_retries": 5,
            "default_retry_delay": 60,
        }
    },
)

# ─── Beat schedule (tareas periódicas) ───────────────────────────────────────
celery_app.conf.beat_schedule = {
    "collect-metrics-hourly": {
        "task": "app.workers.metrics_task.collect_metrics",
        "schedule": 3600,  # cada hora
        "options": {"queue": "metrics"},
    },
    "retry-failed-jobs": {
        "task": "app.workers.publish_task.retry_failed_jobs",
        "schedule": 300,   # cada 5 min
        "options": {"queue": "default"},
    },
}
