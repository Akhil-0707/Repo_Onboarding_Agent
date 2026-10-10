"""Starting analyses: resolve the repo on GitHub, reuse cached results, enqueue ingestion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status

from apps.accounts.crypto import TokenDecryptionError
from apps.accounts.models import User
from apps.accounts.services import get_github_token
from apps.common.errors import ApiError, NotFoundError
from apps.common.logging import get_logger
from apps.ingestion.errors import (
    GitHubTokenRejectedError,
    IngestionError,
    RepositoryNotFoundError,
)
from apps.ingestion.github import RepoInfo, get_code_host, parse_repo_url
from apps.ingestion.progress import initial_steps
from apps.repos.models import IngestionJob, JobStatus, Repository, RepoStatus, UserRepository

logger = get_logger(__name__)


class InvalidRepoUrl(ApiError):
    default_code = "invalid_url"
    default_detail = "Enter a GitHub repository URL like https://github.com/owner/repo."


class RepoTooLarge(ApiError):
    default_code = "limit_exceeded"


class GitHubUnavailable(ApiError):
    status_code = 502
    default_code = "github_error"


class GitHubReauthRequired(ApiError):
    status_code = 403  # not 401: that would make the web client refresh its own session instead
    default_code = "github_reauth_required"


class AnalysisInProgress(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "analysis_in_progress"
    default_detail = "This repository is already being analysed."


OnNewWork = Callable[[], None]
"""Called right before work is enqueued (consumes the user's rate limit); may raise."""
ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.WAITING_FOR_MODEL)


def _no_limit() -> None:
    return None


@dataclass(frozen=True)
class AnalysisStart:
    repository: Repository
    job: IngestionJob | None
    created: bool
    """A new ingestion was enqueued (counts against the rate limit)."""
    cached: bool
    """Results for this exact commit already exist and are ready."""


def _user_token(user: User) -> str | None:
    try:
        return get_github_token(user) or None
    except TokenDecryptionError:
        return None


def resolve_repo(user: User, url: str) -> RepoInfo:
    ref = parse_repo_url(url)
    if ref is None:
        raise InvalidRepoUrl()
    try:
        return get_code_host().resolve(ref, _user_token(user))
    except GitHubTokenRejectedError as exc:
        raise GitHubReauthRequired(str(exc)) from exc
    except RepositoryNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except IngestionError as exc:
        raise GitHubUnavailable(str(exc)) from exc


def latest_job(repository: Repository) -> IngestionJob | None:
    return repository.jobs.order_by("-created_at").first()


def _link(user: User, repository: Repository) -> None:
    """Called after the user's own token resolved the repo, i.e. access was just verified."""
    link, _ = UserRepository.objects.get_or_create(user=user, repository=repository)
    if repository.private:
        UserRepository.objects.filter(pk=link.pk).update(access_checked_at=timezone.now())


def _enqueue(repository: Repository, user: User) -> IngestionJob:
    from apps.ingestion.tasks import start_pipeline

    Repository.objects.filter(pk=repository.pk).update(status=RepoStatus.QUEUED, error="")
    repository.refresh_from_db()
    job = IngestionJob.objects.create(
        repository=repository, user=user, status=JobStatus.QUEUED, steps=initial_steps()
    )
    result = start_pipeline(str(job.pk))
    IngestionJob.objects.filter(pk=job.pk).update(celery_task_id=result.id or "")
    return job


def _enqueue_analysis_only(repository: Repository, user: User) -> IngestionJob:
    """Same commit, code index intact: re-run only the AI sections that are not done."""
    from apps.analysis.models import Analysis, AnalysisStatus
    from apps.analysis.tasks import analyze_repository

    analysis = Analysis.objects.filter(repository=repository).first()
    if analysis is not None:
        sections = {
            key: state if state.get("status") == "done" else {**state, "status": "pending"}
            for key, state in (analysis.sections or {}).items()
        }
        Analysis.objects.filter(pk=analysis.pk).update(
            status=AnalysisStatus.PENDING, error="", sections=sections, finished_at=None
        )
    steps = initial_steps()
    for step in steps:
        if step["key"] != "analyze":
            step.update(status="done", progress=100)
    job = IngestionJob.objects.create(
        repository=repository,
        user=user,
        status=JobStatus.RUNNING,
        steps=steps,
        started_at=timezone.now(),
    )
    result = analyze_repository.delay(str(job.pk))
    IngestionJob.objects.filter(pk=job.pk).update(celery_task_id=result.id or "")
    return job


def start_analysis(user: User, url: str, on_new_work: OnNewWork = _no_limit) -> AnalysisStart:
    return _start_from_info(user, resolve_repo(user, url), on_new_work)


def _start_from_info(user: User, info: RepoInfo, on_new_work: OnNewWork) -> AnalysisStart:
    max_kb = settings.INGEST_MAX_REPO_MB * 1024
    if info.size_kb > max_kb:
        raise RepoTooLarge(
            f"{info.owner}/{info.name} is about {info.size_kb // 1024} MB on GitHub, above the "
            f"{settings.INGEST_MAX_REPO_MB} MB limit."
        )

    existing = Repository.objects.filter(url_key=info.url_key, commit_sha=info.head_sha).first()
    if existing is not None:
        # The user's token just resolved this repo, so access to private repos is verified.
        _link(user, existing)
        if existing.status == RepoStatus.FAILED:
            on_new_work()
            return AnalysisStart(existing, _enqueue(existing, user), created=True, cached=False)
        logger.info("analysis_cache_hit", repo=existing.full_name, sha=info.head_sha[:7])
        return AnalysisStart(
            existing,
            latest_job(existing),
            created=False,
            cached=existing.status == RepoStatus.READY,
        )

    on_new_work()
    try:
        repository = Repository.objects.create(
            url=f"https://github.com/{info.owner}/{info.name}",
            url_key=info.url_key,
            owner=info.owner,
            name=info.name,
            description=info.description[:2000],
            default_branch=info.default_branch,
            commit_sha=info.head_sha,
            private=info.private,
        )
    except IntegrityError:  # another request created it a moment ago
        repository = Repository.objects.get(url_key=info.url_key, commit_sha=info.head_sha)
        _link(user, repository)
        return AnalysisStart(repository, latest_job(repository), created=False, cached=False)

    _link(user, repository)
    return AnalysisStart(repository, _enqueue(repository, user), created=True, cached=False)


def get_user_repository(user: User, repo_id: str) -> Repository:
    """The repository if ``user`` has it on their dashboard; 404 otherwise."""
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(repo_id)
    except (InvalidId, TypeError) as exc:
        raise NotFoundError("Repository not found.") from exc
    link = (
        UserRepository.objects.select_related("repository")
        .filter(user=user, repository_id=oid)
        .first()
    )
    if link is None:
        raise NotFoundError("Repository not found.")
    if link.repository.private:
        _ensure_private_access(user, link)
    return link.repository


def _ensure_private_access(user: User, link: UserRepository) -> None:
    """Cached private analyses are only served while GitHub confirms the user can read the
    repository (re-checked every ``PRIVATE_ACCESS_RECHECK_HOURS``)."""
    now = timezone.now()
    checked = link.access_checked_at
    if checked and now - checked < timedelta(hours=settings.PRIVATE_ACCESS_RECHECK_HOURS):
        return
    repository = link.repository
    ref = parse_repo_url(repository.url)
    try:
        if ref is None:
            raise RepositoryNotFoundError("Unrecognised repository URL.")
        get_code_host().resolve(ref, _user_token(user))
    except GitHubTokenRejectedError as exc:
        # A dead token says nothing about access: keep the link, ask for a new sign-in.
        raise GitHubReauthRequired(str(exc)) from exc
    except RepositoryNotFoundError as exc:
        link.delete()  # access revoked: the cached analysis is no longer visible to this user
        logger.info("private_access_revoked", repo=repository.full_name)
        raise NotFoundError("Repository not found.") from exc
    except IngestionError as exc:
        grace = timedelta(hours=settings.PRIVATE_ACCESS_GRACE_HOURS)
        if checked and now - checked < grace:
            return  # GitHub is down; a recent confirmation is good enough for now
        raise GitHubUnavailable(
            "Could not confirm your access to this private repository with GitHub. "
            "Try again in a moment."
        ) from exc
    UserRepository.objects.filter(pk=link.pk).update(access_checked_at=now)


def reanalyze(
    user: User, repository: Repository, on_new_work: OnNewWork = _no_limit
) -> AnalysisStart:
    """Analyse the latest commit, or retry unfinished AI sections when nothing changed.

    Snapshots are a shared cache, so a finished analysis of the same commit is never redone."""
    from apps.analysis.models import Analysis
    from apps.analysis.sections import SECTION_KEYS

    job = latest_job(repository)
    if job is not None and job.status in ACTIVE_JOB_STATUSES:
        raise AnalysisInProgress()
    info = resolve_repo(user, repository.url)
    if info.head_sha != repository.commit_sha:
        result = _start_from_info(user, info, on_new_work)
        if result.repository.pk != repository.pk:
            # The new snapshot replaces the old one on this user's dashboard.
            UserRepository.objects.filter(user=user, repository=repository).delete()
        return result
    if repository.status == RepoStatus.FAILED:
        on_new_work()
        return AnalysisStart(repository, _enqueue(repository, user), created=True, cached=False)
    if repository.status != RepoStatus.READY:
        raise AnalysisInProgress()
    analysis = Analysis.objects.filter(repository=repository).first()
    if analysis is not None and all(analysis.section_status(k) == "done" for k in SECTION_KEYS):
        return AnalysisStart(repository, job, created=False, cached=True)  # already up to date
    on_new_work()
    return AnalysisStart(
        repository, _enqueue_analysis_only(repository, user), created=True, cached=False
    )
