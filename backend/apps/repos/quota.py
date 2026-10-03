"""Per-user limit on new analyses (``RATE_LIMIT_NEW_ANALYSES``, default 5/hour).

Only requests that create work count: the analysis service consumes the quota right before it
enqueues a pipeline, so cache hits (another user already analysed that commit) are free.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User
from apps.common.errors import ApiError


class RateLimited(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "rate_limited"
    default_detail = "Too many requests."


class NewAnalysisThrottle(SimpleRateThrottle):
    scope = "new_analysis"

    def get_rate(self) -> str | None:
        # Read on every use (DRF caches the rates at import time).
        return settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][self.scope]

    def get_cache_key(self, request: Request, view: Any) -> str:
        return self.key_for(request.user)

    def key_for(self, user: User) -> str:
        return self.cache_format % {"scope": self.scope, "ident": user.pk}


def _wait_text(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def consume_new_analysis(request: Request) -> None:
    throttle = NewAnalysisThrottle()
    if throttle.allow_request(request, None):
        return
    wait = int(throttle.wait() or 0) + 1
    raise RateLimited(
        f"You can start {throttle.num_requests} new analyses per hour. Repositories someone "
        f"already analysed are not limited. Try again in {_wait_text(wait)}.",
        details={"retry_after_seconds": wait},
    )


def quota_status(user: User) -> dict[str, int]:
    throttle = NewAnalysisThrottle()
    assert throttle.num_requests is not None and throttle.duration is not None
    now = throttle.timer()
    history = [
        t for t in throttle.cache.get(throttle.key_for(user), []) if t > now - throttle.duration
    ]
    reset = int(history[-1] + throttle.duration - now) + 1 if history else 0  # oldest is last
    return {
        "limit": throttle.num_requests,
        "used": len(history),
        "remaining": max(0, throttle.num_requests - len(history)),
        "reset_in_seconds": reset if len(history) >= throttle.num_requests else 0,
        "window_seconds": throttle.duration,
    }
