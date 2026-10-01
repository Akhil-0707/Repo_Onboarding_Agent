"""Pydantic schemas for every generated section. They double as the JSON schemas sent to the
model (guided decoding) and as the validators for what comes back."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    # Small models sometimes add extra keys; ignore them instead of failing the section.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


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
