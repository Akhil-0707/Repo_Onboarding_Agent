from __future__ import annotations

from celery import shared_task

from apps.common.logging import get_logger
from apps.ingestion.errors import IngestionError
from apps.ingestion.pipeline import run_ingestion

logger = get_logger(__name__)


@shared_task(acks_late=True, ignore_result=False)
def ingest_repository(job_id: str) -> str | None:
    """Clone + index a repository. Failures are recorded on the job, not re-raised, so a
    user-facing error (e.g. limits exceeded) never shows up as a crashed task."""
    try:
        return run_ingestion(job_id)
    except IngestionError as exc:
        logger.info("ingestion_failed", job_id=job_id, reason=str(exc))
        return None
