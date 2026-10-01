"""Architecture graph repair + Mermaid rendering, and Guided Tour enforcement (no MongoDB)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agents.citations import FileIndex, module_of, repair_architecture, repair_tour
from apps.agents.digest import dependency_summary
from apps.agents.mermaid import node_id, render_mermaid, sanitize_label
from apps.agents.schemas import FLOW_TRACE_REQUIRED, Architecture, Tour
from apps.agents.structured import (
    OutputRejectedError,
    StructuredOutputError,
    generate_structured,
)
from tests.fakes.llm import ScriptedLLM, reply

FILES = [
    {"path": "src/api/routes.py", "lines": 80},
    {"path": "src/api/auth.py", "lines": 40},
    {"path": "src/core/orders.py", "lines": 200},
    {"path": "src/db/models.py", "lines": 120},
    {"path": "main.py", "lines": 20},
]
SYMBOLS = {"src/core/orders.py": [{"name": "place_order", "start_line": 30, "end_line": 64}]}
EDGES = [
    ("main.py", "src/api/routes.py"),
    ("src/api/routes.py", "src/core/orders.py"),
    ("src/api/auth.py", "src/core/orders.py"),
    ("src/core/orders.py", "src/db/models.py"),
    ("src/api/routes.py", "src/api/auth.py"),  # inside one module: ignored
]


@pytest.fixture
def index() -> FileIndex:
    return FileIndex(FILES, SYMBOLS, edges=EDGES)


def module(id_: str, paths: list[str], kind: str = "core", name: str | None = None) -> dict:
    return {"id": id_, "name": name or id_.title(), "kind": kind, "paths": paths,
            "description": "Does things"}  # fmt: skip


# --- architecture ---------------------------------------------------------------------------


def test_module_of_prefers_files_then_longest_directory() -> None:
    modules = [module("src", ["src/"]), module("api", ["src/api/"]), module("main", ["main.py"])]
    assert module_of("src/api/routes.py", modules) == "api"
    assert module_of("src/db/models.py", modules) == "src"
    assert module_of("main.py", modules) == "main"
    assert module_of("README.md", modules) is None


def test_repair_architecture_verifies_paths_ids_and_edges(index: FileIndex) -> None:
    data = {
        "modules": [
            module("API Layer", ["src/api", "./src/api/routes.py", "src/api/missing.py"]),
            module("core", ["core/"]),  # suffix-only dir: not resolvable -> dropped module
            module("orders", ["src/core/"], name="Order logic"),
            module("db", ["src/db/models.py"], kind="data"),
            module("stripe", [], kind="external", name="Stripe"),
            module("orders", ["main.py"], kind="entry"),  # duplicate id gets a suffix
        ],
        "edges": [
            {"source": "api layer", "target": "Order logic", "label": "calls"},
            {"source": "orders", "target": "stripe", "label": "charges"},
            {"source": "orders", "target": "nowhere", "label": "x"},
            {"source": "db", "target": "db", "label": "self"},
            {"source": "API Layer", "target": "orders", "label": "duplicate"},
        ],
    }
    report = repair_architecture(data, index)

    ids = [m["id"] for m in data["modules"]]
    assert ids == ["api_layer", "orders", "db", "stripe", "orders_2"]
    assert data["modules"][0]["paths"] == ["src/api/", "src/api/routes.py"]
    assert report.dropped_paths == ["src/api/missing.py", "core/"]

    edges = {(e["source"], e["target"]): e for e in data["edges"]}
    assert edges["api_layer", "orders"] == {
        "source": "api_layer", "target": "orders", "label": "calls", "derived": False,
        "imports": 2,
    }  # fmt: skip
    assert edges["orders", "stripe"]["imports"] == 0
    # Proven by the import graph but missing from the model's answer:
    assert edges["orders", "db"]["derived"] and edges["orders", "db"]["imports"] == 1
    assert edges["orders_2", "api_layer"]["derived"]
    assert len(edges) == 4


def test_derived_edges_are_capped(index: FileIndex) -> None:
    data = {
        "modules": [module(name, [path]) for name, path in
                    [("m", "main.py"), ("r", "src/api/routes.py"), ("a", "src/api/auth.py"),
                     ("o", "src/core/orders.py"), ("d", "src/db/models.py")]],
        "edges": [],
    }  # fmt: skip
    repair_architecture(data, index, max_edges=2)
    assert len(data["edges"]) == 2 and all(e["derived"] for e in data["edges"])


def test_mermaid_is_deterministic_and_sanitised() -> None:
    data = {
        "modules": [
            module("end", ["main.py"], kind="entry", name='CLI "main" <script>'),
            module("db", ["src/db/"], kind="data", name="Models [ORM] {x} | #1; `a` & b"),
            module("pay", [], kind="external", name="Payments"),
        ],
        "edges": [
            {"source": "end", "target": "db", "label": "click href javascript:alert(1)"},
            {"source": "db", "target": "pay", "label": None},
            {"source": "end", "target": "pay", "derived": True, "imports": 3},
            {"source": "end", "target": "ghost", "label": "dropped"},
        ],
    }
    source = render_mermaid(data)
    assert source == render_mermaid(data)
    assert source.splitlines() == [
        "flowchart LR",
        "    m_end([\"CLI 'main' script\"])",
        '    m_db[("Models ORM x 1 a b")]',
        '    m_pay{{"Payments"}}',
        '    m_end -->|"click href javascript:alert(1)"| m_db',
        "    m_db --> m_pay",
        '    m_end -.->|"3 imports"| m_pay',
        "    classDef data fill:#fef3c7,stroke:#d97706,color:#451a03",
        "    classDef entry fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b",
        "    classDef external fill:#f5f5f4,stroke:#78716c,color:#1c1917,stroke-dasharray:4 3",
        "    class m_db data",
        "    class m_end entry",
        "    class m_pay external",
    ]


def test_sanitize_label() -> None:
    assert sanitize_label('a"b') == "a'b"
    assert sanitize_label("x\n\ty") == "x y"
    assert sanitize_label("a" * 60, limit=10) == "a" * 9 + "…"
    assert sanitize_label(None) == ""
    assert node_id("Weird-Id!") == "m_weird_id_"


def test_dependency_summary_groups_by_directory_or_falls_back_to_files() -> None:
    summary = dependency_summary(EDGES)
    assert "src/api/ -> src/core/ (2 imports)" in summary
    assert "(root files) -> src/api/ (1 import)" in summary
    flat = dependency_summary([("lib/a.js", "lib/b.js"), ("lib/a.js", "lib/c.js")])
    assert flat.splitlines() == ["  - lib/a.js -> lib/b.js (1 import)",
                                 "  - lib/a.js -> lib/c.js (1 import)"]  # fmt: skip
    assert dependency_summary([]) == "(no internal imports detected)"


def test_architecture_schema_coerces_unknown_kinds() -> None:
    arch = Architecture.model_validate(
        {"summary": "A long enough summary of the system.",
         "modules": [module("a", ["x/"], kind="Data Store"), module("b", ["y/"], kind="UI")]}
    )  # fmt: skip
    assert [m.kind for m in arch.modules] == ["other", "ui"]


# --- tour -----------------------------------------------------------------------------------


def step(kind: str = "core_logic", path: str = "main.py", **extra: Any) -> dict[str, Any]:
    return {"title": "A step", "kind": kind, "path": path,
            "explanation": "Explains what happens in this part of the code.", **extra}  # fmt: skip


def tour(*steps: dict[str, Any]) -> dict[str, Any]:
    return {"intro": "A tour through placing an order.", "steps": list(steps)}


def test_tour_schema_requires_a_flow_trace() -> None:
    with pytest.raises(ValueError, match="flow_trace"):
        Tour.model_validate(tour(step(), step(), step()))
    assert Tour.model_validate(tour(step(), step("flow-trace"), step())).steps[1].kind == (
        "flow_trace"
    )


def test_missing_flow_trace_is_repaired_by_reprompting() -> None:
    llm = ScriptedLLM(
        reply(json.dumps(tour(step(), step(), step()))),
        reply(json.dumps(tour(step("entry_point"), step("flow_trace"), step("flow_trace")))),
    )
    result = generate_structured(llm, [{"role": "user", "content": "Section: tour"}], Tour)
    assert [s.kind for s in result.steps] == ["entry_point", "flow_trace", "flow_trace"]
    feedback = llm.requests[1]["messages"][-1]["content"]
    assert FLOW_TRACE_REQUIRED in feedback


def test_rejected_output_is_sent_back_to_the_model() -> None:
    def accept(output: Tour) -> None:
        if output.steps[0].path == "ghost.py":
            raise OutputRejectedError("ghost.py does not exist")

    llm = ScriptedLLM(
        reply(json.dumps(tour(step("flow_trace", "ghost.py"), step(), step()))),
        reply(json.dumps(tour(step("flow_trace"), step(), step()))),
    )
    result = generate_structured(llm, [{"role": "user", "content": "x"}], Tour, accept=accept)
    assert result.steps[0].path == "main.py"
    assert "- ghost.py does not exist" in llm.requests[1]["messages"][-1]["content"]

    ghostly = tour(step("flow_trace", "ghost.py"), step(), step())
    always = ScriptedLLM(*[reply(json.dumps(ghostly))] * 3)
    with pytest.raises(StructuredOutputError, match=r"ghost.py does not exist"):
        generate_structured(always, [{"role": "user", "content": "x"}], Tour, accept=accept)


def test_repair_tour(index: FileIndex) -> None:
    data = tour(
        step("entry_point", "./main.py:1-1"),
        step("flow_trace", "orders.py", symbol="place_order()", start_line=500, end_line=510),
        step("flow_trace", "src/core/orders.py", symbol="place_order"),  # duplicate stop
        step("core_logic", "src/ghost.py"),
        step("data_model", "src/db/models.py", start_line=10, end_line=30),
    )
    report = repair_tour(data, index)
    stops = [(s["path"], s["start_line"], s["end_line"]) for s in data["steps"]]
    assert stops == [
        ("main.py", None, None),  # filler 1-1 range dropped
        ("src/core/orders.py", 30, 64),  # resolved by basename, lines from the symbol
        ("src/db/models.py", 10, 30),
    ]
    assert report.dropped_paths == ["src/ghost.py"]
