"""Attach a request id to every request and to every log line emitted while handling it."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(
        self, get_response: Callable[[HttpRequest], HttpResponse | Awaitable[HttpResponse]]
    ) -> None:
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    @staticmethod
    def _bind(request: HttpRequest) -> str:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.request_id = request_id  # type: ignore[attr-defined]
        return request_id

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        if iscoroutinefunction(self):
            return self.__acall__(request)
        request_id = self._bind(request)
        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id  # type: ignore[index]
        return response  # type: ignore[return-value]

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        request_id = self._bind(request)
        response = await self.get_response(request)  # type: ignore[misc]
        response[REQUEST_ID_HEADER] = request_id
        return response
