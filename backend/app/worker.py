"""Celery app: the background worker that runs slow jobs (PDF ingestion now, research runs later).

The API only enqueues a small JSON message in Redis; a worker process picks it up.
Start a worker with: celery -A app.worker worker
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "researchpilot",
    broker=settings.redis_url,
    include=["app.sources.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    # Job status lives in our own database tables, so Celery doesn't need to store results.
    task_ignore_result=True,
    # Acknowledge a message only after the task finishes. If a worker dies mid-task,
    # Redis hands the message to another worker instead of losing it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Ingestion jobs are long; take one message at a time so work spreads across workers.
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
