"""Sandboxed, shallow, single-commit fetch of a repository.

Safety properties:
- only the exact resolved commit is fetched (``--depth 1``), no tags, no submodules, no LFS;
- hooks are disabled and symlinks are checked out as plain files, so nothing in the repo can
  execute or escape the sandbox directory;
- the access token travels in an ``http.extraHeader`` passed through ``GIT_CONFIG_*``
  environment variables, so it never appears in the URL, in ``.git/config`` or in logs;
- the working tree size is checked against the limit after checkout.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

from apps.common.logging import get_logger, scrub
from apps.ingestion.errors import CloneError, LimitExceededError

logger = get_logger(__name__)


def _git_env(token: str | None, allow_local: bool) -> dict[str, str]:
    config = {
        "core.hooksPath": os.devnull,
        "core.symlinks": "false",
        "core.fsmonitor": "false",
        "core.longpaths": "true",
        "submodule.recurse": "false",
        "protocol.ext.allow": "never",
        "protocol.file.allow": "always" if allow_local else "never",
        "advice.detachedHead": "false",
        "init.defaultBranch": "main",
    }
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        config["http.https://github.com/.extraheader"] = f"AUTHORIZATION: basic {basic}"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", os.environ.get("USERPROFILE", "")),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": str(len(config)),
    }
    for system_key in ("SYSTEMROOT", "TEMP", "TMP"):  # needed by git on Windows
        if system_key in os.environ:
            env[system_key] = os.environ[system_key]
    for index, (key, value) in enumerate(config.items()):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _run(args: list[str], cwd: Path, env: dict[str, str], timeout: int) -> None:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed git argv, no shell
            ["git", *args],  # noqa: S607
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CloneError("Cloning took too long and was stopped.") from exc
    if completed.returncode != 0:
        detail = scrub(
            completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else ""
        )
        logger.warning("git_failed", args=args[:2], detail=detail)
        if "not our ref" in completed.stderr or "couldn't find remote ref" in completed.stderr:
            raise CloneError("That commit is no longer available on GitHub. Try again.")
        if (
            "Authentication failed" in completed.stderr
            or "could not read Username" in completed.stderr
        ):
            raise CloneError("GitHub refused access to this repository.")
        raise CloneError("Could not clone the repository from GitHub.")


def working_tree_bytes(root: Path) -> int:
    total = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            try:
                total += (Path(current) / filename).lstat().st_size
            except OSError:
                continue
    return total


def clone_repository(
    url: str,
    commit_sha: str,
    destination: Path,
    *,
    token: str | None = None,
    timeout: int = 300,
    max_bytes: int = 200 * 1024 * 1024,
    allow_local: bool = False,
) -> Path:
    """Fetch exactly ``commit_sha`` of ``url`` into ``destination`` (created if missing)."""
    destination.mkdir(parents=True, exist_ok=True)
    env = _git_env(token, allow_local)
    _run(["init", "-q"], destination, env, timeout)
    _run(["remote", "add", "origin", url], destination, env, timeout)
    _run(
        [
            "fetch",
            "--depth",
            "1",
            "--no-tags",
            "--no-recurse-submodules",
            "-q",
            "origin",
            commit_sha,
        ],
        destination,
        env,
        timeout,
    )
    _run(["checkout", "-q", "FETCH_HEAD"], destination, env, timeout)

    size = working_tree_bytes(destination)
    if size > max_bytes:
        raise LimitExceededError(
            f"The repository is {size / 1_048_576:.0f} MB, above RepoGuide's "
            f"{max_bytes / 1_048_576:.0f} MB limit."
        )
    return destination
