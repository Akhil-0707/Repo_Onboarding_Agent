"""Decide which files of a cloned repository are worth indexing.

Skips VCS/dependency/build directories, lockfiles, binaries, minified and generated files,
vendored code, symlinks (they could point outside the sandbox) and anything matched by the
repository's ``.gitignore`` files. Enforces the file-count limit.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pathspec

from apps.ingestion.errors import LimitExceededError
from apps.ingestion.languages import detect_language

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "bower_components",
        "jspm_packages",
        "venv",
        ".venv",
        "env",
        ".env",
        "virtualenv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "site-packages",
        "dist",
        "build",
        "out",
        "target",
        "obj",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".angular",
        ".turbo",
        ".parcel-cache",
        ".cache",
        "coverage",
        "htmlcov",
        ".nyc_output",
        ".gradle",
        ".idea",
        ".vscode",
        ".terraform",
        "Pods",
        "DerivedData",
        ".yarn",
        ".pnpm-store",
    }
)

VENDORED_DIRS = frozenset(
    {"vendor", "vendors", "vendored", "third_party", "thirdparty", "3rdparty"}
)

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "bun.lock",
        "poetry.lock",
        "pipfile.lock",
        "pdm.lock",
        "uv.lock",
        "cargo.lock",
        "composer.lock",
        "gemfile.lock",
        "go.sum",
        "packages.lock.json",
        "gradle.lockfile",
        "mix.lock",
        "flake.lock",
        "podfile.lock",
        "pubspec.lock",
    }
)

BINARY_EXTENSIONS = frozenset(
    {
        # images / media / fonts
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".avif", ".tif",
        ".tiff", ".psd", ".svg", ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".mov", ".avi",
        ".webm", ".mkv", ".ttf", ".otf", ".woff", ".woff2", ".eot",
        # archives / packages
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".ear",
        ".whl", ".egg", ".deb", ".rpm", ".dmg", ".iso", ".apk", ".aab", ".nupkg",
        # compiled / native
        ".pyc", ".pyo", ".pyd", ".class", ".o", ".a", ".so", ".dylib", ".dll", ".exe", ".lib",
        ".wasm", ".bin", ".dat", ".obj",
        # documents / data / models
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".sqlite", ".sqlite3",
        ".db", ".pkl", ".pickle", ".npy", ".npz", ".h5", ".pt", ".pth", ".onnx", ".safetensors",
        ".parquet", ".avro", ".map",
    }
)  # fmt: skip

GENERATED_SUFFIXES = (
    "_pb2.py",
    "_pb2_grpc.py",
    ".pb.go",
    ".pb.gw.go",
    ".g.dart",
    ".freezed.dart",
    ".designer.cs",
)

MINIFIED_CHECK_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".css"})
SNIFF_BYTES = 8192


@dataclass(frozen=True)
class FilterLimits:
    max_files: int = 5000
    max_file_bytes: int = 500 * 1024


@dataclass(frozen=True)
class SourceFile:
    path: str
    """Repo-relative POSIX path."""
    abs_path: Path
    size: int
    language: str


@dataclass
class FilterResult:
    files: list[SourceFile] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)
    too_large: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


class _GitIgnores:
    """All ``.gitignore`` files in the tree, each applied relative to its directory."""

    def __init__(self) -> None:
        self._specs: list[tuple[str, pathspec.GitIgnoreSpec]] = []

    def add(self, directory: str, gitignore: Path) -> None:
        try:
            lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        self._specs.append((directory, pathspec.GitIgnoreSpec.from_lines(lines)))

    def ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        for directory, spec in self._specs:
            if directory and not rel_path.startswith(f"{directory}/"):
                continue
            local = rel_path[len(directory) + 1 :] if directory else rel_path
            if spec.match_file(f"{local}/" if is_dir else local):
                return True
        return False


def _is_minified(path: Path, suffix: str, name: str) -> bool:
    if ".min." in name:
        return True
    if suffix not in MINIFIED_CHECK_EXTENSIONS:
        return False
    try:
        with path.open("rb") as handle:
            head = handle.read(SNIFF_BYTES * 4)
    except OSError:
        return False
    lines = head.splitlines() or [b""]
    longest = max(len(line) for line in lines)
    return longest > 1000 and len(head) / len(lines) > 300


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(SNIFF_BYTES)
    except OSError:
        return True


def classify(rel_path: str, abs_path: Path, size: int, limits: FilterLimits) -> str | None:
    """Return a skip reason, or ``None`` when the file should be indexed."""
    pure = PurePosixPath(rel_path)
    name = pure.name.lower()
    suffix = pure.suffix.lower()
    if name in LOCKFILES:
        return "lockfile"
    if suffix in BINARY_EXTENSIONS:
        return "binary"
    if name.endswith(GENERATED_SUFFIXES):
        return "generated"
    if size == 0:
        return "empty"
    if size > limits.max_file_bytes:
        return "too_large"
    if _is_minified(abs_path, suffix, name):
        return "minified"
    if _looks_binary(abs_path):
        return "binary"
    return None


def filter_repository(root: Path, limits: FilterLimits | None = None) -> FilterResult:
    limits = limits or FilterLimits()
    result = FilterResult()
    ignores = _GitIgnores()

    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        if ".gitignore" in filenames:
            ignores.add(rel_dir, current_path / ".gitignore")

        kept_dirs = []
        for dirname in sorted(dirnames):
            rel = f"{rel_dir}/{dirname}" if rel_dir else dirname
            lowered = dirname.lower()
            if (current_path / dirname).is_symlink():
                result.skipped["symlink"] += 1
            elif (
                dirname in IGNORED_DIRS or lowered in IGNORED_DIRS or dirname.endswith(".egg-info")
            ):
                result.skipped["ignored_dir"] += 1
            elif lowered in VENDORED_DIRS:
                result.skipped["vendored"] += 1
            elif ignores.ignored(rel, is_dir=True):
                result.skipped["gitignored"] += 1
            else:
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs  # prune the walk in place

        for filename in sorted(filenames):
            abs_path = current_path / filename
            rel = f"{rel_dir}/{filename}" if rel_dir else filename
            if abs_path.is_symlink():
                result.skipped["symlink"] += 1
                continue
            if ignores.ignored(rel):
                result.skipped["gitignored"] += 1
                continue
            try:
                size = abs_path.stat().st_size
            except OSError:
                result.skipped["unreadable"] += 1
                continue
            reason = classify(rel, abs_path, size, limits)
            if reason:
                result.skipped[reason] += 1
                if reason == "too_large":
                    result.too_large.append(rel)
                continue
            result.files.append(SourceFile(rel, abs_path, size, detect_language(rel)))
            if len(result.files) > limits.max_files:
                raise LimitExceededError(
                    f"The repository has more than {limits.max_files:,} source files after "
                    "filtering, which is above RepoGuide's limit."
                )
    return result


def read_text(file: SourceFile) -> str:
    """Decode a kept file as UTF-8, replacing undecodable bytes."""
    return file.abs_path.read_bytes().decode("utf-8", errors="replace")
