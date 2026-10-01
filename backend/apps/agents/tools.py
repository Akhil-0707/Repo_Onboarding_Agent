"""Read-only tools the agents can call, scoped to one repository snapshot.

Every tool has a Pydantic argument model (the source of the JSON schema sent to the model and
of strict validation), returns compact text for the model plus machine-readable citations,
and wraps repository text in ``<repo_content>`` delimiters: content from the repo is data,
never instructions.
"""

from __future__ import annotations

import difflib
import fnmatch
import json
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import re2
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.agents.repo_facts import entry_point_candidates, top_level_structure
from apps.ingestion import index_store
from apps.ingestion.index_store import BLOBS, EDGES, FILES, collection
from apps.repos.models import Repository
from apps.search.hybrid import hybrid_search

MAX_OUTPUT_CHARS = 8000
MAX_READ_LINES = 200
MAX_GREP_BYTES = 30 * 1024 * 1024


# --- plumbing ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    path: str
    start_line: int
    end_line: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "start_line": self.start_line, "end_line": self.end_line}


@dataclass
class ToolResult:
    ok: bool
    output: str
    citations: list[Citation] = field(default_factory=list)
    error_type: str | None = None


class ToolContext:
    """Per-agent-run cache of repo data shared by the tools."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.repo_id = str(repository.pk)

    @cached_property
    def files(self) -> list[dict[str, Any]]:
        return index_store.list_files(self.repo_id)

    @cached_property
    def by_path(self) -> dict[str, dict[str, Any]]:
        return {f["path"]: f for f in self.files}

    def content(self, path: str) -> str | None:
        file = index_store.get_file(self.repo_id, path)
        if file is None:
            return None
        return index_store.get_blob(file["blob_sha"]) or ""

    def suggest(self, path: str, n: int = 3) -> list[str]:
        candidates = list(self.by_path)
        close = difflib.get_close_matches(path, candidates, n=n, cutoff=0.5)
        name = posixpath.basename(path)
        same_name = [p for p in candidates if posixpath.basename(p) == name and p not in close]
        return (close + same_name)[:n]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _escape(text: str) -> str:
    return text.replace("</repo_content", "<\\/repo_content")


def wrap(source: str, body: str, path: str | None = None) -> str:
    attrs = f'source="{source}"' + (f' path="{path}"' if path else "")
    if len(body) > MAX_OUTPUT_CHARS:
        body = body[:MAX_OUTPUT_CHARS] + "\n… [output truncated]"
    return f"<repo_content {attrs}>\n{_escape(body)}\n</repo_content>"


def numbered(lines: list[str], start: int) -> str:
    width = len(str(start + len(lines) - 1))
    return "\n".join(f"{start + i:>{width}} | {line}" for i, line in enumerate(lines))


def _norm_path(path: str) -> str:
    return posixpath.normpath(path.strip().lstrip("/")).removeprefix("./") if path.strip() else ""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[ToolContext, Any], ToolResult]

    def schema(self) -> dict[str, Any]:
        parameters = self.args_model.model_json_schema()
        parameters.pop("title", None)
        for prop in parameters.get("properties", {}).values():
            prop.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


# --- tools ---------------------------------------------------------------------------------


class ListDirectoryArgs(ToolArgs):
    path: str = Field("", max_length=500, description="Directory path; empty for the repo root")


def list_directory(ctx: ToolContext, args: ListDirectoryArgs) -> ToolResult:
    base = _norm_path(args.path)
    if base in ctx.by_path:
        return ToolResult(
            False, f"'{base}' is a file. Use read_file to open it.", error_type="not_a_dir"
        )
    prefix = f"{base}/" if base else ""
    dirs: dict[str, int] = {}
    files: list[dict[str, Any]] = []
    for file in ctx.files:
        if not file["path"].startswith(prefix):
            continue
        rest = file["path"][len(prefix) :]
        if "/" in rest:
            head = rest.split("/", 1)[0]
            dirs[head] = dirs.get(head, 0) + 1
        else:
            files.append(file)
    if not dirs and not files:
        top = ", ".join(name for name, _ in top_level_structure(ctx.by_path)[:15])
        return ToolResult(False, f"No directory '{base}'. Top level: {top}", error_type="not_found")
    lines = [f"{base or '.'}/"]
    lines += [f"  {name}/  ({count} files)" for name, count in sorted(dirs.items())]
    lines += [f"  {f['path'][len(prefix):]}  ({f['lines']} lines)" for f in files]
    if len(lines) > 201:
        lines = [*lines[:201], f"  … {len(lines) - 201} more entries"]
    return ToolResult(True, wrap("list_directory", "\n".join(lines), base or "."))


class ReadFileArgs(ToolArgs):
    path: str = Field(..., min_length=1, max_length=500, description="Repo-relative file path")
    start_line: int = Field(1, ge=1, description="First line to read (1-based)")
    end_line: int | None = Field(None, ge=1, description="Last line to read (inclusive)")


def read_file(ctx: ToolContext, args: ReadFileArgs) -> ToolResult:
    path = _norm_path(args.path)
    content = ctx.content(path)
    if content is None:
        hint = ctx.suggest(path)
        extra = f" Did you mean: {', '.join(hint)}?" if hint else ""
        return ToolResult(False, f"File not found: {path}.{extra}", error_type="not_found")
    lines = content.splitlines()
    total = max(1, len(lines))
    if args.start_line > total:
        return ToolResult(False, f"{path} has only {total} lines.", error_type="out_of_range")
    end = min(args.end_line or total, total)
    if end < args.start_line:
        return ToolResult(False, "end_line must be >= start_line.", error_type="bad_range")
    note = ""
    if end - args.start_line + 1 > MAX_READ_LINES:
        end = args.start_line + MAX_READ_LINES - 1
        note = f"\n[showing {MAX_READ_LINES} lines; continue with start_line={end + 1}]"
    body = (
        f"{path} (lines {args.start_line}-{end} of {total})\n"
        f"{numbered(lines[args.start_line - 1 : end], args.start_line)}{note}"
    )
    return ToolResult(True, wrap("read_file", body, path), [Citation(path, args.start_line, end)])


class SearchCodeArgs(ToolArgs):
    query: str = Field(..., min_length=2, max_length=300, description="What to look for")
    limit: int = Field(8, ge=1, le=15, description="Maximum results")


def search_code(ctx: ToolContext, args: SearchCodeArgs) -> ToolResult:
    hits = hybrid_search(ctx.repo_id, args.query, limit=args.limit)
    if not hits:
        return ToolResult(True, wrap("search_code", f"No results for {args.query!r}."))
    blocks = []
    for hit in hits:
        label = f" ({hit.symbol})" if hit.symbol else ""
        snippet = hit.content.splitlines()[:15]
        more = "\n…" if hit.end_line - hit.start_line + 1 > 15 else ""
        blocks.append(
            f"### {hit.path}:{hit.start_line}-{hit.end_line}{label}\n"
            f"{numbered(snippet, hit.start_line)}{more}"
        )
    citations = [Citation(h.path, h.start_line, h.end_line) for h in hits]
    return ToolResult(True, wrap("search_code", "\n\n".join(blocks)), citations)


class GrepArgs(ToolArgs):
    pattern: str = Field(..., min_length=1, max_length=200, description="RE2 regular expression")
    path_glob: str | None = Field(None, max_length=200, description="e.g. 'src/**/*.py'")
    ignore_case: bool = Field(False, description="Case-insensitive match")
    max_results: int = Field(50, ge=1, le=200)


def grep(ctx: ToolContext, args: GrepArgs) -> ToolResult:
    try:
        regex = re2.compile(f"(?i){args.pattern}" if args.ignore_case else args.pattern)
    except re2.error as exc:
        return ToolResult(False, f"Invalid regular expression: {exc}", error_type="bad_pattern")
    files = [
        f
        for f in ctx.files
        if not args.path_glob
        or fnmatch.fnmatch(f["path"], args.path_glob)
        or fnmatch.fnmatch(f["path"], args.path_glob.replace("**/", ""))
    ]
    shas = {f["path"]: f["blob_sha"] for f in files}
    matches: list[str] = []
    citations: list[Citation] = []
    scanned = 0
    blobs = {
        d["_id"]: d["content"]
        for d in collection(BLOBS).find({"_id": {"$in": list(set(shas.values()))}})
    }
    for path in sorted(shas):
        content = blobs.get(shas[path], "")
        scanned += len(content)
        if scanned > MAX_GREP_BYTES:
            matches.append("[stopped: scan limit reached; narrow path_glob]")
            break
        for number, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{path}:{number}: {line.strip()[:200]}")
                citations.append(Citation(path, number, number))
                if len(citations) >= args.max_results:
                    break
        if len(citations) >= args.max_results:
            matches.append(f"[max_results={args.max_results} reached]")
            break
    if not citations:
        return ToolResult(True, wrap("grep", f"No matches for /{args.pattern}/."))
    return ToolResult(True, wrap("grep", "\n".join(matches)), citations)


class GetSymbolArgs(ToolArgs):
    name: str = Field(..., min_length=1, max_length=200, description="Function/class/method name")


def get_symbol(ctx: ToolContext, args: GetSymbolArgs) -> ToolResult:
    name = args.name
    parent = None
    if "." in name:
        parent, name = name.rsplit(".", 1)
    query: dict[str, Any] = {"repo_id": ObjectId(ctx.repo_id), "symbols.name": name}
    found = []
    for doc in collection(FILES).find(query, {"path": 1, "symbols": 1}):
        for symbol in doc["symbols"]:
            if symbol["name"] == name and (parent is None or symbol.get("parent") == parent):
                found.append((doc["path"], symbol))
    if not found:
        pattern = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
        for doc in collection(FILES).find(
            {"repo_id": ObjectId(ctx.repo_id), "symbols.name": pattern}, {"path": 1, "symbols": 1}
        ):
            found += [(doc["path"], s) for s in doc["symbols"] if s["name"].lower() == name.lower()]
    if not found:
        names = collection(FILES).distinct("symbols.name", {"repo_id": ObjectId(ctx.repo_id)})
        close = difflib.get_close_matches(name, names, n=5, cutoff=0.6)
        hint = f" Similar: {', '.join(close)}." if close else ""
        return ToolResult(False, f"No symbol named '{args.name}'.{hint}", error_type="not_found")
    found.sort(key=lambda item: (item[1].get("kind") == "method", item[0], item[1]["start_line"]))
    lines = []
    citations = []
    for path, symbol in found[:10]:
        owner = f" in {symbol['parent']}" if symbol.get("parent") else ""
        location = f"{path}:{symbol['start_line']}-{symbol['end_line']}"
        lines.append(f"{symbol['kind']} {symbol['name']}{owner} — {location}")
        citations.append(Citation(path, symbol["start_line"], symbol["end_line"]))
    path, symbol = found[0]
    source = (ctx.content(path) or "").splitlines()
    end = min(symbol["end_line"], symbol["start_line"] + 79)
    excerpt = numbered(source[symbol["start_line"] - 1 : end], symbol["start_line"])
    body = "\n".join(lines) + f"\n\nSource of the first match:\n{excerpt}"
    if end < symbol["end_line"]:
        body += f"\n[truncated; read_file {path} from line {end + 1}]"
    return ToolResult(True, wrap("get_symbol", body, path), citations)


class GetDependenciesArgs(ToolArgs):
    module: str = Field(..., min_length=1, max_length=500, description="File path or directory")


def get_dependencies(ctx: ToolContext, args: GetDependenciesArgs) -> ToolResult:
    module = _norm_path(args.module)
    repo = ObjectId(ctx.repo_id)
    is_file = module in ctx.by_path
    is_dir = any(p.startswith(f"{module}/") for p in ctx.by_path)
    if not is_file and not is_dir:
        hint = ctx.suggest(module)
        extra = f" Did you mean: {', '.join(hint)}?" if hint else ""
        return ToolResult(False, f"No file or directory '{module}'.{extra}", error_type="not_found")

    def inside(path: str) -> bool:
        return path == module or path.startswith(f"{module}/")

    if is_file:
        outgoing = list(collection(EDGES).find({"repo_id": repo, "src": module}))
        directory = posixpath.dirname(module) or "."
        incoming = list(
            collection(EDGES).find({"repo_id": repo, "dst": {"$in": [module, directory]}})
        )
    else:
        regex = {"$regex": f"^{re.escape(module)}/"}
        outgoing = [
            e for e in collection(EDGES).find({"repo_id": repo, "src": regex})
            if e["external"] or not inside(e["dst"])
        ]  # fmt: skip
        incoming = [
            e for e in collection(EDGES).find({"repo_id": repo, "external": False, "dst": regex})
            if not inside(e["src"])
        ]  # fmt: skip
        incoming += [
            e for e in collection(EDGES).find({"repo_id": repo, "external": False, "dst": module})
            if not inside(e["src"])
        ]  # fmt: skip

    internal = sorted({e["dst"] for e in outgoing if not e["external"]})
    external = sorted({e["dst"] for e in outgoing if e["external"]})
    users = sorted({e["src"] for e in incoming if not e["external"] and e["src"] != module})
    parts = [f"Dependencies of {module}{'' if is_file else '/'}:"]
    parts.append("Imports (in this repo): " + (", ".join(internal[:60]) or "none"))
    parts.append("External packages: " + (", ".join(external[:60]) or "none"))
    parts.append(f"Imported by ({len(users)}): " + (", ".join(users[:60]) or "nothing"))
    return ToolResult(True, wrap("get_dependencies", "\n".join(parts), module))


class NoArgs(ToolArgs):
    pass


def get_repo_metadata(ctx: ToolContext, _args: NoArgs) -> ToolResult:
    repo = ctx.repository
    paths = list(ctx.by_path)
    structure = top_level_structure(paths)
    data = {
        "name": repo.full_name,
        "description": repo.description,
        "default_branch": repo.default_branch,
        "commit": repo.commit_sha[:12],
        "languages_percent": repo.languages,
        "frameworks_and_tools": repo.frameworks,
        "stats": {k: v for k, v in repo.stats.items() if k != "skipped"},
        "manifests": repo.detection.get("manifests", [])[:20],
        "scripts": repo.detection.get("scripts", {}),
        "top_level": [f"{name} ({count} files)" for name, count in structure],
        "entry_point_candidates": entry_point_candidates(paths),
    }
    return ToolResult(True, wrap("get_repo_metadata", json.dumps(data, indent=1)))


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            "list_directory",
            "List files and sub-directories of a directory in the repository.",
            ListDirectoryArgs,
            list_directory,
        ),
        Tool(
            "read_file",
            f"Read a file or line range with line numbers (max {MAX_READ_LINES} lines per call).",
            ReadFileArgs,
            read_file,
        ),
        Tool(
            "search_code",
            "Semantic + keyword search over the codebase. Use natural language or identifiers.",
            SearchCodeArgs,
            search_code,
        ),
        Tool(
            "grep",
            "Find lines matching a regular expression (RE2 syntax), optionally within a path glob.",
            GrepArgs,
            grep,
        ),
        Tool(
            "get_symbol",
            "Find where a function, class or method is defined ('Class.method' also works).",
            GetSymbolArgs,
            get_symbol,
        ),
        Tool(
            "get_dependencies",
            "Show what a file or directory imports and what imports it.",
            GetDependenciesArgs,
            get_dependencies,
        ),
        Tool(
            "get_repo_metadata",
            "Repo facts: languages, frameworks, manifests, scripts, layout and entry points.",
            NoArgs,
            get_repo_metadata,
        ),
    ]
}


def tool_schemas(names: list[str] | None = None) -> list[dict[str, Any]]:
    return [TOOLS[name].schema() for name in (names or list(TOOLS))]


def _format_validation_error(exc: ValidationError) -> str:
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "arguments"
        problems.append(f"{location}: {error['msg']}")
    return "; ".join(problems)


def execute_tool(name: str, arguments: str | dict[str, Any] | None, ctx: ToolContext) -> ToolResult:
    """Validate and run a tool call. Never raises: errors come back as ``ok=False`` results
    whose message is written so the model can repair its call."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolResult(
            False,
            f"Unknown tool '{name}'. Available tools: {', '.join(TOOLS)}.",
            error_type="unknown_tool",
        )
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return ToolResult(
                False,
                f"Arguments for {name} must be a JSON object ({exc.msg} at position {exc.pos}).",
                error_type="invalid_json",
            )
    if not isinstance(arguments, dict):
        return ToolResult(
            False, f"Arguments for {name} must be a JSON object.", error_type="invalid_json"
        )
    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolResult(
            False,
            f"Invalid arguments for {name}: {_format_validation_error(exc)}. "
            f"Expected schema: {json.dumps(tool.schema()['function']['parameters'])}",
            error_type="invalid_arguments",
        )
    try:
        return tool.handler(ctx, args)
    except Exception as exc:  # a tool bug must not crash the agent loop
        return ToolResult(False, f"{name} failed: {type(exc).__name__}", error_type="tool_error")
