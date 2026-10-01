"""Deterministic pre-analysis: a compact digest of facts the model would otherwise have to
discover through many tool calls (small models do much better when handed these up front)."""

from __future__ import annotations

import posixpath
from collections import Counter
from typing import Any

from bson import ObjectId

from apps.agents.repo_facts import entry_point_candidates, top_level_structure
from apps.agents.tools import ToolContext, wrap
from apps.ingestion.index_store import EDGES, FILES, collection

README_CHARS = 3500
README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme")


def _readme(ctx: ToolContext) -> tuple[str | None, str]:
    candidates = sorted(
        (p for p in ctx.by_path if posixpath.basename(p).lower() in README_NAMES),
        key=lambda p: (p.count("/"), len(p)),
    )
    if not candidates:
        return None, ""
    path = candidates[0]
    return path, (ctx.content(path) or "")[:README_CHARS]


def central_files(repo_id: str, limit: int = 12) -> list[tuple[str, int]]:
    """Files imported by the most other files (in-degree in the dependency graph)."""
    counts: Counter[str] = Counter()
    for edge in collection(EDGES).find(
        {"repo_id": ObjectId(repo_id), "external": False}, {"dst": 1, "src": 1}
    ):
        if edge["dst"] != edge["src"]:
            counts[edge["dst"]] += 1
    return counts.most_common(limit)


def internal_edges(repo_id: str) -> list[tuple[str, str]]:
    return [
        (edge["src"], edge["dst"])
        for edge in collection(EDGES).find(
            {"repo_id": ObjectId(repo_id), "external": False}, {"dst": 1, "src": 1}
        )
        if edge["src"] != edge["dst"]
    ]


def _group(path: str, depth: int = 2) -> str:
    parts = path.split("/")[:-1][:depth]
    return "/".join(parts) + "/" if parts else "(root files)"


def dependency_summary(edges: list[tuple[str, str]], limit: int = 20) -> str:
    """Import counts between directories; between files when the code lives in one directory."""
    groups: Counter[tuple[str, str]] = Counter(
        (_group(src), _group(dst)) for src, dst in edges if _group(src) != _group(dst)
    )
    pairs = groups if len(groups) >= 3 else Counter(edges)
    if not pairs:
        return "(no internal imports detected)"
    return "\n".join(
        f"  - {src} -> {dst} ({n} import{'s' if n != 1 else ''})"
        for (src, dst), n in pairs.most_common(limit)
    )


def symbol_rich_files(repo_id: str, limit: int = 10) -> list[tuple[str, int]]:
    pipeline = [
        {"$match": {"repo_id": ObjectId(repo_id)}},
        {"$project": {"path": 1, "n": {"$size": {"$ifNull": ["$symbols", []]}}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ]
    return [(doc["path"], doc["n"]) for doc in collection(FILES).aggregate(pipeline) if doc["n"]]


def build_digest(ctx: ToolContext) -> str:
    repo = ctx.repository
    paths = list(ctx.by_path)
    lines: list[str] = [
        f"Repository: {repo.full_name} "
        f"(branch {repo.default_branch}, commit {repo.commit_sha[:10]})",
    ]
    if repo.description:
        lines.append(f"GitHub description: {repo.description}")
    stats: dict[str, Any] = repo.stats or {}
    lines.append(
        f"Size: {stats.get('files', len(paths))} files, {stats.get('lines', '?')} lines, "
        f"{stats.get('symbols', '?')} symbols"
    )
    if repo.languages:
        langs = ", ".join(f"{k} {v}%" for k, v in list(repo.languages.items())[:6])
        lines.append(f"Languages: {langs}")
    if repo.frameworks:
        lines.append(f"Frameworks & tools: {', '.join(repo.frameworks)}")
    managers = (repo.detection or {}).get("package_managers") or []
    if managers:
        lines.append(f"Package managers: {', '.join(managers)}")
    scripts = (repo.detection or {}).get("scripts") or {}
    if scripts:
        lines.append("Scripts found in manifests:")
        lines += [
            f"  - {name}: {cmd}" if cmd else f"  - {name}"
            for name, cmd in list(scripts.items())[:15]
        ]
    manifests = (repo.detection or {}).get("manifests") or []
    if manifests:
        lines.append(f"Manifests: {', '.join(manifests[:12])}")

    lines.append("Top-level layout:")
    lines += [f"  - {name} ({count} files)" for name, count in top_level_structure(paths, limit=20)]

    entries = entry_point_candidates(paths)
    if entries:
        lines.append(f"Likely entry points: {', '.join(entries)}")
    central = central_files(ctx.repo_id)
    if central:
        lines.append("Most imported files (imported by N files):")
        lines += [f"  - {path} ({n})" for path, n in central]
    rich = symbol_rich_files(ctx.repo_id)
    if rich:
        lines.append("Files defining the most functions/classes:")
        lines += [f"  - {path} ({n} symbols)" for path, n in rich]

    digest = "\n".join(lines)
    readme_path, readme = _readme(ctx)
    if readme_path:
        digest += "\n\n" + wrap("readme_excerpt", readme, readme_path)
    return digest
