"""LLM access behind a small interface.

``LLMClient`` is what the rest of the code depends on. ``OpenAICompatibleLLMClient`` talks to
any OpenAI-compatible server (vLLM on Kaggle, Ollama, a hosted provider) and assumes the server
can vanish at any moment: every call has timeouts, retries with exponential backoff and
jitter, and a terminal :class:`ModelOfflineError` the caller can turn into "pause and resume".
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from typing import Any

import openai
from django.conf import settings

from apps.common.logging import get_logger
from apps.llm.config import LLMConfig, get_llm_config
from apps.llm.errors import LLMRequestError, ModelOfflineError
from apps.llm.types import LLMResponse, Message, StreamEvent, ToolCall, Usage

logger = get_logger(__name__)

_RETRYABLE = (
    openai.APIConnectionError,  # includes APITimeoutError
    openai.InternalServerError,
    openai.RateLimitError,
)


class LLMClient(ABC):
    """Interface used by agents. Implementations must raise ``ModelOfflineError`` when the
    server cannot be reached after retries, and ``LLMRequestError`` for rejected requests."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Iterator[StreamEvent]: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        backoff_max: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._explicit_config = config
        self.connect_timeout = connect_timeout or settings.LLM_CONNECT_TIMEOUT
        self.read_timeout = read_timeout or settings.LLM_READ_TIMEOUT
        self.max_retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
        self.backoff_base = backoff_base or settings.LLM_BACKOFF_BASE
        self.backoff_max = backoff_max or settings.LLM_BACKOFF_MAX
        self._sleep = sleep
        self._sdk: openai.OpenAI | None = None
        self._sdk_key: tuple[str, str] | None = None

    # -- configuration --------------------------------------------------------------------
    @property
    def config(self) -> LLMConfig:
        # Re-resolved on each call so `set_llm_url` takes effect without a restart.
        return self._explicit_config or get_llm_config()

    @property
    def model_name(self) -> str:
        return self.config.model

    def _client(self) -> openai.OpenAI:
        config = self.config
        key = (config.base_url, config.api_key)
        if self._sdk is None or self._sdk_key != key:
            self._sdk = openai.OpenAI(
                base_url=config.base_url,
                api_key=config.api_key or "not-set",
                timeout=openai.Timeout(self.read_timeout, connect=self.connect_timeout),
                max_retries=0,  # retries are handled here so they are logged and bounded
            )
            self._sdk_key = key
        return self._sdk

    def _extra_body(self) -> dict[str, Any]:
        if settings.LLM_DISABLE_THINKING:
            # Qwen3-style chat templates: skip <think> blocks for faster, parseable output.
            return {"chat_template_kwargs": {"enable_thinking": False}}
        return {}

    def _backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max, self.backoff_base * (2**attempt))
        return delay * random.uniform(0.5, 1.0)  # noqa: S311 - jitter, not crypto

    # -- retry wrapper --------------------------------------------------------------------
    def _with_retries(self, op: str, fn: Callable[[], Any]) -> tuple[Any, int]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn(), attempt + 1
            except _RETRYABLE as exc:
                last_error = exc
                logger.warning(
                    "llm_call_retryable_error",
                    op=op,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
            except openai.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_error = exc
                    logger.warning("llm_call_server_error", op=op, status=exc.status_code)
                else:
                    raise LLMRequestError(
                        f"Model server rejected the request ({exc.status_code})", exc.status_code
                    ) from exc
            if attempt < self.max_retries:
                self._sleep(self._backoff(attempt))
        raise ModelOfflineError(
            f"Model server unavailable after {self.max_retries + 1} attempts: "
            f"{type(last_error).__name__}"
        ) from last_error

    # -- API ------------------------------------------------------------------------------
    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        model = self.model_name
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "extra_body": self._extra_body(),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if response_format:
            kwargs["response_format"] = response_format
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        started = time.perf_counter()
        completion, attempts = self._with_retries(
            "chat", lambda: self._client().chat.completions.create(**kwargs)
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        if not completion.choices:
            raise LLMRequestError("Model returned no choices")
        choice = completion.choices[0]
        tool_calls = [
            ToolCall(
                id=tc.id or f"call_{i}",
                name=tc.function.name,
                arguments=tc.function.arguments or "{}",
            )
            for i, tc in enumerate(choice.message.tool_calls or [])
            if getattr(tc, "function", None) is not None
        ]
        usage = Usage(
            prompt_tokens=getattr(completion.usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(completion.usage, "completion_tokens", 0) or 0,
        )
        response = LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            model=completion.model or model,
            attempts=attempts,
        )
        logger.info(
            "llm_call",
            op="chat",
            model=response.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            attempts=attempts,
            tool_calls=len(tool_calls),
        )
        return response

    def stream_chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream tokens. Retries happen only before the first chunk arrives; a disconnect
        mid-stream raises ``ModelOfflineError`` because partial output cannot be replayed."""
        model = self.model_name
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            "extra_body": self._extra_body(),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        started = time.perf_counter()
        stream, attempts = self._with_retries(
            "stream_chat", lambda: self._client().chat.completions.create(**kwargs)
        )

        text_parts: list[str] = []
        partial_calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        usage = Usage()
        served_model = model
        try:
            for chunk in stream:
                served_model = chunk.model or served_model
                if chunk.usage is not None:
                    usage = Usage(
                        prompt_tokens=chunk.usage.prompt_tokens or 0,
                        completion_tokens=chunk.usage.completion_tokens or 0,
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield StreamEvent(type="token", text=delta.content)
                for tc in delta.tool_calls or []:
                    slot = partial_calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function is not None:
                        slot["name"] += tc.function.name or ""
                        slot["args"] += tc.function.arguments or ""
        except (openai.APIConnectionError, openai.APIStatusError) as exc:
            raise ModelOfflineError("Model stream interrupted") from exc
        if finish_reason is None:
            # The connection closed before the model finished (e.g. the tunnel died).
            raise ModelOfflineError("Model stream ended before completion")

        tool_calls = [
            ToolCall(
                id=slot["id"] or f"call_{idx}", name=slot["name"], arguments=slot["args"] or "{}"
            )
            for idx, slot in sorted(partial_calls.items())
            if slot["name"]
        ]
        latency_ms = int((time.perf_counter() - started) * 1000)
        response = LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            model=served_model,
            attempts=attempts,
        )
        logger.info(
            "llm_call",
            op="stream_chat",
            model=served_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            attempts=attempts,
            tool_calls=len(tool_calls),
        )
        yield StreamEvent(type="done", response=response)


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Process-wide client. Tests swap it with :func:`set_llm_client`."""
    global _default_client
    if _default_client is None:
        _default_client = OpenAICompatibleLLMClient()
    return _default_client


def set_llm_client(client: LLMClient | None) -> None:
    global _default_client
    _default_client = client
