from __future__ import annotations

import json

import pytest

from apps.llm.client import OpenAICompatibleLLMClient
from apps.llm.config import LLMConfig, invalidate_cache
from apps.llm.errors import LLMRequestError, ModelOfflineError
from tests.fakes.openai_server import (
    ErrorReply,
    FakeOpenAIServer,
    JsonReply,
    StreamReply,
    completion,
    stream_chunks,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]


def make_client(**kwargs: object) -> OpenAICompatibleLLMClient:
    sleeps: list[float] = []
    client = OpenAICompatibleLLMClient(sleep=sleeps.append, **kwargs)  # type: ignore[arg-type]
    client.sleeps = sleeps  # type: ignore[attr-defined]
    return client


def test_chat_returns_content_and_usage(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(completion("hello there", prompt_tokens=20, completion_tokens=4))

    response = make_client().chat([{"role": "user", "content": "hi"}])

    assert response.content == "hello there"
    assert response.tool_calls == []
    assert response.usage.prompt_tokens == 20
    assert response.usage.completion_tokens == 4
    assert response.latency_ms >= 0
    assert response.attempts == 1


def test_chat_sends_api_key_model_and_disables_thinking(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.required_api_key = "test-key"
    fake_llm.enqueue(completion("ok"))

    make_client().chat([{"role": "user", "content": "hi"}])

    body = fake_llm.requests[0]
    assert body["model"] == "fake-model"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_chat_parses_tool_calls(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(
        completion(tool_calls=[{"name": "read_file", "arguments": '{"path": "README.md"}'}])
    )

    response = make_client().chat([{"role": "user", "content": "read it"}], tools=TOOLS)

    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "read_file"
    assert json.loads(call.arguments) == {"path": "README.md"}
    assert fake_llm.requests[0]["tools"][0]["function"]["name"] == "read_file"
    assert response.assistant_message()["tool_calls"][0]["function"]["name"] == "read_file"


def test_malformed_tool_call_arguments_are_passed_through_raw(fake_llm: FakeOpenAIServer) -> None:
    """The client must not crash on broken JSON; the agent loop repairs it."""
    fake_llm.enqueue(completion(tool_calls=[{"name": "read_file", "arguments": '{"path": '}]))

    response = make_client().chat([{"role": "user", "content": "x"}], tools=TOOLS)

    assert response.tool_calls[0].arguments == '{"path": '


def test_retries_server_errors_then_succeeds(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(ErrorReply(502), ErrorReply(503), completion("recovered"))
    client = make_client(max_retries=3)

    response = client.chat([{"role": "user", "content": "hi"}])

    assert response.content == "recovered"
    assert response.attempts == 3
    assert len(client.sleeps) == 2  # type: ignore[attr-defined]
    assert client.sleeps[1] >= client.sleeps[0] * 0.5  # type: ignore[attr-defined]


def test_raises_model_offline_after_exhausting_retries(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(ErrorReply(500), ErrorReply(500), ErrorReply(500))

    with pytest.raises(ModelOfflineError):
        make_client(max_retries=2).chat([{"role": "user", "content": "hi"}])
    assert len(fake_llm.requests) == 3


def test_client_errors_are_not_retried(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(ErrorReply(400, {"error": {"message": "bad"}}), completion("never"))

    with pytest.raises(LLMRequestError) as info:
        make_client(max_retries=3).chat([{"role": "user", "content": "hi"}])
    assert info.value.status_code == 400
    assert len(fake_llm.requests) == 1


def test_read_timeout_is_retried_and_becomes_offline(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(
        JsonReply(completion("slow").body, delay=1.0), JsonReply(completion("slow").body, delay=1.0)
    )

    with pytest.raises(ModelOfflineError):
        make_client(read_timeout=0.2, connect_timeout=0.2, max_retries=1).chat(
            [{"role": "user", "content": "hi"}]
        )
    assert len(fake_llm.requests) == 2


def test_unreachable_server_is_offline() -> None:
    client = make_client(
        config=LLMConfig(base_url="http://127.0.0.1:9/v1", api_key="k", model="m"),
        connect_timeout=0.2,
        max_retries=1,
    )
    with pytest.raises(ModelOfflineError):
        client.chat([{"role": "user", "content": "hi"}])


def test_stream_yields_tokens_and_assembles_tool_calls(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(
        StreamReply(
            stream_chunks(
                ["Look", "ing"], tool_call={"name": "read_file", "arguments": '{"path": "a.py"}'}
            )
        )
    )

    events = list(make_client().stream_chat([{"role": "user", "content": "x"}], tools=TOOLS))

    tokens = [e.text for e in events if e.type == "token"]
    assert tokens == ["Look", "ing"]
    done = events[-1]
    assert done.type == "done" and done.response is not None
    assert done.response.content == "Looking"
    assert done.response.tool_calls[0].name == "read_file"
    assert json.loads(done.response.tool_calls[0].arguments) == {"path": "a.py"}
    assert done.response.usage.completion_tokens == 3


def test_slow_stream_outlives_the_read_timeout(fake_llm: FakeOpenAIServer) -> None:
    # 6 chunks x 0.1 s = longer than the 0.3 s read timeout, but each gap is shorter.
    fake_llm.enqueue(StreamReply(stream_chunks(['{"a"', ": ", "1}"]), delay_between=0.1))
    client = make_client(read_timeout=0.3, connect_timeout=0.3, max_retries=0)
    events = list(
        client.stream_chat(
            [{"role": "user", "content": "json"}], response_format={"type": "json_object"}
        )
    )
    assert events[-1].response is not None and events[-1].response.content == '{"a": 1}'
    assert fake_llm.requests[-1]["response_format"] == {"type": "json_object"}


def test_stream_interrupted_mid_way_raises_offline(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.enqueue(StreamReply(stream_chunks(["a", "b", "c", "d"]), drop_after=2))

    with pytest.raises(ModelOfflineError):
        list(make_client().stream_chat([{"role": "user", "content": "x"}]))


def test_new_base_url_takes_effect_without_new_client(
    fake_llm: FakeOpenAIServer, settings: object
) -> None:
    second = FakeOpenAIServer().start()
    try:
        client = make_client()
        fake_llm.enqueue(completion("from first"))
        assert client.chat([{"role": "user", "content": "x"}]).content == "from first"

        second.enqueue(completion("from second"))
        settings.LLM_BASE_URL = second.url  # type: ignore[attr-defined]
        invalidate_cache()
        assert client.chat([{"role": "user", "content": "x"}]).content == "from second"
    finally:
        second.stop()
