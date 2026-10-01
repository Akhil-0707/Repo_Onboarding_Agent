"""Citation parsing, validation and stripping in chat answers (no MongoDB)."""

from __future__ import annotations

import pytest

from apps.agents.citations import FileIndex
from apps.chat.citations import format_citation, process_answer

FILES = [
    {"path": "app/main.py", "lines": 30},
    {"path": "app/services.py", "lines": 20},
    {"path": "Dockerfile", "lines": 12},
    {"path": "README.md", "lines": 40},
]


@pytest.fixture
def index() -> FileIndex:
    return FileIndex(FILES, repo_name="acme/py_app")


def test_real_citations_are_normalised_and_collected(index: FileIndex) -> None:
    refs = process_answer(
        "Startup is in [./app/main.py:8-11]; users in [services.py#L10-L20] and "
        "[app/services.py:5-999]. Again [app/main.py:8-11].",
        index,
    )
    assert refs.text == (
        "Startup is in [app/main.py:8-11]; users in [app/services.py:10-20] and "
        "[app/services.py:5-20]. Again [app/main.py:8-11]."
    )
    assert refs.citations == [
        {"path": "app/main.py", "start_line": 8, "end_line": 11},
        {"path": "app/services.py", "start_line": 10, "end_line": 20},
        {"path": "app/services.py", "start_line": 5, "end_line": 20},
    ]
    assert refs.stripped == []


def test_invented_files_are_stripped_from_the_text(index: FileIndex) -> None:
    refs = process_answer(
        "Config is loaded in [app/settings.py:1-9]. Users are cached ([app/cache.py]) "
        "by [app/services.py:10-12].",
        index,
    )
    assert refs.text == "Config is loaded in. Users are cached by [app/services.py:10-12]."
    assert refs.stripped == ["[app/settings.py:1-9]", "[app/cache.py]"]
    assert [c["path"] for c in refs.citations] == ["app/services.py"]


def test_ordinary_brackets_links_and_code_are_left_alone(index: FileIndex) -> None:
    text = (
        "Ratio [0.5], flag [optional], see [the docs](https://example.com/a.md), "
        "call `obj.method()` or `1.5`.\n"
        "```python\nload('[app/ghost.py:1]')  # [app/main.py:1-2]\n```\n"
        "Plain words."
    )
    refs = process_answer(text, index)
    assert refs.text == text
    assert refs.citations == [] and refs.stripped == []


def test_backticked_paths_become_citations_when_real(index: FileIndex) -> None:
    refs = process_answer("Edit `app/main.py:3` and `Dockerfile`; `ghost.py` is not real.", index)
    assert refs.text == "Edit [app/main.py:3] and `Dockerfile`; `ghost.py` is not real."
    assert refs.citations == [{"path": "app/main.py", "start_line": 3, "end_line": 3}]


def test_files_without_extension_resolve_inside_brackets(index: FileIndex) -> None:
    refs = process_answer("Built by [Dockerfile:2-5] (see [README.md]).", index)
    assert refs.text == "Built by [Dockerfile:2-5] (see [README.md])."
    assert len(refs.citations) == 2


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("a.py", None, None), "[a.py]"),
        (("a.py", 3, 3), "[a.py:3]"),
        (("a.py", 3, None), "[a.py:3]"),
        (("a.py", 3, 9), "[a.py:3-9]"),
    ],
)
def test_format_citation(args: tuple, expected: str) -> None:
    assert format_citation(*args) == expected
