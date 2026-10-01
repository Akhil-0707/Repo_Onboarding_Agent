"""Server-Sent Events stream of ingestion progress.

Plain async Django view (DRF has no async support): JWT auth is checked by hand. The stream
sends a full ``snapshot`` first, then incremental ``step`` / ``log`` / ``job`` events, and a
fresh snapshot on every keep-alive tick so clients self-heal if an event was dropped.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.authentication import VersionedJWTAuthentication
from apps.common.errors import NotFoundError, error_response
from apps.common.events import get_event_bus
from apps.ingestion.progress import channel
from apps.repos.models import TERMINAL_JOB_STATUSES, IngestionJob
from apps.repos.serializers import JobSerializer
from apps.repos.services import get_user_repository, latest_job

KEEPALIVE_SECONDS = 15.0


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _authenticate(request: HttpRequest) -> Any:
    result = VersionedJWTAuthentication().authenticate(request)  # type: ignore[arg-type]
    if result is None:
        raise AuthenticationFailed("Authentication credentials were not provided.")
    return result[0]


def _resolve_job(request: HttpRequest, repo_id: str) -> IngestionJob:
    user = _authenticate(request)
    job = latest_job(get_user_repository(user, repo_id))
    if job is None:
        raise NotFoundError("No ingestion job for this repository.")
    return job


def _snapshot(job_id: str) -> dict[str, Any]:
    return dict(JobSerializer(IngestionJob.objects.get(pk=job_id)).data)


async def job_events(job_id: str, tick: float = KEEPALIVE_SECONDS) -> AsyncIterator[str]:
    subscription = get_event_bus().subscribe(channel(job_id), tick=tick)
    try:
        await anext(subscription)  # subscribed: nothing published from now on is missed
        snapshot = await sync_to_async(_snapshot)(job_id)
        yield sse("snapshot", snapshot)
        if snapshot["status"] in TERMINAL_JOB_STATUSES:
            yield sse("end", {"status": snapshot["status"]})
            return
        async for event in subscription:
            if event is None:
                snapshot = await sync_to_async(_snapshot)(job_id)
                yield sse("snapshot", snapshot)
                if snapshot["status"] in TERMINAL_JOB_STATUSES:
                    yield sse("end", {"status": snapshot["status"]})
                    return
                continue
            yield sse(str(event.get("type", "message")), event)
            if event.get("type") == "job" and event.get("status") in TERMINAL_JOB_STATUSES:
                yield sse("end", {"status": event["status"]})
                return
    finally:
        await subscription.aclose()


async def job_stream_view(request: HttpRequest, repo_id: str) -> HttpResponse:
    if request.method != "GET":
        return error_response("method_not_allowed", "Use GET.", 405)
    try:
        job = await sync_to_async(_resolve_job)(request, repo_id)
    except AuthenticationFailed as exc:
        return error_response("not_authenticated", str(exc.detail), 401)
    except NotFoundError as exc:
        return error_response("not_found", str(exc.detail), 404)

    response = StreamingHttpResponse(job_events(str(job.pk)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # nginx: do not buffer
    return response
