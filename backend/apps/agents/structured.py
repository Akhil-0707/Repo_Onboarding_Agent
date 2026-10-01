"""Structured (JSON) generation validated against Pydantic models, with repair retries."""

from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings
from pydantic import BaseModel, ValidationError

from apps.agents.loop import AgentLogger, TokenBudget, Usage
from apps.common.logging import get_logger
from apps.llm.client import LLMClient
from apps.llm.errors import LLMRequestError
from apps.llm.types import Message

logger = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class StructuredOutputError(Exception):
    """The model could not produce valid output for the schema after all repairs."""


def extract_json(text: str) -> Any:
    """Parse the first JSON object in ``text`` (tolerates code fences and chatter)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in the reply")
    value, _ = json.JSONDecoder().raw_decode(text, start)
    return value


def _schema_for(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    return {"name": model.__name__, "schema": schema, "strict": True}


def _describe(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors()[:15]:
        location = ".".join(str(p) for p in error["loc"]) or "(root)"
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)


def generate_structured[T: BaseModel](
    llm: LLMClient,
    messages: list[Message],
    model: type[T],
    *,
    max_repairs: int | None = None,
    max_tokens: int = 3000,
    budget: TokenBudget | None = None,
    usage: Usage | None = None,
    agent_logger: AgentLogger | None = None,
    purpose: str = "structured",
) -> T:
    max_repairs = settings.ANALYSIS_MAX_REPAIRS if max_repairs is None else max_repairs
    guided = bool(settings.LLM_GUIDED_JSON)
    messages = list(messages)
    last_error = ""
    for attempt in range(max_repairs + 1):
        if budget is not None and budget.exhausted:
            raise StructuredOutputError("Token budget for this repository is used up.")
        response_format = (
            {"type": "json_schema", "json_schema": _schema_for(model)} if guided else None
        )
        try:
            response = llm.chat(
                messages, response_format=response_format, max_tokens=max_tokens, temperature=0.1
            )
        except LLMRequestError as exc:
            if guided and exc.status_code in {400, 422}:
                logger.info("guided_json_unsupported_falling_back", schema=model.__name__)
                guided = False
                continue
            raise
        if usage is not None:
            usage.add(response)
        if budget is not None:
            budget.used += response.usage.total_tokens
        if agent_logger is not None:
            agent_logger.llm(response, attempt, f"{purpose}:json")

        try:
            return model.model_validate(extract_json(response.content))
        except (ValueError, ValidationError) as exc:
            last_error = _describe(exc) if isinstance(exc, ValidationError) else str(exc)
            logger.info("structured_output_invalid", schema=model.__name__, attempt=attempt + 1)
            messages += [
                {"role": "assistant", "content": response.content[:4000]},
                {
                    "role": "user",
                    "content": (
                        "That output was not valid. Problems:\n"
                        f"{last_error}\n"
                        "Reply with ONLY the corrected JSON object that matches the schema. "
                        "No explanations, no code fences."
                    ),
                },
            ]
    raise StructuredOutputError(
        f"The model did not produce valid {model.__name__} output: {last_error[:300]}"
    )
