from __future__ import annotations

from django.conf import settings
from django.db import models


class RepoStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    INGESTING = "ingesting", "Ingesting"
    WAITING_FOR_MODEL = "waiting_for_model", "Waiting for model"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_MODEL = "waiting_for_model", "Waiting for model"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.DONE, JobStatus.FAILED})


class Repository(models.Model):
    """One analysed snapshot of a GitHub repository: results are cached per commit SHA."""

    url = models.URLField(max_length=300)
    url_key = models.CharField(max_length=300)
    """Lower-cased ``github.com/owner/name``; together with ``commit_sha`` the cache key."""
    owner = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    default_branch = models.CharField(max_length=255)
    commit_sha = models.CharField(max_length=40)
    private = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=RepoStatus.choices, default=RepoStatus.QUEUED)
    error = models.TextField(blank=True, default="")
    stats = models.JSONField(default=dict, blank=True)
    languages = models.JSONField(default=dict, blank=True)
    frameworks = models.JSONField(default=list, blank=True)
    detection = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ingested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "repositories"
        constraints = [
            models.UniqueConstraint(fields=["url_key", "commit_sha"], name="uniq_repo_commit"),
        ]
        indexes = [models.Index(fields=["status"], name="repo_status_idx")]

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}@{self.commit_sha[:7]}"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class UserRepository(models.Model):
    """Links a user to the repositories on their dashboard (many users can share one)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    access_checked_at = models.DateTimeField(null=True, blank=True)
    """When GitHub last confirmed this user can read the (private) repository."""

    class Meta:
        db_table = "user_repos"
        constraints = [
            models.UniqueConstraint(fields=["user", "repository"], name="uniq_user_repo"),
        ]
        indexes = [models.Index(fields=["user", "-created_at"], name="user_repo_recent_idx")]


class IngestionJob(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="jobs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=JobStatus.choices, default=JobStatus.QUEUED)
    steps = models.JSONField(default=list, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    """Last progress write; the stale-job sweeper fails running jobs that stop updating."""

    class Meta:
        db_table = "ingestion_jobs"
        indexes = [
            models.Index(fields=["repository", "-created_at"], name="job_repo_recent_idx"),
            models.Index(fields=["status"], name="job_status_idx"),
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES
