"""Tool-calling agent loop built for small, self-hosted models.

Safeguards:
- every tool call is validated (``execute_tool``); invalid calls get an error message that
  tells the model how to fix them (repair), with a cap on consecutive repairs;
- tool calls written as text are recovered (``parse_text_tool_calls``);
- an iteration cap and a shared token budget, after which the model must answer;
- older tool output is compacted so the context stays within a 16k window;
- a checkpoint callback after every step so a run can resume after the model disappears.
``ModelOfflineError`` is deliberately *not* caught here: callers checkpoint and pause.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from apps.agents.tools import Citation, ToolContext, ToolResult, execute_tool, tool_schemas
from apps.common.logging import get_logger, scrub
from apps.common.mongo import get_db
from apps.llm.client import LLMClient
from apps.llm.toolcall_parse import parse_text_tool_calls, strip_tool_call_markup
from apps.llm.types import LLMResponse, Message, ToolCall

logger = get_logger(__name__)

AGENT_LOGS = "agent_logs"
FINAL_ANSWER_NUDGE = (
    "Stop calling tools now. Write your answer using only the information gathered so far."
)
REPAIR_EXHAUSTED_NUDGE = (
    "Your last tool calls were invalid several times. Do not call tools again; "
    "answer with what you have."
)
EMPTY_ANSWER_NUDGE = "Your reply was empty. Either call a tool or write your answer."
REPAIRABLE = {"invalid_json", "invalid_arguments", "unknown_tool"}


class BudgetExceededError(Exception):
    """The repository's token budget is used up."""


@dataclass
class TokenBudget:
    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    def add(self, response: LLMResponse) -> None:
        self.calls += 1
        self.prompt_tokens += response.usage.prompt_tokens
        self.completion_tokens += response.usage.completion_tokens
        self.latency_ms += response.latency_ms

    def merge(self, other: Usage) -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.latency_ms += other.latency_ms

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
        }


@dataclass
class ToolEvent:
    name: str
    arguments: str
    ok: bool
    summary: str
    duration_ms: int
    citations: list[Citation] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments[:500],
            "ok": self.ok,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AgentResult:
    final_text: str
    messages: list[Message]
    citations: list[Citation]
    tool_events: list[ToolEvent]
    iterations: int
    usage: Usage
    stopped_reason: str


class AgentLogger:
    """Writes one document per LLM call / tool call to ``agent_logs`` (TTL 30 days)."""

    def __init__(self, repo_id: str, *, scope: str, run_id: str | None = None) -> None:
        self.repo_id = ObjectId(repo_id)
        self.scope = scope
        self.run_id = run_id

    def _write(self, doc: dict[str, Any]) -> None:
        try:
            get_db()[AGENT_LOGS].insert_one(
                {"repo_id": self.repo_id, "scope": self.scope, "run_id": self.run_id,
                 "ts": datetime.now(UTC), **doc}
            )  # fmt: skip
        except Exception as exc:  # logging must never break an agent run
            logger.warning("agent_log_write_failed", error=str(exc))

    def llm(self, response: LLMResponse, iteration: int, purpose: str) -> None:
        self._write(
            {
                "kind": "llm",
                "purpose": purpose,
                "iteration": iteration,
                "model": response.model,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "latency_ms": response.latency_ms,
                "attempts": response.attempts,
                "tool_calls": [tc.name for tc in response.tool_calls],
                "finish_reason": response.finish_reason,
            }
        )

    def tool(self, event: ToolEvent, iteration: int, error_type: str | None) -> None:
        self._write(
            {
                "kind": "tool",
                "iteration": iteration,
                "tool": event.name,
                "arguments": scrub(event.arguments[:500]),
                "ok": event.ok,
                "error_type": error_type,
                "duration_ms": event.duration_ms,
            }
        )


def _summary(name: str, arguments: str, result: ToolResult) -> str:
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    target = args.get("query") or args.get("pattern") or args.get("path") or args.get("name")
    target = target or args.get("module") or ""
    verb = {
        "search_code": "Searching for",
        "grep": "Grepping for",
        "read_file": "Reading",
        "list_directory": "Listing",
        "get_symbol": "Looking up",
        "get_dependencies": "Checking dependencies of",
        "get_repo_metadata": "Reading repository metadata",
    }.get(name, f"Calling {name}")
    text = f"{verb} '{target}'" if target else verb
    return text if result.ok else f"{text} (failed: {result.error_type})"


def compact_messages(
    messages: list[Message], max_chars: int, keep_recent: int = 3
) -> list[Message]:
    """Shorten older tool results so the conversation fits the model's context window."""

    def size(msgs: list[Message]) -> int:
        return sum(
            len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls", [])))
            for m in msgs
        )

    if size(messages) <= max_chars:
        return messages
    compacted = [dict(m) for m in messages]
    tool_indexes = [i for i, m in enumerate(compacted) if m.get("role") == "tool"]
    for index in tool_indexes[:-keep_recent] if keep_recent else tool_indexes:
        content = str(compacted[index].get("content") or "")
        if len(content) > 400:
            compacted[index]["content"] = content[:400] + "\n… [earlier tool output truncated]"
        if size(compacted) <= max_chars:
            return compacted
    # Still too big: truncate the most recent tool outputs too, newest last.
    for index in tool_indexes[-keep_recent:]:
        content = str(compacted[index].get("content") or "")
        if len(content) > 2000:
            compacted[index]["content"] = content[:2000] + "\n… [tool output truncated]"
    return compacted


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        ctx: ToolContext,
        *,
        tools: list[str] | None = None,
        max_iterations: int = 6,
        budget: TokenBudget | None = None,
        max_repairs: int = 2,
        max_context_chars: int = 40_000,
        final_max_tokens: int = 1200,
        agent_logger: AgentLogger | None = None,
        on_step: Callable[[list[Message]], None] | None = None,
        on_tool_start: Callable[[str, str], None] | None = None,
        on_tool_end: Callable[[ToolEvent], None] | None = None,
        purpose: str = "agent",
    ) -> None:
        self.llm = llm
        self.ctx = ctx
        self.tool_names = tools
        self.schemas = tool_schemas(tools)
        self.known = {s["function"]["name"] for s in self.schemas}
        self.max_iterations = max_iterations
        self.budget = budget or TokenBudget(limit=10**9)
        self.max_repairs = max_repairs
        self.max_context_chars = max_context_chars
        self.final_max_tokens = final_max_tokens
        self.agent_logger = agent_logger
        self.on_step = on_step
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.purpose = purpose
        self.usage = Usage()

    def _chat(self, messages: list[Message], iteration: int, *, tools: bool) -> LLMResponse:
        if self.budget.exhausted:
            raise BudgetExceededError("Token budget for this repository is used up.")
        response = self.llm.chat(
            compact_messages(messages, self.max_context_chars),
            tools=self.schemas if tools else None,
            max_tokens=self.final_max_tokens,
        )
        self.usage.add(response)
        self.budget.used += response.usage.total_tokens
        if self.agent_logger:
            self.agent_logger.llm(response, iteration, self.purpose)
        return response

    def _run_tool(self, call: ToolCall, iteration: int) -> tuple[ToolEvent, ToolResult]:
        if self.on_tool_start:
            self.on_tool_start(call.name, call.arguments)
        started = time.perf_counter()
        if self.tool_names is not None and call.name not in self.known:
            result = ToolResult(
                False,
                f"Tool '{call.name}' is not available here. "
                f"Use one of: {', '.join(sorted(self.known))}.",
                error_type="unknown_tool",
            )
        else:
            result = execute_tool(call.name, call.arguments, self.ctx)
        event = ToolEvent(
            name=call.name,
            arguments=call.arguments,
            ok=result.ok,
            summary=_summary(call.name, call.arguments, result),
            duration_ms=int((time.perf_counter() - started) * 1000),
            citations=result.citations,
        )
        if self.agent_logger:
            self.agent_logger.tool(event, iteration, result.error_type)
        if self.on_tool_end:
            self.on_tool_end(event)
        return event, result

    def run(self, messages: list[Message], start_iteration: int = 0) -> AgentResult:
        messages = list(messages)
        events: list[ToolEvent] = []
        citations: list[Citation] = []
        consecutive_invalid = 0
        nudged_empty = False
        iteration = start_iteration
        stopped = "answered"

        while True:
            if iteration >= self.max_iterations:
                stopped = "max_iterations"
                break
            if self.budget.remaining < 2000:
                stopped = "budget"
                break
            response = self._chat(messages, iteration, tools=True)
            iteration += 1
            calls = response.tool_calls or parse_text_tool_calls(response.content, self.known)

            if not calls:
                text = strip_tool_call_markup(response.content)
                if text:
                    messages.append({"role": "assistant", "content": text})
                    if self.on_step:
                        self.on_step(messages)
                    return AgentResult(
                        text, messages, citations, events, iteration, self.usage, stopped
                    )
                if nudged_empty:
                    stopped = "empty"
                    break
                nudged_empty = True
                messages.append({"role": "user", "content": EMPTY_ANSWER_NUDGE})
                continue

            # Record the call in OpenAI format so tool results attach to it.
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        strip_tool_call_markup(response.content) if response.tool_calls else ""
                    ),
                    "tool_calls": [c.to_message_dict() for c in calls],
                }
            )
            any_valid = False
            for call in calls:
                event, result = self._run_tool(call, iteration)
                events.append(event)
                citations.extend(result.citations)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result.output})
                if result.ok or result.error_type not in REPAIRABLE:
                    any_valid = True
            consecutive_invalid = 0 if any_valid else consecutive_invalid + 1
            if self.on_step:
                self.on_step(messages)
            if consecutive_invalid > self.max_repairs:
                messages.append({"role": "user", "content": REPAIR_EXHAUSTED_NUDGE})
                stopped = "repairs_exhausted"
                break

        # Out of iterations/budget/repairs: one last call without tools forces an answer.
        if stopped != "repairs_exhausted":
            messages.append({"role": "user", "content": FINAL_ANSWER_NUDGE})
        response = self._chat(messages, iteration, tools=False)
        text = strip_tool_call_markup(response.content)
        messages.append({"role": "assistant", "content": text})
        if self.on_step:
            self.on_step(messages)
        return AgentResult(text, messages, citations, events, iteration + 1, self.usage, stopped)
