"""Split files into retrieval chunks.

Parsed languages are chunked by symbol: each top-level function/class is one chunk; a class
that is too big becomes a header chunk plus one chunk per method; anything still too big is
split into overlapping line windows. Code between symbols (imports, constants, ``main``
blocks) becomes "module" chunks. Unparsed languages use overlapping line windows.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.ingestion.parsing import Symbol

MAX_CHUNK_LINES = 120
MAX_CHUNK_CHARS = 6000  # ~1,500 tokens
SPLIT_OVERLAP_LINES = 10
WINDOW_LINES = 80
WINDOW_OVERLAP_LINES = 15


@dataclass(frozen=True)
class Chunk:
    path: str
    language: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    content: str

    def as_document(self) -> dict[str, object]:
        return {
            "path": self.path,
            "language": self.language,
            "symbol": self.symbol,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
        }


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _fits(lines: list[str], start: int, end: int) -> bool:
    if end - start + 1 > MAX_CHUNK_LINES:
        return False
    return len(_slice(lines, start, end)) <= MAX_CHUNK_CHARS


def _windows(start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    step = max(1, size - overlap)
    while cursor <= end:
        spans.append((cursor, min(end, cursor + size - 1)))
        if cursor + size - 1 >= end:
            break
        cursor += step
    return spans


def _char_bounded(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """Line windows that also respect the character cap (long minified-ish lines)."""
    spans: list[tuple[int, int]] = []
    for w_start, w_end in _windows(start, end, MAX_CHUNK_LINES, SPLIT_OVERLAP_LINES):
        cursor = w_start
        while cursor <= w_end:
            stop = cursor
            size = len(lines[cursor - 1]) if cursor - 1 < len(lines) else 0
            while stop < w_end and size + len(lines[stop]) + 1 <= MAX_CHUNK_CHARS:
                stop += 1
                size += len(lines[stop - 1]) + 1
            spans.append((cursor, stop))
            cursor = stop + 1
    return spans


class _Builder:
    def __init__(self, path: str, language: str, lines: list[str]) -> None:
        self.path = path
        self.language = language
        self.lines = lines
        self.chunks: list[Chunk] = []

    def emit(self, start: int, end: int, symbol: str | None, kind: str) -> None:
        start, end = max(1, start), min(len(self.lines), end)
        if end < start:
            return
        content = _slice(self.lines, start, end)
        if not content.strip():
            return
        if _fits(self.lines, start, end):
            self.chunks.append(Chunk(self.path, self.language, symbol, kind, start, end, content))
            return
        spans = _char_bounded(self.lines, start, end)
        for index, (s, e) in enumerate(spans, start=1):
            part = _slice(self.lines, s, e)
            if part.strip():
                label = f"{symbol} (part {index}/{len(spans)})" if symbol else None
                self.chunks.append(Chunk(self.path, self.language, label, kind, s, e, part))

    def gap(self, start: int, end: int) -> None:
        """Module-level code between symbols."""
        if end < start:
            return
        if _fits(self.lines, start, end):
            self.emit(start, end, None, "module")
            return
        for s, e in _windows(start, end, WINDOW_LINES, WINDOW_OVERLAP_LINES):
            self.emit(s, e, None, "module")


def chunk_file(path: str, language: str, text: str, symbols: list[Symbol] | None) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    builder = _Builder(path, language, lines)

    if not symbols:
        for start, end in _windows(1, len(lines), WINDOW_LINES, WINDOW_OVERLAP_LINES):
            builder.emit(start, end, None, "file")
        return builder.chunks

    top_level = [s for s in symbols if s.parent is None]
    # Drop symbols nested inside another top-level symbol (e.g. Java inner classes).
    units: list[Symbol] = []
    for symbol in sorted(top_level, key=lambda s: (s.start_line, -s.end_line)):
        if (
            units
            and symbol.start_line >= units[-1].start_line
            and symbol.end_line <= units[-1].end_line
        ):
            continue
        units.append(symbol)

    cursor = 1
    for unit in units:
        builder.gap(cursor, unit.start_line - 1)
        if _fits(lines, unit.start_line, unit.end_line):
            builder.emit(unit.start_line, unit.end_line, unit.name, unit.kind)
        else:
            members = sorted(
                (
                    s
                    for s in symbols
                    if s.parent == unit.name
                    and unit.start_line <= s.start_line <= s.end_line <= unit.end_line
                ),
                key=lambda s: s.start_line,
            )
            if members:
                member_cursor = unit.start_line
                for member in members:
                    if member.start_line < member_cursor:
                        continue
                    builder.emit(member_cursor, member.start_line - 1, unit.name, unit.kind)
                    builder.emit(
                        member.start_line,
                        member.end_line,
                        f"{unit.name}.{member.name}",
                        member.kind,
                    )
                    member_cursor = member.end_line + 1
                builder.emit(member_cursor, unit.end_line, unit.name, unit.kind)
            else:
                builder.emit(unit.start_line, unit.end_line, unit.name, unit.kind)
        cursor = max(cursor, unit.end_line + 1)
    builder.gap(cursor, len(lines))
    return builder.chunks
