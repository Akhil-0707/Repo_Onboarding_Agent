"""Structured logging with secret redaction.

Every log line passes through :func:`redact_secrets`, which masks values whose key looks
sensitive and scrubs token-shaped strings, so OAuth tokens and API keys never reach logs.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)
# GitHub tokens, bearer headers, generic sk- style keys and Fernet ciphertexts.
_SENSITIVE_VALUE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._\-]+"
    r"|sk-[A-Za-z0-9_\-]{16,}|gAAAAA[A-Za-z0-9_\-=]{20,})"
)


def scrub(value: Any) -> Any:
    """Recursively redact sensitive keys and token-shaped substrings."""
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(REDACTED, value)
    if isinstance(value, Mapping):
        return {k: _redact_pair(k, v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(scrub(v) for v in value)
    return value


def _redact_pair(key: Any, value: Any) -> Any:
    # Numbers and booleans are never secrets (e.g. ``prompt_tokens=120``).
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(key, str) and _SENSITIVE_KEY.search(key):
        return REDACTED
    return scrub(value)


def redact_secrets(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if key == "event":
            event_dict[key] = scrub(event_dict[key])
        else:
            event_dict[key] = _redact_pair(key, event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_secrets,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Third-party HTTP clients log full URLs/headers at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpx2", "httpcore", "openai", "pymongo"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
