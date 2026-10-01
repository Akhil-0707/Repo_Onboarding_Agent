from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Message = dict[str, Any]
"""An OpenAI-style chat message (``{"role": ..., "content": ..., ...}``)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    """Raw JSON string exactly as the model produced it (may be malformed)."""

    def to_message_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str | None
    usage: Usage
    latency_ms: int
    model: str
    attempts: int = 1

    def assistant_message(self) -> Message:
        message: Message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [tc.to_message_dict() for tc in self.tool_calls]
        return message


@dataclass(frozen=True)
class StreamEvent:
    type: Literal["token", "done"]
    text: str = ""
    response: LLMResponse | None = None
    """Set on the final ``done`` event: the fully assembled response."""


@dataclass(frozen=True)
class HealthStatus:
    online: bool
    model: str
    latency_ms: int | None
    checked_at: str
    error: str | None = None
    served_models: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "online": self.online,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
            "error": self.error,
        }
