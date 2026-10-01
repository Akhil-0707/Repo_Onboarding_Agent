"""Celery tasks for the ingestion chain: ingest -> embed -> finalize.

Each stage records its own failure on the job; later stages check the job first and do
nothing if it already failed, so a chain never needs exceptions to stop.
"""

from __future__ import annotations

from celery import chain, shared_task
from celery.result import AsyncResult

from apps.common.logging import get_logger
from apps.ingestion.errors import IngestionError
from apps.ingestion.pipeline import fail_job, finalize, job_is_failed, run_ingestion
from apps.repos.models import IngestionJob

logger = get_logger(__name__)


@shared_task(acks_late=True)
def ingest_repository(job_id: str) -> str | None:
    """Clone + index a repository (user-facing failures are recorded on the job)."""
    try:
        return run_ingestion(job_id)
    except IngestionError as exc:
        logger.info("ingestion_failed", job_id=job_id, reason=str(exc))
        return None


@shared_task(acks_late=True)
def embed_repository(job_id: str) -> None:
    from apps.search.embedding_job import run_embedding_stage
    from apps.search.embeddings import EmbeddingError

    if job_is_failed(job_id):
        return
    repo_id = str(IngestionJob.objects.values_list("repository_id", flat=True).get(pk=job_id))
    try:
        run_embedding_stage(job_id, repo_id)
    except EmbeddingError as exc:
        fail_job(job_id, str(exc))


@shared_task(acks_late=True)
def finalize_ingestion(job_id: str) -> None:
    finalize(job_id)


def start_pipeline(job_id: str) -> AsyncResult:
    return chain(
        ingest_repository.si(job_id),
        embed_repository.si(job_id),
        finalize_ingestion.si(job_id),
    ).apply_async()
