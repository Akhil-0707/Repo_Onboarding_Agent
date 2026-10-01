from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.analysis.models import Analysis, AnalysisStatus
from apps.analysis.runner import AnalysisRunner, model_available
from apps.common.logging import get_logger
from apps.ingestion.progress import JobReporter
from apps.repos.models import IngestionJob, JobStatus

logger = get_logger(__name__)


@shared_task(acks_late=True)
def analyze_repository(job_id: str) -> str:
    return AnalysisRunner(job_id).run()


@shared_task(ignore_result=True)
def resume_waiting_analyses() -> int:
    """Celery beat: restart analyses paused while the model server was offline."""
    waiting = list(IngestionJob.objects.filter(status=JobStatus.WAITING_FOR_MODEL))
    if not waiting:
        return 0

    cutoff = timezone.now() - timedelta(hours=settings.ANALYSIS_MAX_WAIT_HOURS)
    for job in waiting:
        analysis = Analysis.objects.filter(repository_id=job.repository_id).first()
        if analysis and analysis.waiting_since and analysis.waiting_since < cutoff:
            message = (
                f"The model server was offline for more than {settings.ANALYSIS_MAX_WAIT_HOURS} "
                "hours. Re-run the analysis when it is back."
            )
            Analysis.objects.filter(pk=analysis.pk).update(
                status=AnalysisStatus.FAILED, error=message
            )
            reporter = JobReporter(str(job.pk))
            reporter.log("analyze", message, level="error")
            reporter.finish(JobStatus.DONE)

    if not model_available():
        return 0
    resumed = 0
    for job in IngestionJob.objects.filter(status=JobStatus.WAITING_FOR_MODEL):
        # Atomic claim: only one beat tick / worker can move a job out of "waiting".
        claimed = IngestionJob.objects.filter(pk=job.pk, status=JobStatus.WAITING_FOR_MODEL).update(
            status=JobStatus.RUNNING
        )
        if claimed:
            analyze_repository.delay(str(job.pk))
            resumed += 1
    if resumed:
        logger.info("analyses_resumed", count=resumed)
    return resumed
