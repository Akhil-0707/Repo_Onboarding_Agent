"""Make sure a Guided Tour contains a flow trace.

When the model wrote a tour without any ``flow_trace`` stop, it is asked a much smaller
question than "rewrite the tour": which of *its own* stops, in order, follow one request or
command through the code. Those stops are then labelled ``flow_trace``. The trace is still the
model's choice; only the bookkeeping is done here.
"""

from __future__ import annotations

import json
from typing import Any

from apps.agents.prompts import SYSTEM
from apps.agents.schemas import FLOW_TRACE_REQUIRED, FlowTracePick
from apps.agents.structured import OutputRejectedError, StructuredOutputError, generate_structured
from apps.llm.client import LLMClient


def ensure_flow_trace(data: dict[str, Any], llm: LLMClient, **structured: Any) -> bool:
    """Label the stops the model picks; True when a pick was needed. Raises
    ``OutputRejectedError`` (the tour is then re-prompted) if no usable pick comes back."""
    steps = data["steps"]
    if any(step["kind"] == "flow_trace" for step in steps):
        return False
    listing = "\n".join(
        f"{n}. {step['title']} - {step['path']}"
        + (f" ({step['symbol']})" if step.get("symbol") else "")
        for n, step in enumerate(steps, 1)
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                f"These are the stops of a guided tour through the repository:\n{listing}\n\n"
                "Pick 2-6 consecutive stops that together follow ONE real request or command "
                "through the code, hop by hop (for example: entry point -> parsing -> "
                "handler). Reply with ONLY a JSON object matching this JSON schema: "
                f"{json.dumps(FlowTracePick.model_json_schema())}"
            ),
        },
    ]

    def in_range(pick: FlowTracePick) -> None:
        bad = [n for n in pick.steps if not 1 <= n <= len(steps)]
        if bad:
            raise OutputRejectedError(f"Stops {bad} do not exist; use numbers 1-{len(steps)}.")

    try:
        pick = generate_structured(
            llm, messages, FlowTracePick, max_repairs=1, max_tokens=200,
            purpose="tour:flow_trace", accept=in_range, **structured,
        )  # fmt: skip
    except StructuredOutputError as exc:
        raise OutputRejectedError(FLOW_TRACE_REQUIRED) from exc
    for number in sorted(set(pick.steps)):
        steps[number - 1]["kind"] = "flow_trace"
    return True
