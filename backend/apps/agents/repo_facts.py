"""Deterministic facts about a repository (no LLM): structure, entry points, central files."""

from __future__ import annotations

import posixpath
import re
from collections import Counter
from collections.abc import Iterable

ENTRY_PATTERNS = [
    re.compile(p)
    for p in (
        r"(^|/)manage\.py$",
        r"(^|/)(main|app|server|wsgi|asgi|__main__|cli|run)\.py$",
        r"(^|/)(index|main|server|app|cli)\.(ts|tsx|js|mjs|cjs)$",
        r"(^|/)cmd/[^/]+/main\.go$",
        r"(^|/)main\.go$",
        r"(^|/)[A-Za-z]*Application\.java$",
        r"(^|/)Main\.java$",
        r"(^|/)bin/[^/]+$",
        r"(^|/)Dockerfile$",
    )
]


def top_level_structure(paths: Iterable[str], limit: int = 25) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for path in paths:
        head = path.split("/", 1)[0]
        counts[f"{head}/" if "/" in path else head] += 1
    return sorted(counts.items(), key=lambda kv: (not kv[0].endswith("/"), -kv[1], kv[0]))[:limit]


def entry_point_candidates(paths: Iterable[str], limit: int = 12) -> list[str]:
    found = [p for p in paths if any(pattern.search(p) for pattern in ENTRY_PATTERNS)]
    # Shallow files first: `main.py` beats `examples/demo/main.py`.
    found.sort(key=lambda p: (p.count("/"), "test" in p.lower() or "example" in p.lower(), p))
    return found[:limit]


def directory_of(path: str) -> str:
    return posixpath.dirname(path) or "."
