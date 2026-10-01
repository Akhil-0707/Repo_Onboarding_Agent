"""No hallucinated references: every path / line range the model outputs is checked against the
real file index and either repaired (normalised path, clamped range, symbol lookup) or removed."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_LINE_SUFFIX = re.compile(r"[:#]L?(\d+)(?:-L?(\d+))?$")


@dataclass
class RefReport:
    checked: int = 0
    repaired: int = 0
    dropped: int = 0
    dropped_paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "repaired": self.repaired,
            "dropped": self.dropped,
            "dropped_paths": self.dropped_paths[:20],
        }


class FileIndex:
    def __init__(
        self,
        files: list[dict[str, Any]],
        symbols: dict[str, list[dict[str, Any]]] | None = None,
        repo_name: str = "",
    ) -> None:
        self.lines = {f["path"]: max(1, int(f.get("lines") or 1)) for f in files}
        self.lower = {p.lower(): p for p in self.lines}
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for path in self.lines:
            self.by_name[posixpath.basename(path).lower()].append(path)
        self.dirs = {posixpath.dirname(p) for p in self.lines} - {""}
        for directory in list(self.dirs):  # include ancestors
            while "/" in directory:
                directory = directory.rsplit("/", 1)[0]
                self.dirs.add(directory)
        self.symbols = symbols or {}
        self.repo_name = repo_name.lower()

    # --- normalisation -------------------------------------------------------------------
    def _clean(self, raw: str) -> tuple[str, int | None, int | None]:
        text = raw.strip().strip("`'\"").strip()
        start = end = None
        match = _LINE_SUFFIX.search(text)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            text = text[: match.start()]
        text = text.replace("\\", "/").removeprefix("./").lstrip("/")
        for prefix in (f"{self.repo_name}/", f"{self.repo_name.split('/')[-1]}/"):
            if self.repo_name and text.lower().startswith(prefix) and text not in self.lines:
                text = text[len(prefix) :]
        return posixpath.normpath(text) if text else "", start, end

    def resolve_file(self, raw: str | None) -> tuple[str | None, int | None, int | None]:
        if not raw:
            return None, None, None
        text, start, end = self._clean(raw)
        if text in self.lines:
            return text, start, end
        if text.lower() in self.lower:
            return self.lower[text.lower()], start, end
        suffix = [p for p in self.lines if p.endswith(f"/{text}")]
        if len(suffix) == 1:
            return suffix[0], start, end
        same_name = self.by_name.get(posixpath.basename(text).lower(), [])
        if len(same_name) == 1:
            return same_name[0], start, end
        return None, None, None

    def resolve_dir(self, raw: str | None) -> str | None:
        if not raw:
            return None
        text, _, _ = self._clean(raw.rstrip("/"))
        if text in self.dirs:
            return text
        lowered = {d.lower(): d for d in self.dirs}
        return lowered.get(text.lower())

    def clamp(self, path: str, start: int | None, end: int | None) -> tuple[int | None, int | None]:
        total = self.lines[path]
        if start is None and end is None:
            return None, None
        start = start or end or 1
        end = end or start
        if start > end:
            start, end = end, start
        if start > total:
            return None, None  # nonsense range: fall back to the whole file
        return max(1, start), min(end, total)

    def symbol_range(self, path: str, name: str) -> tuple[int, int] | None:
        wanted = name.split(".")[-1].split("(")[0].strip().lower()
        for symbol in self.symbols.get(path, []):
            if symbol["name"].lower() == wanted:
                return int(symbol["start_line"]), int(symbol["end_line"])
        return None

    def find_symbol(self, name: str) -> tuple[str, int, int] | None:
        wanted = name.split(".")[-1].split("(")[0].strip().lower()
        hits = [
            (path, int(s["start_line"]), int(s["end_line"]))
            for path, symbols in self.symbols.items()
            for s in symbols
            if s["name"].lower() == wanted
        ]
        return hits[0] if len(hits) == 1 else None


def _fix_file_ref(item: dict[str, Any], index: FileIndex, report: RefReport) -> bool:
    """Repair ``item`` in place; False when it cannot point anywhere real."""
    report.checked += 1
    raw = item.get("path")
    path, start, end = index.resolve_file(raw)
    if path is None:
        report.dropped += 1
        report.dropped_paths.append(str(raw))
        return False
    start = item.get("start_line") or start
    end = item.get("end_line") or end
    start, end = index.clamp(path, start, end)
    if (path, start, end) != (raw, item.get("start_line"), item.get("end_line")):
        report.repaired += 1
    item.update(path=path, start_line=start, end_line=end)
    return True


def repair_overview(data: dict[str, Any], index: FileIndex) -> RefReport:
    report = RefReport()
    kept = []
    for item in data.get("structure", []):
        report.checked += 1
        directory = index.resolve_dir(item.get("path"))
        if directory is not None:
            if item["path"] != f"{directory}/":
                report.repaired += 1
            item["path"] = f"{directory}/"
            kept.append(item)
            continue
        report.checked -= 1  # counted again below
        if _fix_file_ref(item, index, report):
            item.pop("start_line", None)
            item.pop("end_line", None)
            kept.append(item)
    data["structure"] = kept
    data["entry_points"] = [
        e for e in data.get("entry_points", []) if _fix_file_ref(e, index, report)
    ]
    return report


def repair_start_here(data: dict[str, Any], index: FileIndex) -> RefReport:
    report = RefReport()
    seen: set[str] = set()
    kept = []
    for item in data.get("files", []):
        if _fix_file_ref(item, index, report) and item["path"] not in seen:
            seen.add(item["path"])
            kept.append(item)
    data["files"] = kept
    return report


def repair_glossary(data: dict[str, Any], index: FileIndex) -> RefReport:
    """Terms are kept even without a location; locations are verified or looked up."""
    report = RefReport()
    terms = []
    seen: set[str] = set()
    for term in data.get("terms", []):
        key = term["term"].lower()
        if key in seen:
            continue
        seen.add(key)
        if term.get("path"):
            if not _fix_file_ref(term, index, report):
                term.update(path=None, start_line=None, end_line=None)
            elif term.get("start_line") is None:
                found = index.symbol_range(term["path"], term["term"])
                if found:
                    term["start_line"], term["end_line"] = found
        else:
            found_anywhere = index.find_symbol(term["term"])
            if found_anywhere:
                term["path"], term["start_line"], term["end_line"] = found_anywhere
                report.repaired += 1
        terms.append(term)
    data["terms"] = terms
    return report
