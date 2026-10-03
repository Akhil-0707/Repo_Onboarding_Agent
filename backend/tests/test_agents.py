"""Agent building blocks with a scripted model (no database)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agents import loop as loop_module
from apps.agents.citations import FileIndex, repair_glossary, repair_overview, repair_start_here
from apps.agents.loop import (
    FINAL_ANSWER_NUDGE,
    LOOK_FIRST_NUDGE,
    REPAIR_EXHAUSTED_NUDGE,
    AgentLoop,
    BudgetExceededError,
    TokenBudget,
    TokenGate,
    compact_messages,
)
from apps.agents.schemas import StartHere
from apps.agents.structured import StructuredOutputError, extract_json, generate_structured
from apps.agents.tools import Citation, ToolResult
from apps.llm.errors import LLMRequestError, ModelOfflineError
from apps.llm.toolcall_parse import parse_text_tool_calls, strip_tool_call_markup
from tests.fakes.llm import ScriptedLLM, call, reply

KNOWN = {"read_file", "search_code", "get_repo_metadata"}


# --- text tool-call fallback ---------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        '<tool_call>\n{"name": "read_file", "arguments": {"path": "a.py"}}\n</tool_call>',
        'Let me check.\n```json\n{"name": "read_file", "arguments": {"path": "a.py"}}\n```',
        '{"name": "read_file", "parameters": {"path": "a.py"}}',
        '{"function": {"name": "read_file", "arguments": "{\\"path\\": \\"a.py\\"}"}}',
        '<tool_call>{"name": "read_file", "arguments": {"path": "a.py"}}',  # unterminated tag
    ],
)
def test_parses_text_tool_calls(content: str) -> None:
    calls = parse_text_tool_calls(content, KNOWN)
    assert [(c.name, json.loads(c.arguments)) for c in calls] == [("read_file", {"path": "a.py"})]


def test_parses_multiple_calls_and_ignores_unknown_names() -> None:
    content = (
        '<tool_call>{"name": "read_file", "arguments": {"path": "a"}}</tool_call>'
        '<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>'
        '<tool_call>{"name": "search_code", "arguments": {"query": "x"}}</tool_call>'
    )
    assert [c.name for c in parse_text_tool_calls(content, KNOWN)] == ["read_file", "search_code"]


def test_plain_json_answers_are_not_tool_calls() -> None:
    assert parse_text_tool_calls('{"summary": "hello", "name": "Overview"}', KNOWN) == []
    assert parse_text_tool_calls("just prose", KNOWN) == []
    assert strip_tool_call_markup("Answer <tool_call>{}</tool_call>") == "Answer"


# --- agent loop ---------------------------------------------------------------------------


class _Ctx:
    repo_id = "r"


@pytest.fixture
def tool_runs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Replace real tool execution: valid args succeed, anything else fails like the real
    validator does."""
    runs: list[tuple[str, Any]] = []

    def fake_execute(name: str, arguments: Any, ctx: Any) -> ToolResult:
        runs.append((name, arguments))
        try:
            args = json.loads(arguments)
        except (TypeError, json.JSONDecodeError):
            return ToolResult(False, "Arguments must be a JSON object.", error_type="invalid_json")
        if name == "read_file" and "path" not in args:
            return ToolResult(
                False, "Invalid arguments: path: Field required", error_type="invalid_arguments"
            )
        return ToolResult(
            True, f"<repo_content>{name} ok</repo_content>", [Citation(args.get("path", "x"), 1, 2)]
        )

    monkeypatch.setattr(loop_module, "execute_tool", fake_execute)
    return runs


def make_loop(llm: ScriptedLLM, **kwargs: Any) -> AgentLoop:
    return AgentLoop(llm, _Ctx(), tools=sorted(KNOWN), **kwargs)  # type: ignore[arg-type]


def test_tool_call_then_answer(tool_runs: list) -> None:
    llm = ScriptedLLM(
        reply(tool_calls=[call("read_file", {"path": "a.py"})]), reply("Final notes.")
    )
    steps: list[int] = []
    result = make_loop(llm, on_step=lambda m: steps.append(len(m))).run(
        [{"role": "user", "content": "go"}]
    )

    assert result.final_text == "Final notes."
    assert result.stopped_reason == "answered"
    assert [e.summary for e in result.tool_events] == ["Reading 'a.py'"]
    assert result.citations == [Citation("a.py", 1, 2)]
    assert result.usage.calls == 2 and result.usage.prompt_tokens == 200
    second = llm.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert second[-1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "<repo_content>read_file ok</repo_content>",
    }
    assert steps  # checkpoint hook fired
    assert llm.requests[0]["tools"]  # tools offered


def test_streaming_mode_forwards_answer_tokens_only(tool_runs: list) -> None:
    llm = ScriptedLLM(
        reply(tool_calls=[call("read_file", {"path": "a.py"})]),
        reply('<tool_call>{"name": "search_code", "arguments": {"query": "x"}}</tool_call>'),
        reply("Auth lives in auth.py."),
    )
    tokens: list[str] = []
    result = make_loop(llm, on_token=tokens.append).run([{"role": "user", "content": "go"}])
    assert [name for name, _ in tool_runs] == ["read_file", "search_code"]
    assert "".join(tokens).strip() == "Auth lives in auth.py."  # tool-call text never leaks
    assert result.final_text == "Auth lives in auth.py."
    assert result.usage.calls == 3


def test_answers_without_looking_are_sent_back_once(tool_runs: list) -> None:
    llm = ScriptedLLM(
        reply("From memory: it is in auth.py."),
        reply("Let me check.", tool_calls=[call("read_file", {"path": "auth.py"})]),
        reply("Auth lives in auth.py."),
    )
    tokens: list[str] = []
    retracts: list[int] = []
    loop = make_loop(
        llm,
        on_token=tokens.append,
        on_retract=lambda: retracts.append(len(tokens)),
        require_tool_use=True,
    )
    result = loop.run([{"role": "user", "content": "Where is auth?"}])
    assert result.final_text == "Auth lives in auth.py."
    assert llm.requests[1]["messages"][-1]["content"] == LOOK_FIRST_NUDGE
    assert all("From memory" not in str(m["content"]) for m in llm.requests[1]["messages"])
    # The discarded answer and the tool-call preamble were both retracted.
    assert len(retracts) == 2
    assert "".join(tokens[retracts[1] :]).strip() == "Auth lives in auth.py."

    stubborn = ScriptedLLM(reply("No tools needed."), reply("Still no tools."))
    result = make_loop(stubborn, on_token=tokens.append, require_tool_use=True).run(
        [{"role": "user", "content": "Thanks!"}]
    )
    assert result.final_text == "Still no tools."  # nudged once, then accepted


@pytest.mark.parametrize(
    ("chunks", "shown"),
    [
        (["Hello", " world"], "Hello world"),
        (["  <tool", "_call>{}", "</tool_call>"], ""),
        (['{"na', 'me": "grep"}'], ""),
        (["```json\n", '{"name": 1}'], ""),
        (["```py", "thon\nprint(1)\n```"], "```python\nprint(1)\n```"),
        (["{", "x}"], "{x}"),
        (["<", "b>bold"], "<b>bold"),
    ],
)
def test_token_gate(chunks: list[str], shown: str) -> None:
    out: list[str] = []
    gate = TokenGate(out.append)
    for chunk in chunks:
        gate.feed(chunk)
    assert "".join(out) == shown


def test_text_tool_call_fallback(tool_runs: list) -> None:
    llm = ScriptedLLM(
        reply('<tool_call>{"name": "search_code", "arguments": {"query": "auth"}}</tool_call>'),
        reply("Auth lives in auth.py."),
    )
    result = make_loop(llm).run([{"role": "user", "content": "go"}])
    assert tool_runs == [("search_code", '{"query": "auth"}')]
    assert result.final_text == "Auth lives in auth.py."


def test_malformed_call_is_repaired(tool_runs: list) -> None:
    llm = ScriptedLLM(
        reply(tool_calls=[call("read_file", '{"path": ')]),  # broken JSON
        reply(tool_calls=[call("read_file", {"start_line": 3})]),  # missing field
        reply(tool_calls=[call("read_file", {"path": "a.py"})]),  # fixed
        reply("Done."),
    )
    result = make_loop(llm).run([{"role": "user", "content": "go"}])
    assert result.final_text == "Done."
    tool_messages = [m for m in llm.requests[2]["messages"] if m["role"] == "tool"]
    assert "JSON object" in tool_messages[0]["content"]
    assert "Field required" in tool_messages[1]["content"]
    assert [e.ok for e in result.tool_events] == [False, False, True]


def test_repairs_exhausted_forces_an_answer(tool_runs: list) -> None:
    bad = reply(tool_calls=[call("read_file", "{nope")])
    llm = ScriptedLLM(bad, bad, bad, reply("Best effort answer."))
    result = make_loop(llm, max_repairs=2).run([{"role": "user", "content": "go"}])
    assert result.stopped_reason == "repairs_exhausted"
    assert result.final_text == "Best effort answer."
    final_request = llm.requests[-1]
    assert final_request["tools"] is None
    assert final_request["messages"][-1]["content"] == REPAIR_EXHAUSTED_NUDGE


def test_iteration_cap_forces_a_final_answer_without_tools(tool_runs: list) -> None:
    looping = reply(tool_calls=[call("get_repo_metadata", {})])
    llm = ScriptedLLM(looping, looping, reply("Out of steps."))
    result = make_loop(llm, max_iterations=2).run([{"role": "user", "content": "go"}])
    assert result.stopped_reason == "max_iterations"
    assert result.final_text == "Out of steps."
    assert llm.requests[-1]["tools"] is None
    assert llm.requests[-1]["messages"][-1]["content"] == FINAL_ANSWER_NUDGE


def test_empty_reply_is_nudged_once(tool_runs: list) -> None:
    llm = ScriptedLLM(reply(""), reply("Now with content."))
    result = make_loop(llm).run([{"role": "user", "content": "go"}])
    assert result.final_text == "Now with content."


def test_budget(tool_runs: list) -> None:
    llm = ScriptedLLM(reply("x"))
    with pytest.raises(BudgetExceededError):
        make_loop(llm, budget=TokenBudget(limit=100, used=100)).run(
            [{"role": "user", "content": "go"}]
        )

    budget = TokenBudget(limit=10_000)
    llm = ScriptedLLM(
        reply(tool_calls=[call("get_repo_metadata", {})], tokens=(400, 100)), reply("Short.")
    )
    make_loop(llm, budget=budget).run([{"role": "user", "content": "go"}])
    assert budget.used == 650  # both calls counted

    # Nearly exhausted: skip research and answer straight away, without tools.
    llm = ScriptedLLM(reply("Answer from the digest only."))
    result = make_loop(llm, budget=TokenBudget(limit=10_000, used=9_000)).run(
        [{"role": "user", "content": "go"}]
    )
    assert result.stopped_reason == "budget" and llm.requests[0]["tools"] is None


def test_model_offline_propagates_for_checkpointing(tool_runs: list) -> None:
    llm = ScriptedLLM(reply(tool_calls=[call("get_repo_metadata", {})]), ModelOfflineError("gone"))
    saved: list[list] = []
    with pytest.raises(ModelOfflineError):
        make_loop(llm, on_step=lambda m: saved.append(list(m))).run(
            [{"role": "user", "content": "go"}]
        )
    assert saved and saved[-1][-1]["role"] == "tool"  # progress up to the failure is saved


def test_resume_from_checkpointed_messages(tool_runs: list) -> None:
    checkpoint = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [call("get_repo_metadata", {}).to_message_dict()],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "meta"},
    ]
    llm = ScriptedLLM(reply("Resumed answer."))
    result = make_loop(llm, max_iterations=6).run(checkpoint, start_iteration=1)
    assert result.final_text == "Resumed answer."
    assert llm.requests[0]["messages"][-1]["content"] == "meta"


def test_compaction_keeps_recent_tool_output() -> None:
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    for i in range(6):
        messages.append({"role": "tool", "tool_call_id": str(i), "content": f"{i}" * 3000})
    compacted = compact_messages(messages, max_chars=12_000, keep_recent=3)
    sizes = [len(m["content"]) for m in compacted if m["role"] == "tool"]
    assert sizes[:3] == [len("0" * 400 + "\n… [earlier tool output truncated]")] * 3
    assert sizes[-1] == 3000
    assert messages[2]["content"] == "0" * 3000  # original untouched


# --- structured output ---------------------------------------------------------------------


VALID = {"files": [{"path": "a.py", "reason": "It starts the application."}]}


def test_extract_json_tolerates_fences_and_thinking() -> None:
    assert extract_json('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_structured_output_valid_first_time() -> None:
    llm = ScriptedLLM(reply(json.dumps(VALID)))
    result = generate_structured(llm, [{"role": "user", "content": "x"}], StartHere)
    assert result.files[0].path == "a.py"
    assert llm.requests[0]["response_format"]["json_schema"]["name"] == "StartHere"


def test_structured_output_is_repaired_with_validation_errors() -> None:
    llm = ScriptedLLM(
        reply("not json at all"),
        reply('{"files": [{"path": "a.py", "reason": "short"}]}'),  # reason too short
        reply(json.dumps(VALID)),
    )
    result = generate_structured(llm, [{"role": "user", "content": "x"}], StartHere, max_repairs=2)
    assert result.files[0].reason == "It starts the application."
    second_prompt = llm.requests[2]["messages"][-1]["content"]
    assert "files.0.reason" in second_prompt and "at least 10 characters" in second_prompt


def test_structured_output_falls_back_when_guided_decoding_unsupported(settings: Any) -> None:
    settings.LLM_GUIDED_JSON = True
    llm = ScriptedLLM(LLMRequestError("bad request", 400), reply(json.dumps(VALID)))
    generate_structured(llm, [{"role": "user", "content": "x"}], StartHere)
    assert llm.requests[0]["response_format"] is not None
    assert llm.requests[1]["response_format"] is None


def test_structured_output_gives_up() -> None:
    llm = ScriptedLLM(reply("{}"), reply("{}"))
    with pytest.raises(StructuredOutputError, match="StartHere"):
        generate_structured(llm, [{"role": "user", "content": "x"}], StartHere, max_repairs=1)


# --- reference validation ----------------------------------------------------------------


FILES = [
    {"path": "src/app/main.py", "lines": 40},
    {"path": "src/app/models.py", "lines": 120},
    {"path": "README.md", "lines": 10},
    {"path": "tests/test_models.py", "lines": 30},
]
SYMBOLS = {"src/app/models.py": [{"name": "User", "start_line": 10, "end_line": 30}]}


@pytest.fixture
def index() -> FileIndex:
    return FileIndex(FILES, SYMBOLS, repo_name="acme/shop")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/app/main.py", ("src/app/main.py", None, None)),
        ("./src/app/main.py", ("src/app/main.py", None, None)),
        ("`src/app/main.py`", ("src/app/main.py", None, None)),
        ("SRC/App/Main.py", ("src/app/main.py", None, None)),
        ("app/main.py", ("src/app/main.py", None, None)),  # unique suffix
        ("main.py", ("src/app/main.py", None, None)),  # unique basename
        ("shop/src/app/main.py", ("src/app/main.py", None, None)),  # repo-name prefix
        ("src/app/models.py:12-20", ("src/app/models.py", 12, 20)),
        ("src/app/models.py#L5", ("src/app/models.py", 5, 5)),
        ("src/app/nope.py", (None, None, None)),
    ],
)
def test_resolve_file(index: FileIndex, raw: str, expected: tuple) -> None:
    assert index.resolve_file(raw) == expected


def test_clamp(index: FileIndex) -> None:
    assert index.clamp("README.md", 5, 50) == (5, 10)
    assert index.clamp("README.md", 8, 3) == (3, 8)
    assert index.clamp("README.md", 99, 120) == (None, None)
    assert index.clamp("README.md", None, None) == (None, None)


def test_repair_start_here_drops_fakes_and_duplicates(index: FileIndex) -> None:
    data = {
        "files": [
            {"path": "./src/app/main.py", "reason": "r", "start_line": None, "end_line": None},
            {"path": "ghost.py", "reason": "r", "start_line": None, "end_line": None},
            {"path": "src/app/main.py", "reason": "dup", "start_line": None, "end_line": None},
            {"path": "src/app/models.py", "reason": "r", "start_line": 100, "end_line": 500},
        ]
    }
    report = repair_start_here(data, index)
    assert [(f["path"], f["start_line"], f["end_line"]) for f in data["files"]] == [
        ("src/app/main.py", None, None),
        ("src/app/models.py", 100, 120),
    ]
    assert report.dropped == 1 and report.dropped_paths == ["ghost.py"]


def test_repair_overview_accepts_directories(index: FileIndex) -> None:
    data = {
        "structure": [
            {"path": "src/app", "description": "d"},
            {"path": "tests/", "description": "d"},
            {"path": "README.md", "description": "d"},
            {"path": "docs/", "description": "missing"},
        ],
        "entry_points": [
            {"path": "main.py", "description": "d", "start_line": None, "end_line": None}
        ],
    }
    repair_overview(data, index)
    assert [s["path"] for s in data["structure"]] == ["src/app/", "tests/", "README.md"]
    assert data["entry_points"][0]["path"] == "src/app/main.py"


def test_repair_glossary_links_terms_to_definitions(index: FileIndex) -> None:
    data = {
        "terms": [
            {"term": "User", "kind": "class", "definition": "d", "path": None},
            {"term": "Order", "kind": "concept", "definition": "d", "path": "src/app/order.py"},
            {"term": "user", "kind": "class", "definition": "duplicate", "path": None},
            {"term": "User", "kind": "class", "definition": "d", "path": "src/app/models.py"},
        ]
    }
    repair_glossary(data, index)
    user, order = data["terms"]
    assert (user["path"], user["start_line"], user["end_line"]) == ("src/app/models.py", 10, 30)
    assert order["path"] is None  # hallucinated location removed, term kept


def test_clamp_drops_filler_first_line_ranges(index: FileIndex) -> None:
    assert index.clamp("README.md", 1, 1) == (None, None)
    assert index.clamp("README.md", 1, 4) == (1, 4)
    assert index.clamp("README.md", 3, 3) == (3, 3)


def test_symbol_lookup_prefers_exact_case() -> None:
    symbols = {"cmd.js": [{"name": "Command", "start_line": 1, "end_line": 900},
                          {"name": "command", "start_line": 40, "end_line": 60}]}  # fmt: skip
    index = FileIndex([{"path": "cmd.js", "lines": 900}], symbols)
    assert index.symbol_range("cmd.js", "command()") == (40, 60)
    assert index.symbol_range("cmd.js", "Command") == (1, 900)
    assert index.symbol_range("cmd.js", "COMMAND") == (1, 900)


def test_glossary_prefers_symbol_ranges_and_drops_unverifiable_lines() -> None:
    models = (
        "\n".join(f"line {n}" for n in range(1, 121))
        .replace("line 10\n", "class User:\n")
        .replace("line 50", "TAX_RATE = 0.2")
        .replace("line 70", "# used at checkout")
    )
    index = FileIndex(FILES, SYMBOLS, content={"src/app/models.py": models}.get)
    data = {
        "terms": [
            # Guessed lines for a real symbol: replaced by the symbol's range.
            {"term": "User", "kind": "class", "definition": "d", "path": "src/app/models.py",
             "start_line": 120, "end_line": 120},
            # A constant really defined at the cited line: kept.
            {"term": "TAX_RATE", "kind": "config", "definition": "d",
             "path": "src/app/models.py", "start_line": 50, "end_line": 50},
            # Invented line that does not mention the term: range dropped, path kept.
            {"term": "Checkout", "kind": "concept", "definition": "d",
             "path": "src/app/models.py", "start_line": 90, "end_line": 90},
            # The file never mentions the term: location removed, term kept.
            {"term": "test-all", "kind": "config", "definition": "d",
             "path": "src/app/models.py", "start_line": None, "end_line": None},
        ]
    }  # fmt: skip
    report = repair_glossary(data, index)
    lines = [(t["term"], t["path"], t["start_line"], t["end_line"]) for t in data["terms"]]
    assert lines == [
        ("User", "src/app/models.py", 10, 30),
        ("TAX_RATE", "src/app/models.py", 50, 50),
        ("Checkout", "src/app/models.py", None, None),
        ("test-all", None, None, None),
    ]
    assert report.repaired == 3
