"""Citations in chat answers.

The model is asked to cite as ``[path:start-end]``. Every bracketed reference is checked
against the repository's file index: real ones are normalised (exact path, clamped lines),
invented ones are removed from the text. Backticked paths that resolve to real files are
upgraded to citations too; other backticked text is left alone. Fenced code is never touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from apps.agents.citations import FileIndex

_REF = r"(?P<path>[A-Za-z0-9_@+./-]+?)" r"(?:(?::|#L)(?P<start>\d+)(?:-L?(?P<end>\d+))?)?"
# Only tokens that look like a file path count: a directory part or a file extension.
_PATH_LIKE = re.compile(r"/|\.[A-Za-z][A-Za-z0-9]{0,9}$")
# [path:1-2] but not a Markdown link [text](url)
_BRACKETED = re.compile(r"\[" + _REF + r"\](?!\()")
_BACKTICKED = re.compile(r"`" + _REF + r"`")
_FENCE = re.compile(r"(```.*?(?:```|$))", re.DOTALL)
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r"(?<=\S)[ \t]+([,.;:!?])")
_DOUBLE_SPACE = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")


@dataclass
class AnswerRefs:
    text: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    stripped: list[str] = field(default_factory=list)


def format_citation(path: str, start: int | None, end: int | None) -> str:
    if start is None:
        return f"[{path}]"
    return f"[{path}:{start}]" if end in (None, start) else f"[{path}:{start}-{end}]"


def _resolve(match: re.Match[str], index: FileIndex) -> tuple[str, int | None, int | None] | None:
    path, _, _ = index.resolve_file(match.group("path"))
    if path is None:
        return None
    start = int(match.group("start")) if match.group("start") else None
    end = int(match.group("end")) if match.group("end") else None
    start, end = index.clamp(path, start, end)
    return path, start, end


def process_answer(text: str, index: FileIndex) -> AnswerRefs:
    result = AnswerRefs(text="")
    seen: set[tuple[str, int | None, int | None]] = set()

    def keep(ref: tuple[str, int | None, int | None]) -> str:
        if ref not in seen:
            seen.add(ref)
            result.citations.append({"path": ref[0], "start_line": ref[1], "end_line": ref[2]})
        return format_citation(*ref)

    def bracketed(match: re.Match[str]) -> str:
        ref = _resolve(match, index)
        if ref is not None:
            return keep(ref)
        if _PATH_LIKE.search(match.group("path")):  # a citation of a file that does not exist
            result.stripped.append(match.group(0))
            return ""
        return match.group(0)  # ordinary bracketed text such as [0.5] or [optional]

    def backticked(match: re.Match[str]) -> str:
        if not _PATH_LIKE.search(match.group("path")):
            return match.group(0)
        ref = _resolve(match, index)
        return keep(ref) if ref is not None else match.group(0)

    parts = _FENCE.split(text)
    for i, part in enumerate(parts):
        if i % 2 == 1:  # fenced code block
            continue
        part = _BRACKETED.sub(bracketed, part)
        part = _BACKTICKED.sub(backticked, part)
        if result.stripped:
            part = _EMPTY_PARENS.sub("", part)
            part = _DOUBLE_SPACE.sub(" ", part)
            part = _SPACE_BEFORE_PUNCT.sub(r"\1", part)
        parts[i] = part
    result.text = "".join(parts).strip()
    return result
