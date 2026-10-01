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
    repair_glossary,
    repair_overview,
    repair_start_here,
)
from apps.agents.tools import ToolContext


class SectionCheckError(Exception):
    """Output was schema-valid but unusable after reference repair (e.g. no real files left)."""


def _start_here_params(ctx: ToolContext) -> dict[str, Any]:
    count = len(ctx.files)
    return {"min_files": min(8, max(1, count)), "max_files": min(15, max(1, count))}


def _check_start_here(data: dict[str, Any]) -> None:
    if not data["files"]:
        raise SectionCheckError("None of the suggested files exist in the repository.")


def _check_overview(data: dict[str, Any]) -> None:
    if not data["structure"]:
        raise SectionCheckError("The structure section referenced no real paths.")


@dataclass(frozen=True)
class SectionSpec:
    key: str
    label: str
    schema: type[BaseModel]
    repair: Callable[[dict[str, Any], FileIndex], RefReport]
    params: Callable[[ToolContext], dict[str, Any]] = field(default=lambda ctx: {})
    check: Callable[[dict[str, Any]], None] | None = None
    tools: list[str] | None = None
    max_tokens: int = 3000


SECTIONS: list[SectionSpec] = [
    SectionSpec("overview", "Overview", schemas.Overview, repair_overview, check=_check_overview),
    SectionSpec(
        "start_here",
        "Start Here",
        schemas.StartHere,
        repair_start_here,
        params=_start_here_params,
        check=_check_start_here,
    ),
    SectionSpec("glossary", "Glossary", schemas.Glossary, repair_glossary, max_tokens=3500),
]

SECTION_KEYS = [s.key for s in SECTIONS]


def get_section(key: str) -> SectionSpec | None:
    return next((s for s in SECTIONS if s.key == key), None)
