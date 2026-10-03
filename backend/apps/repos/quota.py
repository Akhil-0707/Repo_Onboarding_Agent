"""Per-user limits: new analyses (``RATE_LIMIT_NEW_ANALYSES``, default 5/hour) and chat
questions (``RATE_LIMIT_CHAT_QUESTIONS``, default 30/hour).

Only requests that create work count: the analysis service consumes its quota right before it
enqueues a pipeline, so cache hits (another user already analysed that commit) are free; a chat
question counts once every pre-check passed, right before the model is asked.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User
from apps.common.errors import ApiError

NEW_ANALYSIS = "new_analysis"
CHAT_QUESTION = "chat_question"


class RateLimited(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "rate_limited"
    default_detail = "Too many requests."


class UserQuota(SimpleRateThrottle):
    """A sliding-window limit per user and ``scope`` (history kept in the cache)."""

    def __init__(self, scope: str, user: User) -> None:
        self.scope = scope
        self.user = user
        super().__init__()

    def get_rate(self) -> str | None:
        # Read on every use (DRF caches the rates at import time).
        return settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][self.scope]

    def get_cache_key(self, request: Any = None, view: Any = None) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.user.pk}

    def consume(self) -> int | None:
        """Count one use; the seconds to wait when the limit is reached, else None."""
        if self.allow_request(None, None):  # type: ignore[arg-type]
            return None
        return int(self.wait() or 0) + 1

    def status(self) -> dict[str, int]:
        assert self.num_requests is not None and self.duration is not None
        now = self.timer()
        history = [t for t in self.cache.get(self.get_cache_key(), []) if t > now - self.duration]
        reset = int(history[-1] + self.duration - now) + 1 if history else 0  # oldest is last
        return {
            "limit": self.num_requests,
            "used": len(history),
            "remaining": max(0, self.num_requests - len(history)),
            "reset_in_seconds": reset if len(history) >= self.num_requests else 0,
            "window_seconds": self.duration,
        }


def _wait_text(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def consume_new_analysis(request: Request) -> None:
    quota = UserQuota(NEW_ANALYSIS, request.user)
    wait = quota.consume()
    if wait is None:
        return
    raise RateLimited(
        f"You can start {quota.num_requests} new analyses per hour. Repositories someone "
        f"already analysed are not limited. Try again in {_wait_text(wait)}.",
        details={"retry_after_seconds": wait},
    )


def _chat_limited(quota: UserQuota, wait: int) -> RateLimited:
    return RateLimited(
        f"You can ask {quota.num_requests} questions per hour. Try again in {_wait_text(wait)}.",
        details={"retry_after_seconds": wait},
    )


def consume_chat_question(user: User) -> None:
    quota = UserQuota(CHAT_QUESTION, user)
    wait = quota.consume()
    if wait is not None:
        raise _chat_limited(quota, wait)


def ensure_chat_question_left(user: User) -> None:
    """Raise if ``user`` cannot ask now, without counting anything (e.g. before creating a
    conversation, so a limited first question does not leave an empty one behind)."""
    quota = UserQuota(CHAT_QUESTION, user)
    status = quota.status()
    if status["remaining"] == 0:
        raise _chat_limited(quota, status["reset_in_seconds"])


def quota_status(user: User, scope: str = NEW_ANALYSIS) -> dict[str, int]:
    return UserQuota(scope, user).status()
