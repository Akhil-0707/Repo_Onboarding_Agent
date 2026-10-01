from __future__ import annotations

from django.db import models

from apps.repos.models import Repository


class AnalysisStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    WAITING_FOR_MODEL = "waiting_for_model", "Waiting for model"
    DONE = "done", "Done"
    PARTIAL = "partial", "Partially done"
    FAILED = "failed", "Failed"


class Analysis(models.Model):
    """AI-generated onboarding content for one repository snapshot.

    ``sections`` maps a section key to ``{status, data, error, references, updated_at}``.
    ``checkpoint`` holds the in-progress section's conversation so a run interrupted by the
    model server disappearing resumes exactly where it stopped.
    """

    repository = models.OneToOneField(Repository, on_delete=models.CASCADE, related_name="analysis")
    status = models.CharField(
        max_length=32, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING
    )
    model = models.CharField(max_length=200, blank=True, default="")
    sections = models.JSONField(default=dict, blank=True)
    checkpoint = models.JSONField(null=True, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    est_cost = models.FloatField(default=0.0)
    error = models.TextField(blank=True, default="")
    waiting_since = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analyses"
        indexes = [models.Index(fields=["status"], name="analysis_status_idx")]

    def __str__(self) -> str:
        return f"Analysis of {self.repository}"

    def section_status(self, key: str) -> str:
        return (self.sections.get(key) or {}).get("status", "pending")
