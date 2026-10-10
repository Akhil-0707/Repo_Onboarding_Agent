"""GitHub REST API access (behind the small ``CodeHost`` interface so tests can fake it)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from django.conf import settings

from apps.common.logging import get_logger
from apps.ingestion.errors import (
    GitHubTokenRejectedError,
    IngestionError,
    RepositoryNotFoundError,
)

logger = get_logger(__name__)

REAUTH_MESSAGE = (
    "GitHub no longer accepts your sign-in (it may have been revoked), so RepoGuide could only use "
    "GitHub's limited anonymous access, which failed. Sign out and sign in with GitHub again."
)

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    name: str
    description: str
    default_branch: str
    head_sha: str
    private: bool
    size_kb: int
    html_url: str

    @property
    def url_key(self) -> str:
        return f"github.com/{self.owner}/{self.name}".lower()


def parse_repo_url(value: str) -> RepoRef | None:
    """Accept ``https://github.com/o/r(.git)(/...)``, ``github.com/o/r`` or ``o/r``."""
    text = value.strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", text):
        text = f"github.com/{text}"
    text = re.sub(r"^(https?://)", "", text, flags=re.IGNORECASE)
    text = text.removeprefix("git@").replace(":", "/", 1) if text.startswith("git@") else text
    parts = [p for p in text.split("/") if p]
    if len(parts) < 3 or parts[0].lower() not in _HOSTS:
        return None
    owner, name = parts[1], parts[2].removesuffix(".git")
    if not _NAME.match(owner) or not _NAME.match(name) or name in {".", ".."}:
        return None
    return RepoRef(owner, name)


class CodeHost(ABC):
    @abstractmethod
    def resolve(self, ref: RepoRef, token: str | None) -> RepoInfo: ...


class GitHubCodeHost(CodeHost):
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def _get(self, path: str, token: str | None, accept: str) -> httpx.Response:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return httpx.get(
                f"{settings.GITHUB_API_URL}{path}", headers=headers, timeout=self.timeout
            )
        except httpx.HTTPError as exc:
            raise IngestionError("Could not reach GitHub. Please try again.") from exc

    def _request(self, path: str, token: str | None, accept: str) -> httpx.Response:
        response = self._get(path, token, accept)
        if response.status_code == 401 and token:
            # Revoked/expired user token: public repositories still work anonymously.
            logger.info("github_token_rejected_falling_back_to_anonymous")
            response = self._get(path, None, accept)
            if response.status_code >= 400:
                # The real problem is the dead token, not what the anonymous retry ran into
                # (GitHub's shared per-IP limit, or a private repository it cannot see).
                raise GitHubTokenRejectedError(REAUTH_MESSAGE)
        if response.status_code == 404:
            raise RepositoryNotFoundError(
                "Repository not found. Check the URL, or grant private repository access in "
                "Settings if it is private."
            )
        if (
            response.status_code in {403, 429}
            and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise IngestionError("GitHub API rate limit reached. Please try again later.")
        if response.status_code >= 400:
            raise IngestionError(f"GitHub returned an error ({response.status_code}).")
        return response

    def resolve(self, ref: RepoRef, token: str | None) -> RepoInfo:
        data = self._request(
            f"/repos/{ref.owner}/{ref.name}", token, "application/vnd.github+json"
        ).json()
        owner, name = data["full_name"].split("/", 1)
        branch = data["default_branch"]
        sha = self._request(
            f"/repos/{owner}/{name}/commits/{branch}", token, "application/vnd.github.sha"
        ).text.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise IngestionError("Could not resolve the latest commit of the default branch.")
        return RepoInfo(
            owner=owner,
            name=name,
            description=str(data.get("description") or ""),
            default_branch=branch,
            head_sha=sha,
            private=bool(data.get("private")),
            size_kb=int(data.get("size") or 0),
            html_url=str(data.get("html_url") or f"https://github.com/{owner}/{name}"),
        )


_code_host: CodeHost | None = None


def get_code_host() -> CodeHost:
    global _code_host
    if _code_host is None:
        _code_host = GitHubCodeHost()
    return _code_host


def set_code_host(host: CodeHost | None) -> None:
    global _code_host
    _code_host = host
