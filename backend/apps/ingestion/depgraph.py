"""Resolve parsed imports to files inside the repository (module-level dependency graph).

Edges point from a source file to either a file (Python, JS/TS, Java) or a package directory
(Go). Imports that do not resolve inside the repo are recorded as external dependencies
(``dst`` is the package name, ``external=True``).
"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from apps.ingestion.parsing import ImportRef, ParsedFile

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
JS_LANGUAGES = {"javascript", "typescript", "tsx"}


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    external: bool
    dst_is_dir: bool = False
    specifier: str = ""

    def as_document(self) -> dict[str, object]:
        return {
            "src": self.src,
            "dst": self.dst,
            "external": self.external,
            "dst_is_dir": self.dst_is_dir,
            "specifier": self.specifier,
            "src_dir": posixpath.dirname(self.src),
        }


def module_of(path: str) -> str:
    """Directory that groups a file into a module ("." for the repo root)."""
    return posixpath.dirname(path) or "."


class _PythonIndex:
    def __init__(self, paths: set[str]) -> None:
        self.by_module: dict[str, list[str]] = defaultdict(list)
        for path in sorted(paths, key=lambda p: (p.count("/"), p)):
            if not path.endswith((".py", ".pyi")):
                continue
            parts = list(PurePosixPath(path).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            # Index every suffix so `src/pkg/mod.py` resolves as `pkg.mod` and `src.pkg.mod`.
            for i in range(len(parts)):
                if parts[i:]:
                    self.by_module[".".join(parts[i:])].append(path)

    def lookup(self, module: str) -> str | None:
        hits = self.by_module.get(module)
        return hits[0] if hits else None


def _python_target(src: str, ref: ImportRef, index: _PythonIndex, paths: set[str]) -> str | None:
    if ref.level:
        base = PurePosixPath(src).parent
        for _ in range(ref.level - 1):
            base = base.parent
        rel = ref.module.replace(".", "/") if ref.module else ""
        base_str = "" if base.as_posix() == "." else base.as_posix()
        stem = "/".join(p for p in (base_str, rel) if p)
        module_files = [f"{stem}.py", f"{stem}/__init__.py"] if rel else []
        # `from . import util` -> ./util.py ; `from .pkg import mod` -> ./pkg/mod.py
        name_files = [
            "/".join(p for p in (stem, f"{name}{suffix}") if p)
            for name in ref.names
            for suffix in (".py", "/__init__.py")
        ]
        package_init = [] if rel else ["/".join(p for p in (stem, "__init__.py") if p)]
        candidates = module_files + name_files + package_init
        return next((c for c in candidates if c in paths), None)
    found = index.lookup(ref.module)
    if found:
        return found
    for name in ref.names:  # `from pkg import module`
        found = index.lookup(f"{ref.module}.{name}")
        if found:
            return found
    parent = ref.module.rsplit(".", 1)[0] if "." in ref.module else None
    return index.lookup(parent) if parent else None


def _js_target(src: str, spec: str, paths: set[str]) -> str | None:
    if spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(src), spec))
    elif spec.startswith(("@/", "~/")):
        base = posixpath.normpath(f"src/{spec[2:]}")
    else:
        return None
    stem, ext = posixpath.splitext(base)
    candidates = [base]
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:  # TS sources imported with a .js suffix
        candidates += [f"{stem}{e}" for e in JS_EXTENSIONS]
    candidates += [f"{base}{e}" for e in JS_EXTENSIONS]
    candidates += [f"{base}/index{e}" for e in JS_EXTENSIONS]
    return next((c for c in candidates if c in paths), None)


def _js_package(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]


def _java_target(spec: str, by_suffix: dict[str, str], dirs: set[str]) -> tuple[str | None, bool]:
    parts = spec.split(".")
    if parts[-1] == "*":
        rel = "/".join(parts[:-1])
        match = next((d for d in dirs if d == rel or d.endswith(f"/{rel}")), None)
        return match, True
    for end in (len(parts), len(parts) - 1):  # static imports: drop the member name
        key = "/".join(parts[:end]) + ".java"
        if key in by_suffix:
            return by_suffix[key], False
    return None, False


def build_edges(
    parsed: dict[str, ParsedFile], all_paths: set[str], go_module: str | None = None
) -> list[Edge]:
    py_index = _PythonIndex(all_paths)
    java_by_suffix: dict[str, str] = {}
    dirs: set[str] = set()
    for path in all_paths:
        dirs.add(module_of(path))
        if path.endswith(".java"):
            parts = path.split("/")
            for i in range(len(parts)):
                java_by_suffix.setdefault("/".join(parts[i:]), path)

    edges: set[Edge] = set()
    for src, info in parsed.items():
        for ref in info.imports:
            spec = ref.module
            if info.language == "python":
                target = _python_target(src, ref, py_index, all_paths)
                if target and target != src:
                    edges.add(Edge(src, target, False, specifier=spec or "." * ref.level))
                elif not ref.level and spec:
                    edges.add(Edge(src, spec.split(".")[0], True, specifier=spec))
            elif info.language in JS_LANGUAGES:
                target = _js_target(src, spec, all_paths)
                if target and target != src:
                    edges.add(Edge(src, target, False, specifier=spec))
                elif not spec.startswith((".", "/")):
                    edges.add(Edge(src, _js_package(spec), True, specifier=spec))
            elif info.language == "java":
                target, is_dir = _java_target(spec, java_by_suffix, dirs)
                if target and target != src:
                    edges.add(Edge(src, target, False, dst_is_dir=is_dir, specifier=spec))
                else:
                    edges.add(Edge(src, ".".join(spec.split(".")[:2]), True, specifier=spec))
            elif info.language == "go":
                if go_module and (spec == go_module or spec.startswith(f"{go_module}/")):
                    rel = spec[len(go_module) :].strip("/") or "."
                    if rel in dirs and rel != module_of(src):
                        edges.add(Edge(src, rel, False, dst_is_dir=True, specifier=spec))
                else:
                    edges.add(Edge(src, spec, True, specifier=spec))
    return sorted(edges, key=lambda e: (e.src, e.dst))
