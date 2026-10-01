"""The sandboxed clone, exercised against a real local git repository."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from apps.ingestion.clone import clone_repository, working_tree_bytes
from apps.ingestion.errors import CloneError, LimitExceededError
from tests.conftest_fixtures import copy_fixture

TOKEN = "ghp_" + "t" * 36


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> tuple[str, str]:
    repo = copy_fixture("py_app", tmp_path / "src")
    hooks = repo / ".githooks"
    hooks.mkdir()
    (hooks / "post-checkout").write_text("#!/bin/sh\ntouch HOOK_RAN\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    sha = git(repo, "rev-parse", "HEAD")
    return repo.as_uri(), sha


def test_clones_exact_commit_shallowly(origin: tuple[str, str], tmp_path: Path) -> None:
    url, sha = origin
    dest = clone_repository(url, sha, tmp_path / "clone", allow_local=True)

    assert (dest / "app" / "main.py").is_file()
    assert git(dest, "rev-parse", "HEAD") == sha
    assert git(dest, "rev-list", "--count", "HEAD") == "1"
    assert not (dest / "HOOK_RAN").exists()


def test_token_never_written_to_disk(origin: tuple[str, str], tmp_path: Path) -> None:
    url, sha = origin
    dest = clone_repository(url, sha, tmp_path / "clone", token=TOKEN, allow_local=True)
    git_dir = dest / ".git"
    for path in git_dir.rglob("*"):
        if path.is_file() and path.stat().st_size < 1_000_000:
            assert TOKEN.encode() not in path.read_bytes(), path


def test_local_protocol_blocked_by_default(origin: tuple[str, str], tmp_path: Path) -> None:
    url, sha = origin
    with pytest.raises(CloneError):
        clone_repository(url, sha, tmp_path / "clone")


def test_unknown_commit_fails_cleanly(origin: tuple[str, str], tmp_path: Path) -> None:
    url, _ = origin
    with pytest.raises(CloneError):
        clone_repository(url, "0" * 40, tmp_path / "clone", allow_local=True)


def test_size_limit_enforced_after_checkout(origin: tuple[str, str], tmp_path: Path) -> None:
    url, sha = origin
    with pytest.raises(LimitExceededError, match="limit"):
        clone_repository(url, sha, tmp_path / "clone", allow_local=True, max_bytes=100)


def test_working_tree_bytes_excludes_git(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "big").write_bytes(b"x" * 1000)
    (tmp_path / "a.txt").write_bytes(b"x" * 10)
    assert working_tree_bytes(tmp_path) == 10
