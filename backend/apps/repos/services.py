"""Starting analyses: resolve the repo on GitHub, reuse cached results, enqueue ingestion."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError

from apps.accounts.crypto import TokenDecryptionError
from apps.accounts.models import User
from apps.accounts.services import get_github_token
from apps.common.errors import ApiError, NotFoundError
from apps.common.logging import get_logger
from apps.ingestion.errors import IngestionError, RepositoryNotFoundError
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
    except RepositoryNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except IngestionError as exc:
        raise GitHubUnavailable(str(exc)) from exc


def latest_job(repository: Repository) -> IngestionJob | None:
    return repository.jobs.order_by("-created_at").first()


def _link(user: User, repository: Repository) -> None:
    UserRepository.objects.get_or_create(user=user, repository=repository)


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


def start_analysis(user: User, url: str) -> AnalysisStart:
    info = resolve_repo(user, url)
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
            return AnalysisStart(existing, _enqueue(existing, user), created=True, cached=False)
        logger.info("analysis_cache_hit", repo=existing.full_name, sha=info.head_sha[:7])
        return AnalysisStart(
            existing,
            latest_job(existing),
            created=False,
            cached=existing.status == RepoStatus.READY,
        )

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
    return link.repository
