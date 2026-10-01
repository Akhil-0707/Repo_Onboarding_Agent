"""A real HTTP server that speaks enough of the OpenAI API to exercise ``LLMClient``.

Responses are scripted per test: JSON completions, SSE streams, server errors and hangs
(for timeout tests). Every received request body is recorded for assertions.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class JsonReply:
    body: dict[str, Any]
    status: int = 200
    delay: float = 0.0


@dataclass
class StreamReply:
    chunks: list[dict[str, Any]]
    delay_between: float = 0.0
    drop_after: int | None = None
    """Close the connection abruptly after this many chunks (simulates a dead tunnel)."""


@dataclass
class ErrorReply:
    status: int = 500
    body: dict[str, Any] = field(default_factory=lambda: {"error": {"message": "boom"}})


def completion(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    *,
    model: str = "fake-model",
    finish_reason: str | None = None,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
) -> JsonReply:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.get("id", f"call_{i}"),
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc.get("arguments", "{}")},
            }
            for i, tc in enumerate(tool_calls)
        ]
    return JsonReply(
        {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason or ("tool_calls" if tool_calls else "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    )


def stream_chunks(
    tokens: list[str],
    *,
    tool_call: dict[str, Any] | None = None,
    model: str = "fake-model",
    usage: tuple[int, int] = (5, 3),
) -> list[dict[str, Any]]:
    def chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }

    chunks = [chunk({"role": "assistant", "content": ""})]
    chunks += [chunk({"content": t}) for t in tokens]
    if tool_call:
        args = tool_call.get("arguments", "{}")
        half = len(args) // 2
        chunks.append(
            chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_s0",
                            "type": "function",
                            "function": {"name": tool_call["name"], "arguments": args[:half]},
                        }
                    ]
                }
            )
        )
        chunks.append(chunk({"tool_calls": [{"index": 0, "function": {"arguments": args[half:]}}]}))
    chunks.append(chunk({}, "tool_calls" if tool_call else "stop"))
    chunks.append(
        {
            "id": "chatcmpl-fake",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": model,
            "choices": [],
            "usage": {
                "prompt_tokens": usage[0],
                "completion_tokens": usage[1],
                "total_tokens": sum(usage),
            },
        }
    )
    return chunks


class FakeOpenAIServer:
    def __init__(self) -> None:
        self.replies: deque[JsonReply | StreamReply | ErrorReply] = deque()
        self.requests: list[dict[str, Any]] = []
        self.request_headers: list[dict[str, str]] = []
        self.models: list[str] = ["fake-model"]
        self.models_status = 200
        self.required_api_key: str | None = None
        self.embedding_dimensions = 0
        """When > 0, ``/v1/embeddings`` answers with vectors of this size."""
        self.embedding_failures = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def enqueue(self, *replies: JsonReply | StreamReply | ErrorReply) -> None:
        self.replies.extend(replies)

    def start(self) -> FakeOpenAIServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return

            def _authorized(self) -> bool:
                if fake.required_api_key is None:
                    return True
                return self.headers.get("Authorization") == f"Bearer {fake.required_api_key}"

            def _send_json(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                if not self._authorized():
                    self._send_json(401, {"error": {"message": "unauthorized"}})
                    return
                if self.path.rstrip("/") == "/v1/models":
                    if fake.models_status != 200:
                        self._send_json(fake.models_status, {"error": {"message": "down"}})
                        return
                    self._send_json(
                        200,
                        {
                            "object": "list",
                            "data": [{"id": m, "object": "model"} for m in fake.models],
                        },
                    )
                    return
                self._send_json(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(body)
                fake.request_headers.append(dict(self.headers))
                if not self._authorized():
                    self._send_json(401, {"error": {"message": "unauthorized"}})
                    return
                if self.path.rstrip("/") == "/v1/embeddings" and fake.embedding_dimensions:
                    if fake.embedding_failures > 0:
                        fake.embedding_failures -= 1
                        self._send_json(503, {"error": {"message": "warming up"}})
                        return
                    inputs = body.get("input", [])
                    inputs = [inputs] if isinstance(inputs, str) else inputs
                    data = [
                        {
                            "object": "embedding",
                            "index": i,
                            "embedding": [float(len(t) + 1)] * fake.embedding_dimensions,
                        }
                        for i, t in enumerate(inputs)
                    ]
                    self._send_json(
                        200,
                        {
                            "object": "list",
                            "data": list(reversed(data)),
                            "model": body.get("model"),
                        },
                    )
                    return
                if not fake.replies:
                    self._send_json(500, {"error": {"message": "no scripted reply"}})
                    return
                reply = fake.replies.popleft()
                try:
                    if isinstance(reply, ErrorReply):
                        self._send_json(reply.status, reply.body)
                    elif isinstance(reply, JsonReply):
                        if reply.delay:
                            time.sleep(reply.delay)
                        self._send_json(reply.status, reply.body)
                    else:
                        self._stream(reply)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # client gave up (timeout tests)

            def _stream(self, reply: StreamReply) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                for i, chunk in enumerate(reply.chunks):
                    if reply.drop_after is not None and i >= reply.drop_after:
                        self.wfile.flush()
                        self.connection.shutdown(2)
                        return
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                    if reply.delay_between:
                        time.sleep(reply.delay_between)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        return Handler
