"""A scriptable stand-in for the GitHub API (``CodeHost``)."""

from __future__ import annotations

from apps.ingestion.errors import IngestionError, RepositoryNotFoundError
from apps.ingestion.github import CodeHost, RepoInfo, RepoRef


class FakeCodeHost(CodeHost):
    def __init__(self) -> None:
        self.sha = "a" * 40
        self.private = False
        self.denied: set[str | None] = set()  # tokens that may not see the repository
        self.down = False
        self.calls = 0
        self.tokens: list[str | None] = []

    def resolve(self, ref: RepoRef, token: str | None) -> RepoInfo:
        self.calls += 1
        self.tokens.append(token)
        if self.down:
            raise IngestionError("GitHub is unavailable.")
        if token in self.denied or ref.name == "missing":
            raise RepositoryNotFoundError("Repository not found.")
        return RepoInfo(
            owner="acme", name=ref.name, description="", default_branch="main",
            head_sha=self.sha, private=self.private, size_kb=50,
            html_url=f"https://github.com/acme/{ref.name}",
        )  # fmt: skip
