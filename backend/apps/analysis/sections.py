"""Registry of generated sections, in the order they are produced."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from apps.agents import schemas
from apps.agents.citations import (
    FileIndex,
    RefReport,
    repair_architecture,
    repair_glossary,
    repair_overview,
    repair_start_here,
    repair_tour,
)
from apps.agents.digest import dependency_summary, internal_edges
from apps.agents.flowtrace import ensure_flow_trace
from apps.agents.mermaid import render_mermaid
from apps.agents.structured import OutputRejectedError
from apps.agents.tools import ToolContext


class SectionCheckError(OutputRejectedError):
    """Output was schema-valid but unusable after reference repair (e.g. no real files left).
    The model is asked to fix it; the section fails only when the repairs run out."""


def _start_here_params(ctx: ToolContext) -> dict[str, Any]:
    count = len(ctx.files)
    return {"min_files": min(8, max(1, count)), "max_files": min(15, max(1, count))}


def _check_start_here(data: dict[str, Any]) -> None:
    if not data["files"]:
        raise SectionCheckError(
            "None of the suggested files exist in the repository. Use exact paths from the "
            "digest or the research notes."
        )


def _check_overview(data: dict[str, Any]) -> None:
    if not data["structure"]:
        raise SectionCheckError(
            "'structure' referenced no real paths. Use exact directories or files from the digest."
        )


def _architecture_params(ctx: ToolContext) -> dict[str, Any]:
    return {"dependency_summary": dependency_summary(internal_edges(ctx.repo_id))}


def _finish_architecture(data: dict[str, Any], index: FileIndex) -> RefReport:
    report = repair_architecture(data, index)
    data["mermaid"] = render_mermaid(data)
    return report


def _check_architecture(data: dict[str, Any]) -> None:
    if len(data["modules"]) < 2:
        raise SectionCheckError(
            "Fewer than 2 modules point at real files or directories. Use exact paths from the "
            "digest or the research notes."
        )


def _tour_params(ctx: ToolContext) -> dict[str, Any]:
    count = len(ctx.files)
    return {"min_steps": min(8, max(3, count)), "max_steps": min(12, max(3, count))}


def _check_tour(data: dict[str, Any]) -> None:
    if len(data["steps"]) < 3:
        raise SectionCheckError(
            "Fewer than 3 steps point at real files. Use exact paths from the digest or notes."
        )
    if not any(step["kind"] == "flow_trace" for step in data["steps"]):
        raise SectionCheckError(
            "Every flow_trace step pointed at a file that does not exist. Trace a flow through "
            "real files from the digest or notes."
        )


@dataclass(frozen=True)
class SectionSpec:
    key: str
    label: str
    schema: type[BaseModel]
    repair: Callable[[dict[str, Any], FileIndex], RefReport]
    params: Callable[[ToolContext], dict[str, Any]] = field(default=lambda ctx: {})
    check: Callable[[dict[str, Any]], None] | None = None
    ensure: Callable[..., bool] | None = None
    """Optional follow-up model call after repair (``data, llm, **structured_kwargs``)."""
    tools: list[str] | None = None
    max_tokens: int = 3000


SECTIONS: list[SectionSpec] = [
    SectionSpec("overview", "Overview", schemas.Overview, repair_overview, check=_check_overview),
    SectionSpec(
        "architecture",
        "Architecture",
        schemas.Architecture,
        _finish_architecture,
        params=_architecture_params,
        check=_check_architecture,
    ),
    SectionSpec(
        "start_here",
        "Start Here",
        schemas.StartHere,
        repair_start_here,
        params=_start_here_params,
        check=_check_start_here,
    ),
    SectionSpec(
        "tour",
        "Guided Tour",
        schemas.Tour,
        repair_tour,
        params=_tour_params,
        check=_check_tour,
        ensure=ensure_flow_trace,
        max_tokens=4500,
    ),
    SectionSpec("glossary", "Glossary", schemas.Glossary, repair_glossary, max_tokens=3500),
]

SECTION_KEYS = [s.key for s in SECTIONS]


def get_section(key: str) -> SectionSpec | None:
    return next((s for s in SECTIONS if s.key == key), None)
