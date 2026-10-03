"""Resolve the effective LLM configuration: runtime overrides first, then env settings."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from django.conf import settings

from apps.common.logging import get_logger

logger = get_logger(__name__)

KEY_BASE_URL = "llm.base_url"
KEY_MODEL = "llm.model"
RUNTIME_KEYS = (KEY_BASE_URL, KEY_MODEL)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


_lock = threading.Lock()
_cached: tuple[float, LLMConfig] | None = None


def normalize_base_url(url: str) -> str:
    """Validate an http(s) URL and make sure it points at the ``/v1`` API root."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Not a valid http(s) URL: {url!r}")
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _load_overrides() -> dict[str, str]:
    from apps.llm.models import RuntimeSetting

    try:
        rows = RuntimeSetting.objects.filter(key__in=RUNTIME_KEYS).values_list("key", "value")
        return {key: value for key, value in rows if value}
    except Exception as exc:  # DB unavailable: fall back to env settings
        logger.warning("runtime_settings_unavailable", error=str(exc))
        return {}


def get_llm_config(*, refresh: bool = False) -> LLMConfig:
    global _cached
    ttl = float(settings.LLM_RUNTIME_CONFIG_TTL)
    with _lock:
        now = time.monotonic()
        if not refresh and _cached is not None and now - _cached[0] < ttl:
            return _cached[1]
        overrides = _load_overrides()
        config = LLMConfig(
            base_url=overrides.get(KEY_BASE_URL, settings.LLM_BASE_URL),
            api_key=settings.LLM_API_KEY,
            model=overrides.get(KEY_MODEL, settings.LLM_MODEL),
        )
        _cached = (now, config)
        return config


def set_runtime_value(key: str, value: str) -> None:
    from apps.llm.models import RuntimeSetting

    if key not in RUNTIME_KEYS:
        raise ValueError(f"Unknown runtime setting {key!r}")
    RuntimeSetting.objects.update_or_create(key=key, defaults={"value": value})
    invalidate_cache()


def clear_runtime_value(key: str) -> None:
    from apps.llm.models import RuntimeSetting

    RuntimeSetting.objects.filter(key=key).delete()
    invalidate_cache()


def invalidate_cache() -> None:
    global _cached
    with _lock:
        _cached = None
