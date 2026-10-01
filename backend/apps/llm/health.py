"""Model server health: a cheap ``GET /models`` with the API key, cached briefly in Redis."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.common.logging import get_logger
from apps.llm.config import LLMConfig, get_llm_config
from apps.llm.types import HealthStatus

logger = get_logger(__name__)

CACHE_KEY = "llm:health"


def _probe(config: LLMConfig) -> HealthStatus:
    checked_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    try:
        response = httpx.get(
            f"{config.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {config.api_key}"} if config.api_key else {},
            timeout=settings.LLM_HEALTH_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return HealthStatus(
            online=False,
            model=config.model,
            latency_ms=None,
            checked_at=checked_at,
            error=f"unreachable ({type(exc).__name__})",
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        return HealthStatus(
            online=False,
            model=config.model,
            latency_ms=latency_ms,
            checked_at=checked_at,
            error=f"HTTP {response.status_code}",
        )
    try:
        served = [m.get("id", "") for m in response.json().get("data", [])]
    except ValueError:
        served = []
    if served and config.model not in served:
        return HealthStatus(
            online=False,
            model=config.model,
            latency_ms=latency_ms,
            checked_at=checked_at,
            error="configured model is not served by the server",
            served_models=served,
        )
    return HealthStatus(
        online=True,
        model=config.model,
        latency_ms=latency_ms,
        checked_at=checked_at,
        served_models=served,
    )


def check_llm_health(*, force: bool = False) -> HealthStatus:
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return HealthStatus(**cached)
    status = _probe(get_llm_config())
    cache.set(
        CACHE_KEY,
        {**status.as_dict(), "served_models": status.served_models},
        timeout=settings.LLM_HEALTH_CACHE_SECONDS,
    )
    previous = cache.get(f"{CACHE_KEY}:last_online")
    if previous is not None and previous != status.online:
        logger.info("llm_health_changed", online=status.online, error=status.error)
    cache.set(f"{CACHE_KEY}:last_online", status.online, timeout=None)
    return status


def is_model_online() -> bool:
    return check_llm_health().online
