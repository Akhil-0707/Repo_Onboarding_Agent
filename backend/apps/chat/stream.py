"""``POST /api/repos/{id}/threads/{tid}/messages/stream``: ask a question, stream the answer.

The agent is synchronous (LLM client, PyMongo), so it runs in a worker thread and hands events
to the response through an asyncio queue. If the browser disconnects, the agent stops at its
next step. Checks that can fail (auth, ownership, input, model offline) answer with a normal
JSON error before any streaming starts.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from django.db import connections
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import AuthenticationFailed

from apps.chat.agent import answer_question
from apps.chat.models import Message, MessageRole, Thread
from apps.chat.serializers import AskSerializer, MessageSerializer
from apps.chat.views import get_user_thread
from apps.common.errors import NotFoundError, error_response
from apps.common.logging import get_logger
from apps.llm.health import check_llm_health
from apps.repos.models import RepoStatus
from apps.repos.stream import KEEPALIVE_SECONDS, authenticate_request, sse

logger = get_logger(__name__)


def _title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:79] + "…"


def _prepare(
    request: HttpRequest, repo_id: str, thread_id: str, content: str
) -> HttpResponse | tuple[Thread, Message]:
    user = authenticate_request(request)
    thread = get_user_thread(user, repo_id, thread_id)
    if thread.repository.status != RepoStatus.READY:
        return error_response("repo_not_ready", "The repository is still being processed.", 409)
    if not check_llm_health().online:
        return error_response(
            "model_offline", "The AI model is offline. Questions can be asked when it is back.", 503
        )
    question = Message.objects.create(thread=thread, role=MessageRole.USER, content=content)
    if not thread.title:
        thread.title = _title(content)
    thread.save(update_fields=["title", "updated_at"])
    return thread, question


async def answer_events(
    thread_id: str, question_id: str, tick: float = KEEPALIVE_SECONDS
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    cancelled = threading.Event()

    def emit(event: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event, data))

    def work() -> None:
        try:
            answer_question(thread_id, question_id, emit, cancelled.is_set)
        except Exception:
            logger.exception("chat_stream_worker_failed", thread=thread_id)
            emit("error", {"code": "server_error", "message": "Something went wrong."})
        finally:
            connections.close_all()  # this thread's connections
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker = threading.Thread(target=work, name=f"chat-{question_id}", daemon=True)
    worker.start()
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=tick)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                return
            yield sse(*item)
    finally:
        cancelled.set()  # client gone (or finished): the agent stops at its next step


# Authenticated by the Authorization header only (never cookies), so CSRF does not apply.
@csrf_exempt
async def message_stream_view(request: HttpRequest, repo_id: str, thread_id: str) -> HttpResponse:
    if request.method != "POST":
        return error_response("method_not_allowed", "Use POST.", 405)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return error_response("parse_error", "Malformed JSON.", 400)
    ask = AskSerializer(data=body if isinstance(body, dict) else {})
    if not ask.is_valid():
        return error_response("validation_error", "Invalid question.", 400, ask.errors)
    try:
        prepared = await sync_to_async(_prepare)(
            request, repo_id, thread_id, ask.validated_data["content"]
        )
    except AuthenticationFailed as exc:
        return error_response("not_authenticated", str(exc.detail), 401)
    except NotFoundError as exc:
        return error_response("not_found", str(exc.detail), 404)
    if isinstance(prepared, HttpResponse):
        return prepared
    thread, question = prepared

    async def events() -> AsyncIterator[str]:
        yield sse("start", {"message": dict(MessageSerializer(question).data)})
        async for chunk in answer_events(str(thread.pk), str(question.pk)):
            yield chunk

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
