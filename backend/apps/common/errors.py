"""Consistent error envelope for every API response.

Shape: ``{"error": {"code": str, "message": str, "details": Any}}``
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.logging import get_logger

logger = get_logger(__name__)


class ApiError(exceptions.APIException):
    """Base class for domain errors raised from views and services."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"
    default_detail = "Bad request."

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        super().__init__(detail=message or self.default_detail, code=self.default_code)
        self.details = details


class ModelOfflineApiError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "model_offline"
    default_detail = "The language model server is offline. Try again when it is back."


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_detail = "Not found."


_CODE_BY_CLASS: dict[type[exceptions.APIException], str] = {
    exceptions.ValidationError: "validation_error",
    exceptions.ParseError: "parse_error",
    exceptions.AuthenticationFailed: "authentication_failed",
    exceptions.NotAuthenticated: "not_authenticated",
    exceptions.PermissionDenied: "permission_denied",
    exceptions.NotFound: "not_found",
    exceptions.MethodNotAllowed: "method_not_allowed",
    exceptions.Throttled: "rate_limited",
}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def error_response(code: str, message: str, http_status: int, details: Any = None) -> JsonResponse:
    """Envelope for plain Django (non-DRF) views such as SSE endpoints."""
    return JsonResponse(error_body(code, message, details), status=http_status)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("unhandled_api_error", view=str(context.get("view")))
        return Response(
            error_body("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    assert isinstance(exc, exceptions.APIException)
    if isinstance(exc, ApiError):
        code, message, details = exc.default_code, str(exc.detail), exc.details
    elif isinstance(exc, exceptions.ValidationError):
        code, message, details = "validation_error", "Invalid input.", exc.detail
    else:
        code = _CODE_BY_CLASS.get(type(exc), getattr(exc, "default_code", "error"))
        message = str(exc.detail) if not isinstance(exc.detail, dict | list) else "Request failed."
        details = exc.detail if isinstance(exc.detail, dict | list) else None
        if isinstance(exc, exceptions.Throttled):
            details = {"retry_after_seconds": exc.wait}

    response.data = error_body(code, message, details)
    return response
