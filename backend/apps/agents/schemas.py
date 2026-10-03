"""Pydantic schemas for every generated section. They double as the JSON schemas sent to the
model (guided decoding) and as the validators for what comes back."""

from __future__ import annotations

import re
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    # Small models sometimes add extra keys; ignore them instead of failing the section.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _coerce_kind(value: Any, allowed: tuple[str, ...]) -> Any:
    """'Flow-Trace' -> 'flow_trace'; unknown kinds become 'other' instead of failing the section."""
    if not isinstance(value, str):
        return value
    kind = re.sub(r"[\s-]+", "_", value.strip().lower())
    return kind if kind in allowed else "other"


class TechItem(_Model):
    name: str = Field(..., min_length=1, max_length=60, description="Language, framework or tool")
    role: str = Field(..., min_length=3, max_length=200, description="What it is used for here")


class StructureItem(_Model):
    path: str = Field(..., min_length=1, description="Directory or file path, e.g. 'src/api/'")
    description: str = Field(..., min_length=3, max_length=300)


class RunStep(_Model):
    description: str = Field(..., min_length=3, max_length=300)
    command: str | None = Field(None, max_length=300, description="Shell command, if any")


class EntryPoint(_Model):
    path: str = Field(..., min_length=1)
    description: str = Field(..., min_length=3, max_length=300)
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)


class Overview(_Model):
    summary: str = Field(
        ..., min_length=40, max_length=1500, description="2-4 sentences: what the project does"
    )
    tech_stack: list[TechItem] = Field(..., min_length=1, max_length=15)
    structure: list[StructureItem] = Field(..., min_length=1, max_length=15)
    prerequisites: list[str] = Field(default_factory=list, max_length=10)
    how_to_run: list[RunStep] = Field(default_factory=list, max_length=12)
    entry_points: list[EntryPoint] = Field(default_factory=list, max_length=8)
    starter_questions: list[str] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="Questions a newcomer might ask about this codebase",
    )


class StartHereItem(_Model):
    path: str = Field(..., min_length=1, description="File path")
    reason: str = Field(..., min_length=10, max_length=300, description="Why read it, in one line")
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)


class StartHere(_Model):
    files: list[StartHereItem] = Field(
        ..., min_length=1, max_length=15, description="Ordered: read the first one first"
    )


GlossaryKind = Literal["concept", "class", "function", "module", "config", "other"]


class GlossaryTerm(_Model):
    term: str = Field(..., min_length=1, max_length=80)
    kind: GlossaryKind = "concept"
    definition: str = Field(..., min_length=10, max_length=500)
    path: str | None = Field(None, description="File where it is defined, if any")
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)


class Glossary(_Model):
    terms: list[GlossaryTerm] = Field(..., min_length=3, max_length=40)


ModuleKind = Literal[
    "entry", "core", "service", "data", "ui", "config", "util", "external", "test", "other"
]


class ArchModule(_Model):
    id: str = Field(..., min_length=1, max_length=40, description="Short unique id, e.g. 'api'")
    name: str = Field(..., min_length=1, max_length=60)
    kind: ModuleKind = "core"
    paths: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Directories (ending with '/') or files that make up this module",
    )
    description: str = Field(..., min_length=3, max_length=300)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> Any:
        return _coerce_kind(value, get_args(ModuleKind))


class ArchEdge(_Model):
    source: str = Field(..., min_length=1, description="Id of the module that uses the target")
    target: str = Field(..., min_length=1)
    label: str | None = Field(None, max_length=60, description="Short verb phrase")


class Architecture(_Model):
    summary: str = Field(
        ..., min_length=30, max_length=1200, description="How the system is organised"
    )
    modules: list[ArchModule] = Field(..., min_length=2, max_length=14)
    edges: list[ArchEdge] = Field(default_factory=list, max_length=30)


TourKind = Literal[
    "intro", "entry_point", "flow_trace", "core_logic", "data_model", "config", "testing", "other"
]


class TourStep(_Model):
    title: str = Field(..., min_length=3, max_length=100)
    kind: TourKind = "other"
    path: str = Field(..., min_length=1)
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)
    symbol: str | None = Field(None, max_length=120, description="Function or class in focus")
    explanation: str = Field(..., min_length=20, max_length=1500, description="2-5 sentences")

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> Any:
        return _coerce_kind(value, get_args(TourKind))


FLOW_TRACE_REQUIRED = (
    'At least one step must have kind "flow_trace": follow one real request or command through '
    "the code, hop by hop, with the file and function of each hop."
)


class Tour(_Model):
    """A flow trace is required, but enforced after reference repair (``ensure_flow_trace``):
    small models write good tours yet often forget the label, and rewriting the whole tour
    to fix one label is the hardest possible repair for them."""

    intro: str = Field(..., min_length=20, max_length=800)
    steps: list[TourStep] = Field(..., min_length=3, max_length=14, description="Reading order")


class FlowTracePick(_Model):
    steps: list[int] = Field(
        ...,
        min_length=2,
        max_length=6,
        description="Numbers of the consecutive stops that follow one request or command",
    )
