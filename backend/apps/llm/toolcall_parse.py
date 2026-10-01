"""Recover tool calls that a model wrote as plain text instead of structured ``tool_calls``.

Small models (and vLLM's hermes parser in streaming mode) sometimes emit the call in the
message body. Accepted shapes:
- ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>`` (Hermes / Qwen)
- a fenced ```json block containing such an object (or a list of them)
- a bare JSON object with ``name`` + ``arguments`` (or ``parameters``)
Only names in ``known_tools`` are accepted, so ordinary JSON answers are never misread.
"""

from __future__ import annotations

import json
import re
from typing import Any

from apps.llm.types import ToolCall

_TAGGED = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.DOTALL)
_FENCED = re.compile(r"```(?:json|tool_call)?\s*(.*?)```", re.DOTALL)


def _objects_in(text: str) -> list[Any]:
    """Every top-level JSON value that can be decoded from ``text``."""
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        start = min(
            (i for i in (text.find("{", index), text.find("[", index)) if i != -1), default=-1
        )
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        values.append(value)
        index = end
    return values


def _as_call(value: Any, known: set[str], index: int) -> ToolCall | None:
    if not isinstance(value, dict):
        return None
    if "function" in value and isinstance(value["function"], dict):  # OpenAI-shaped
        value = value["function"]
    name = value.get("name") or value.get("tool")
    if not isinstance(name, str) or name not in known:
        return None
    arguments = value.get("arguments", value.get("parameters", value.get("args", {})))
    if isinstance(arguments, str):
        raw = arguments  # keep as written; validation reports problems to the model
    else:
        raw = json.dumps(arguments if arguments is not None else {})
    return ToolCall(id=f"text_call_{index}", name=name, arguments=raw)


def parse_text_tool_calls(content: str, known_tools: set[str] | list[str]) -> list[ToolCall]:
    if not content or not known_tools:
        return []
    known = set(known_tools)
    candidates: list[str] = _TAGGED.findall(content)
    if not candidates:
        candidates = _FENCED.findall(content)
    if not candidates:
        candidates = [content]

    calls: list[ToolCall] = []
    for chunk in candidates:
        for value in _objects_in(chunk):
            items = value if isinstance(value, list) else [value]
            for item in items:
                call = _as_call(item, known, len(calls))
                if call is not None:
                    calls.append(call)
    return calls


def strip_tool_call_markup(content: str) -> str:
    """Remove ``<tool_call>`` blocks (so they are not shown as answer text)."""
    return _TAGGED.sub("", content).strip()
