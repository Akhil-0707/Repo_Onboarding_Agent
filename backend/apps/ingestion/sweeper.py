"""Fail jobs whose worker died without saying so (SIGKILL, OOM, a lost container).

A running job writes ``heartbeat_at`` on every progress update; one that has been silent for
``INGEST_STALE_MINUTES`` is stopped. Queued jobs get a longer grace period
(``INGEST_QUEUED_TIMEOUT_MINUTES``) because they may wait behind long analyses.
Jobs waiting for the model server are handled by ``resume_waiting_analyses`` instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.analysis.models import Analysis, AnalysisStatus
from apps.analysis.sections import SECTIONS
from apps.common.logging import get_logger
from apps.ingestion.pipeline import fail_job
from apps.ingestion.progress import JobReporter, iso_now
from apps.repos.models import IngestionJob, JobStatus, RepoStatus

logger = get_logger(__name__)


def abandon_analysis(job: IngestionJob, message: str) -> None:
    """The code index is fine (the repo stays browsable); only the AI analysis stopped."""
    analysis = Analysis.objects.filter(repository_id=job.repository_id).first()
    if analysis is not None:
        sections = dict(analysis.sections or {})
        for spec in SECTIONS:
            state = sections.get(spec.key) or {}
            if state.get("status") != "done":
                sections[spec.key] = {**state, "status": "failed", "error": message}
        done = sum(1 for spec in SECTIONS if sections[spec.key].get("status") == "done")
        analysis.sections = sections
        analysis.status = AnalysisStatus.PARTIAL if done else AnalysisStatus.FAILED
        analysis.error = message
        analysis.finished_at = timezone.now()
        analysis.save()  # the checkpoint is kept: re-analysing resumes from it
    reporter = JobReporter(str(job.pk))
    reporter._set_step(
        "analyze", {"status": "failed", "message": message, "finished_at": iso_now()}
    )
    reporter.log("analyze", message, level="error")
    reporter.finish(JobStatus.DONE)


def sweep_stale_jobs(now: datetime | None = None) -> int:
    now = now or timezone.now()
    limits = {
        JobStatus.RUNNING: now - timedelta(minutes=settings.INGEST_STALE_MINUTES),
        JobStatus.QUEUED: now - timedelta(minutes=settings.INGEST_QUEUED_TIMEOUT_MINUTES),
    }
    swept = 0
    for job in IngestionJob.objects.select_related("repository").filter(status__in=list(limits)):
        last_sign_of_life = job.heartbeat_at or job.started_at or job.created_at
        if last_sign_of_life >= limits[JobStatus(job.status)]:
            continue
        # Claim it atomically so two beat ticks never handle the same job.
        if not IngestionJob.objects.filter(pk=job.pk, status=job.status).update(
            status=JobStatus.FAILED if job.repository.status != RepoStatus.READY else job.status,
            heartbeat_at=now,
        ):
            continue
        minutes = int((now - last_sign_of_life).total_seconds() // 60)
        message = (
            f"The job stopped responding (no progress for {minutes} minutes) and was stopped. "
            "Start it again to retry."
        )
        logger.warning("stale_job_swept", job=str(job.pk), status=job.status, minutes=minutes)
        if job.repository.status == RepoStatus.READY:
            abandon_analysis(job, message)
        else:
            fail_job(str(job.pk), message)
        swept += 1
    return swept
