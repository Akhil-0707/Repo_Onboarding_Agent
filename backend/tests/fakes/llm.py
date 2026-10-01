"""In-process fake ``LLMClient``s for agent tests."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from apps.llm.client import LLMClient
from apps.llm.errors import ModelOfflineError
from apps.llm.types import LLMResponse, Message, StreamEvent, ToolCall, Usage


def reply(
    content: str = "", tool_calls: list[ToolCall] | None = None, tokens: tuple[int, int] = (100, 50)
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=Usage(*tokens),
        latency_ms=5,
        model="fake-llm",
    )


def call(name: str, arguments: dict[str, Any] | str, call_id: str = "c1") -> ToolCall:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(id=call_id, name=name, arguments=raw)


class ScriptedLLM(LLMClient):
    """Returns queued responses (or raises queued exceptions) and records every request."""

    def __init__(self, *responses: LLMResponse | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return "fake-llm"

    def chat(self, messages: list[Message], **kwargs: Any) -> LLMResponse:
        self.requests.append({"messages": [dict(m) for m in messages], **kwargs})
        if not self.responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def stream_chat(self, messages: list[Message], **kwargs: Any) -> Iterator[StreamEvent]:
        response = self.chat(messages, **kwargs)
        for word in response.content.split(" "):
            yield StreamEvent(type="token", text=word + " ")
        yield StreamEvent(type="done", response=response)


def _digest_list(prompt: str, label: str) -> list[str]:
    match = re.search(rf"{re.escape(label)}:?\s*(.*)", prompt)
    return [p.strip() for p in match.group(1).split(",")] if match else []


def _digest_dirs(prompt: str) -> list[str]:
    return re.findall(r"^\s+- (\S+/) \(\d+ files\)", prompt, flags=re.MULTILINE)


def section_answer(section: str, prompt: str) -> dict[str, Any]:
    """Schema-valid output built from the digest's real paths, plus bogus ones to exercise
    reference repair."""
    entries = _digest_list(prompt, "Likely entry points") or ["README.md"]
    dirs = _digest_dirs(prompt) or ["./"]
    if section == "overview":
        return {
            "summary": "A small web service that exposes user data over HTTP. It is a fixture.",
            "tech_stack": [{"name": "Python", "role": "Main language"}],
            "structure": [{"path": d, "description": "Source directory"} for d in dirs]
            + [{"path": "imaginary/", "description": "Does not exist"}],
            "prerequisites": ["Python 3.12"],
            "how_to_run": [{"description": "Install", "command": "pip install -e ."}],
            "entry_points": [{"path": entries[0], "description": "Main entry point"}],
            "starter_questions": [
                "Where are users stored?",
                "How are routes registered?",
                "How do I add an endpoint?",
                "How is configuration loaded?",
            ],
        }
    if section == "start_here":
        return {
            "files": [{"path": e, "reason": "Start here to see how it boots."} for e in entries]
            + [
                {"path": "does/not/exist.py", "reason": "A hallucinated file to be dropped."},
                {"path": f"./{entries[0]}", "reason": "Duplicate written differently."},
            ]
        }
    if section == "architecture":
        return {
            "summary": "A Flask app: the entry point builds the app and routes call services.",
            "modules": [
                {"id": "App", "name": "Application", "kind": "Entry", "paths": [entries[0]],
                 "description": "Creates and runs the app"},
                {"id": "core", "name": "Core package", "kind": "core",
                 "paths": ["app/", "app/ghost.py"], "description": "Routes and services"},
                {"id": "tests", "name": "Tests", "kind": "test", "paths": ["tests/"],
                 "description": "Unit tests"},
                {"id": "db", "name": "User store", "kind": "external", "paths": [],
                 "description": "Where users live"},
                {"id": "phantom", "name": "Phantom", "kind": "core", "paths": ["phantom/"],
                 "description": "Does not exist"},
            ],
            "edges": [
                {"source": "App", "target": "Core package", "label": "registers routes"},
                {"source": "core", "target": "db", "label": "stores users"},
                {"source": "core", "target": "phantom", "label": "dropped"},
                {"source": "core", "target": "core", "label": "self loop"},
            ],
        }  # fmt: skip
    if section == "tour":
        return {
            "intro": "Follow one HTTP request from app start-up to the user service.",
            "steps": [
                {"title": "Start-up", "kind": "entry_point", "path": entries[0],
                 "explanation": "create_app builds the Flask app and registers the routes."},
                {"title": "Routing", "kind": "Flow Trace", "path": "app/routes.py",
                 "explanation": "A request for /users lands in the route registered here."},
                {"title": "Service", "kind": "flow_trace", "path": "app/services.py",
                 "symbol": "UserService", "start_line": 99, "end_line": 99,
                 "explanation": "The route asks UserService for the users it stores."},
                {"title": "Ghost", "kind": "core_logic", "path": "nope/ghost.py",
                 "explanation": "A hallucinated stop that must be dropped."},
            ],
        }  # fmt: skip
    if section == "glossary":
        return {
            "terms": [
                {"term": "UserService", "kind": "class", "definition": "Stores users in memory."},
                {
                    "term": "Ghost",
                    "kind": "concept",
                    "definition": "Points at a file that does not exist.",
                    "path": "nope/ghost.py",
                },
                {
                    "term": "Entry point",
                    "kind": "concept",
                    "definition": "Where execution starts.",
                    "path": entries[0],
                },
            ]
        }
    raise AssertionError(f"unexpected section {section}")


class FakeAnalysisLLM(LLMClient):
    """A cooperative model: one tool call, then notes, then valid JSON per section."""

    def __init__(self, offline_after: int | None = None) -> None:
        self.offline_after = offline_after
        self.calls = 0
        self.sections_answered: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-llm"

    def chat(self, messages: list[Message], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        if self.offline_after is not None and self.calls > self.offline_after:
            raise ModelOfflineError("Model server unavailable (test)")
        prompt = "\n".join(str(m.get("content") or "") for m in messages if m["role"] == "user")
        if kwargs.get("tools"):
            if not any(m["role"] == "tool" for m in messages):
                return reply(tool_calls=[call("get_repo_metadata", {})])
            return reply("Research notes: entry point and services verified with tools.")
        section = re.search(r"^Section: (\w+)", prompt, flags=re.MULTILINE)
        if section:
            self.sections_answered.append(section.group(1))
            return reply(json.dumps(section_answer(section.group(1), prompt)))
        return reply("Research notes written without tools.")

    def stream_chat(self, messages: list[Message], **kwargs: Any) -> Iterator[StreamEvent]:
        response = self.chat(messages, **kwargs)
        yield StreamEvent(type="token", text=response.content)
        yield StreamEvent(type="done", response=response)
