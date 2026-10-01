"""No hallucinated references: every path / line range the model outputs is checked against the
real file index and either repaired (normalised path, clamped range, symbol lookup) or removed."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from collections.abc import Callable
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


def term_key(name: str, keep_case: bool = False) -> str:
    """``Command.parse()`` -> ``parse``: the identifier a symbol lookup should match."""
    key = name.split(".")[-1].split("(")[0].strip()
    return key if keep_case else key.lower()


class FileIndex:
    def __init__(
        self,
        files: list[dict[str, Any]],
        symbols: dict[str, list[dict[str, Any]]] | None = None,
        repo_name: str = "",
        content: Callable[[str], str | None] | None = None,
        edges: list[tuple[str, str]] | None = None,
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
        self._content = content
        self._text: dict[str, list[str] | None] = {}
        self.edges = edges or []  # internal (importer, imported) file pairs

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
        if start == end == 1 and total > 1:
            return None, None  # a lone "1-1" is filler small models write for "the whole file"
        return max(1, start), min(end, total)

    def lines_of(self, path: str) -> list[str] | None:
        if self._content is None:
            return None
        if path not in self._text:
            text = self._content(path)
            self._text[path] = text.splitlines() if text is not None else None
        return self._text[path]

    def mentions(self, path: str, start: int, end: int, name: str, slack: int = 2) -> bool | None:
        """Whether ``name`` appears near lines ``start``-``end``; None when contents are unknown."""
        lines = self.lines_of(path)
        if lines is None:
            return None
        window = "\n".join(lines[max(0, start - 1 - slack) : end + slack]).lower()
        return term_key(name) in window

    def symbol_range(self, path: str, name: str) -> tuple[int, int] | None:
        """Exact-case matches win (``command`` the method over ``Command`` the class)."""
        symbols = self.symbols.get(path, [])
        exact = term_key(name, keep_case=True)
        loose = exact.lower()
        match = next((s for s in symbols if s["name"] == exact), None) or next(
            (s for s in symbols if s["name"].lower() == loose), None
        )
        return (int(match["start_line"]), int(match["end_line"])) if match else None

    def find_symbol(self, name: str) -> tuple[str, int, int] | None:
        wanted = term_key(name)
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


def _fix_definition_lines(item: dict[str, Any], index: FileIndex, report: RefReport) -> None:
    """The symbol index beats guessed line numbers; unverifiable guesses are dropped."""
    path, start, end = item["path"], item.get("start_line"), item.get("end_line")
    name = item.get("symbol") or item.get("term") or ""
    found = index.symbol_range(path, name) if name else None
    if found:
        if found != (start, end):
            report.repaired += 1
        item["start_line"], item["end_line"] = found
    elif start is not None and name and index.mentions(path, start, end or start, name) is False:
        item["start_line"] = item["end_line"] = None
        report.repaired += 1


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
            else:
                _fix_definition_lines(term, index, report)
        else:
            found_anywhere = index.find_symbol(term["term"])
            if found_anywhere:
                term["path"], term["start_line"], term["end_line"] = found_anywhere
                report.repaired += 1
        terms.append(term)
    data["terms"] = terms
    return report


def repair_tour(data: dict[str, Any], index: FileIndex) -> RefReport:
    """Steps pointing at unknown files are dropped; symbols pin down the line range."""
    report = RefReport()
    seen: set[tuple[str, int | None, int | None]] = set()
    kept = []
    for step in data.get("steps", []):
        if not _fix_file_ref(step, index, report):
            continue
        if step.get("symbol"):
            _fix_definition_lines(step, index, report)
        key = (step["path"], step.get("start_line"), step.get("end_line"))
        if key not in seen:
            seen.add(key)
            kept.append(step)
    data["steps"] = kept
    return report


_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG.sub("_", text.lower()).strip("_")[:30] or "module"


def module_of(path: str, modules: list[dict[str, Any]]) -> str | None:
    """The module owning ``path``: an exact file match, else the longest directory prefix."""
    best, best_len = None, -1
    for module in modules:
        for owned in module["paths"]:
            if owned.endswith("/"):
                if path.startswith(owned) and len(owned) > best_len:
                    best, best_len = module["id"], len(owned)
            elif owned == path:
                return module["id"]
    return best


def repair_architecture(data: dict[str, Any], index: FileIndex, max_edges: int = 30) -> RefReport:
    """Verify module paths, normalise ids, resolve edges by id or name, then add the import
    edges the dependency graph proves (``derived``) so the map reflects the real code."""
    report = RefReport()
    modules: list[dict[str, Any]] = []
    alias: dict[str, str] = {}
    for module in data.get("modules", []):
        paths: list[str] = []
        for raw in module.get("paths", []):
            report.checked += 1
            directory = index.resolve_dir(raw)
            path = f"{directory}/" if directory is not None else index.resolve_file(raw)[0]
            if path is None:
                report.dropped += 1
                report.dropped_paths.append(str(raw))
                continue
            if path != raw:
                report.repaired += 1
            if path not in paths:
                paths.append(path)
        if not paths and module.get("kind") != "external":
            continue  # nothing real behind it
        base = _slug(module.get("id") or module["name"])
        new_id, n = base, 2
        while any(m["id"] == new_id for m in modules):
            new_id, n = f"{base}_{n}", n + 1
        for key in (module.get("id"), module.get("name")):
            if key:
                alias.setdefault(key.strip().lower(), new_id)
                alias.setdefault(_slug(key), new_id)
        modules.append({**module, "id": new_id, "paths": paths})
    data["modules"] = modules

    def resolve(ref: str) -> str | None:
        return alias.get(ref.strip().lower()) or alias.get(_slug(ref))

    imports: dict[tuple[str, str], int] = defaultdict(int)
    for src, dst in index.edges:
        a, b = module_of(src, modules), module_of(dst, modules)
        if a and b and a != b:
            imports[(a, b)] += 1

    edges: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for edge in data.get("edges", []):
        source, target = resolve(edge.get("source", "")), resolve(edge.get("target", ""))
        if not source or not target or source == target or (source, target) in pairs:
            continue
        pairs.add((source, target))
        edges.append(
            {**edge, "source": source, "target": target, "derived": False,
             "imports": imports.get((source, target), 0)}
        )  # fmt: skip
    for (source, target), count in sorted(imports.items(), key=lambda kv: -kv[1]):
        if len(edges) >= max_edges:
            break
        if (source, target) not in pairs:
            pairs.add((source, target))
            edges.append(
                {"source": source, "target": target, "label": None, "derived": True,
                 "imports": count}
            )  # fmt: skip
    data["edges"] = edges[:max_edges]
    return report
