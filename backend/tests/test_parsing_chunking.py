from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from apps.ingestion.chunking import MAX_CHUNK_CHARS, MAX_CHUNK_LINES, chunk_file
from apps.ingestion.depgraph import build_edges
from apps.ingestion.parsing import ParsedFile, parse_source
from tests.conftest_fixtures import FIXTURES


def parse_fixture(repo: str, rel: str, language: str) -> ParsedFile:
    parsed = parse_source(language, (FIXTURES / repo / rel).read_text(encoding="utf-8"))
    assert parsed is not None
    return parsed


def names(parsed: ParsedFile) -> set[tuple[str, str]]:
    return {(s.kind, s.qualified_name) for s in parsed.symbols}


# --- parsing -----------------------------------------------------------------------------


def test_python_symbols_and_imports() -> None:
    parsed = parse_fixture("py_app", "app/services.py", "python")
    assert names(parsed) >= {
        ("class", "User"),
        ("class", "UserService"),
        ("method", "UserService.get_user"),
        ("method", "UserService.list_users"),
    }
    user = next(s for s in parsed.symbols if s.name == "User")
    assert user.start_line == 4  # includes the @dataclass decorator
    main = parse_fixture("py_app", "app/main.py", "python")
    modules = {(i.module, i.level) for i in main.imports}
    assert modules == {("flask", 0), ("app.routes", 0), ("config", 1)}


def test_typescript_symbols_and_imports() -> None:
    parsed = parse_fixture("js_app", "src/services/users.ts", "typescript")
    assert names(parsed) >= {
        ("interface", "User"),
        ("class", "UserStore"),
        ("method", "UserStore.find"),
        ("function", "getUser"),
    }
    server = parse_fixture("js_app", "src/server.ts", "typescript")
    assert {i.module for i in server.imports} == {"express", "./routes/index"}


def test_tsx_arrow_component() -> None:
    parsed = parse_fixture("js_app", "src/components/Button.tsx", "tsx")
    assert ("function", "Button") in names(parsed)
    assert ("type", "Props") in names(parsed)


def test_go_symbols_package_and_imports() -> None:
    parsed = parse_fixture("go_app", "internal/store/store.go", "go")
    assert parsed.package == "store"
    assert names(parsed) >= {
        ("struct", "Store"),
        ("function", "New"),
        ("method", "Store.Get"),
        ("method", "Store.Put"),
    }
    main = parse_fixture("go_app", "main.go", "go")
    assert {i.module for i in main.imports} == {"fmt", "github.com/acme/tool/internal/store"}


def test_java_symbols_package_and_imports() -> None:
    parsed = parse_fixture(
        "java_app", "src/main/java/com/example/demo/DemoApplication.java", "java"
    )
    assert parsed.package == "com.example.demo"
    assert names(parsed) >= {
        ("class", "DemoApplication"),
        ("method", "DemoApplication.main"),
        ("method", "DemoApplication.greet"),
    }
    assert "com.example.demo.service.GreetingService" in {i.module for i in parsed.imports}


def test_unparsed_language_returns_none() -> None:
    assert parse_source("ruby", "puts 1") is None


def test_syntax_errors_do_not_crash() -> None:
    parsed = parse_source("python", "def broken(:\n    pass\nclass Ok:\n    pass\n")
    assert parsed is not None
    assert parsed.has_errors
    assert ("class", "Ok") in names(parsed)


# --- chunking ----------------------------------------------------------------------------


def test_chunks_follow_symbols_and_cover_module_code() -> None:
    text = (FIXTURES / "py_app/app/main.py").read_text(encoding="utf-8")
    parsed = parse_source("python", text)
    assert parsed is not None
    chunks = chunk_file("app/main.py", "python", text, parsed.symbols)

    by_symbol = {c.symbol: c for c in chunks}
    assert by_symbol["create_app"].kind == "function"
    assert by_symbol["create_app"].content.startswith("def create_app")
    assert by_symbol["cli"].start_line < by_symbol["cli"].end_line
    module_chunks = [c for c in chunks if c.kind == "module"]
    assert any("from flask import Flask" in c.content for c in module_chunks)
    assert any('if __name__ == "__main__"' in c.content for c in module_chunks)
    for chunk in chunks:
        lines = text.splitlines()[chunk.start_line - 1 : chunk.end_line]
        assert chunk.content == "\n".join(lines)


def test_large_class_splits_into_methods() -> None:
    methods = "\n".join(
        f"    def m{i}(self):\n" + "        x = 1\n" * 20 + "        return x\n" for i in range(10)
    )
    text = f"class Big:\n    '''doc'''\n{methods}"
    parsed = parse_source("python", text)
    assert parsed is not None
    chunks = chunk_file("big.py", "python", text, parsed.symbols)

    assert any(c.symbol == "Big" and c.start_line == 1 for c in chunks)  # header
    assert {f"Big.m{i}" for i in range(10)} <= {c.symbol for c in chunks}
    assert all(c.end_line - c.start_line + 1 <= MAX_CHUNK_LINES for c in chunks)


def test_huge_function_is_split_with_overlap() -> None:
    body = "".join(f"    v{i} = {i}\n" for i in range(400))
    text = f"def huge():\n{body}    return 1\n"
    parsed = parse_source("python", text)
    assert parsed is not None
    chunks = chunk_file("huge.py", "python", text, parsed.symbols)

    parts = [c for c in chunks if (c.symbol or "").startswith("huge (part")]
    assert len(parts) >= 4
    for first, second in itertools.pairwise(parts):
        assert second.start_line <= first.end_line  # overlap
    assert all(len(c.content) <= MAX_CHUNK_CHARS for c in chunks)
    assert parts[-1].end_line == len(text.splitlines())


def test_line_window_fallback_for_unparsed_languages() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 201))
    chunks = chunk_file("notes.txt", "text", text, None)
    assert [c.kind for c in chunks] == ["file"] * len(chunks)
    assert chunks[0].start_line == 1 and chunks[0].end_line == 80
    assert chunks[1].start_line == 66  # 15-line overlap
    assert chunks[-1].end_line == 200


def test_long_lines_respect_char_cap() -> None:
    text = "\n".join("x" * 2000 for _ in range(10))
    chunks = chunk_file("data.txt", "text", text, None)
    assert all(len(c.content) <= MAX_CHUNK_CHARS for c in chunks)
    assert chunks[-1].end_line == 10


def test_empty_file_has_no_chunks() -> None:
    assert chunk_file("e.py", "python", "", []) == []


# --- dependency graph --------------------------------------------------------------------


def parse_repo(repo: str, language_by_suffix: dict[str, str]) -> tuple[dict, set[str]]:
    root = FIXTURES / repo
    paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    parsed = {}
    for path in paths:
        language = language_by_suffix.get(Path(path).suffix)
        if language:
            parsed[path] = parse_source(language, (root / path).read_text(encoding="utf-8"))
    return parsed, paths


def internal(edges: list) -> set[tuple[str, str]]:
    return {(e.src, e.dst) for e in edges if not e.external}


def test_python_import_resolution() -> None:
    parsed, paths = parse_repo("py_app", {".py": "python"})
    edges = build_edges(parsed, paths)
    assert internal(edges) >= {
        ("app/main.py", "app/routes.py"),
        ("app/main.py", "app/config.py"),
        ("app/routes.py", "app/services.py"),
        ("tests/test_services.py", "app/services.py"),
    }
    assert ("app/main.py", "flask") in {(e.src, e.dst) for e in edges if e.external}


def test_typescript_import_resolution() -> None:
    parsed, paths = parse_repo("js_app", {".ts": "typescript", ".tsx": "tsx"})
    edges = build_edges(parsed, paths)
    assert internal(edges) == {
        ("src/index.ts", "src/server.ts"),
        ("src/server.ts", "src/routes/index.ts"),
        ("src/routes/index.ts", "src/services/users.ts"),
    }
    assert ("src/server.ts", "express") in {(e.src, e.dst) for e in edges if e.external}


def test_go_import_resolution_uses_module_path() -> None:
    parsed, paths = parse_repo("go_app", {".go": "go"})
    edges = build_edges(parsed, paths, go_module="github.com/acme/tool")
    internal_edges = [e for e in edges if not e.external]
    assert [(e.src, e.dst, e.dst_is_dir) for e in internal_edges] == [
        ("main.go", "internal/store", True)
    ]


def test_java_import_resolution() -> None:
    parsed, paths = parse_repo("java_app", {".java": "java"})
    edges = build_edges(parsed, paths)
    assert (
        "src/main/java/com/example/demo/DemoApplication.java",
        "src/main/java/com/example/demo/service/GreetingService.java",
    ) in internal(edges)


@pytest.mark.parametrize(
    ("src", "module", "names", "level", "expected"),
    [
        ("pkg/a.py", "", ("util",), 1, "pkg/util.py"),
        ("pkg/sub/a.py", "core", (), 2, "pkg/core.py"),
        ("pkg/a.py", "", ("x",), 1, "pkg/__init__.py"),
    ],
)
def test_python_relative_imports(
    src: str, module: str, names: tuple[str, ...], level: int, expected: str
) -> None:
    from apps.ingestion.parsing import ImportRef

    paths = {"pkg/__init__.py", "pkg/util.py", "pkg/core.py", "pkg/sub/a.py", "pkg/a.py"}
    parsed = {src: ParsedFile("python", imports=[ImportRef(module, 1, level, names)])}
    assert internal(build_edges(parsed, paths)) == {(src, expected)}
