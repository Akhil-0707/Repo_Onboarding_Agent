"""Celery tasks for the pipeline chain: ingest -> embed -> mark_indexed -> analyze.

Each stage records its own failure on the job; later stages check the job first and do
nothing if it already failed, so a chain never needs exceptions to stop.
"""

from __future__ import annotations

from celery import chain, shared_task
from celery.result import AsyncResult

from apps.common.logging import get_logger
from apps.ingestion.errors import IngestionError
from apps.ingestion.pipeline import fail_job, job_is_failed, mark_indexed, run_ingestion
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
def mark_repository_indexed(job_id: str) -> None:
    mark_indexed(job_id)


def start_pipeline(job_id: str) -> AsyncResult:
    from apps.analysis.tasks import analyze_repository

    return chain(
        ingest_repository.si(job_id),
        embed_repository.si(job_id),
        mark_repository_indexed.si(job_id),
        analyze_repository.si(job_id),
    ).apply_async()
