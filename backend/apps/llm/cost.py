"""Token usage arithmetic. Tokens and latency are the primary metrics; the dollar estimate
uses configurable per-1k prices that default to 0 for the self-hosted model."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings

USAGE_KEYS = ("calls", "prompt_tokens", "completion_tokens", "latency_ms")


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1000 * settings.LLM_COST_PER_1K_INPUT
        + completion_tokens / 1000 * settings.LLM_COST_PER_1K_OUTPUT,
        6,
    )


def sum_usage(items: Iterable[Mapping[str, Any] | None]) -> dict[str, Any]:
    total = dict.fromkeys(USAGE_KEYS, 0)
    for item in items:
        for key in USAGE_KEYS:
            total[key] += int((item or {}).get(key) or 0)
    total["total_tokens"] = total["prompt_tokens"] + total["completion_tokens"]
    total["est_cost"] = estimate_cost(total["prompt_tokens"], total["completion_tokens"])
    return total
