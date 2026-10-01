from __future__ import annotations

from rest_framework import exceptions

from apps.common.errors import ModelOfflineApiError, api_exception_handler
from apps.common.logging import REDACTED, redact_secrets, scrub


def test_redacts_sensitive_keys() -> None:
    event = redact_secrets(
        None,
        "info",
        {"event": "login", "access_token": "abc", "headers": {"Authorization": "Bearer x"}},
    )
    assert event["access_token"] == REDACTED
    assert event["headers"]["Authorization"] == REDACTED


def test_scrubs_token_shaped_values_inside_strings() -> None:
    text = "cloning with ghp_abcdefghijklmnopqrstuvwxyz0123 and Bearer eyJhbGciOi.payload.sig"
    cleaned = scrub(text)
    assert "ghp_" not in cleaned
    assert "eyJhbGciOi" not in cleaned
    assert cleaned.count(REDACTED) == 2


def test_error_envelope_for_validation_error() -> None:
    response = api_exception_handler(exceptions.ValidationError({"url": ["bad"]}), {})
    assert response is not None
    assert response.status_code == 400
    assert response.data == {
        "error": {
            "code": "validation_error",
            "message": "Invalid input.",
            "details": {"url": ["bad"]},
        }
    }


def test_error_envelope_for_domain_error() -> None:
    response = api_exception_handler(ModelOfflineApiError(), {})
    assert response is not None
    assert response.status_code == 503
    assert response.data["error"]["code"] == "model_offline"


def test_error_envelope_for_throttle() -> None:
    response = api_exception_handler(exceptions.Throttled(wait=42), {})
    assert response is not None
    assert response.status_code == 429
    assert response.data["error"]["code"] == "rate_limited"
    assert response.data["error"]["details"] == {"retry_after_seconds": 42}


def test_unhandled_exception_becomes_500_envelope() -> None:
    response = api_exception_handler(RuntimeError("secret detail"), {})
    assert response is not None
    assert response.status_code == 500
    assert response.data["error"]["code"] == "server_error"
    assert "secret detail" not in str(response.data)


def test_numeric_token_counts_are_not_redacted() -> None:
    event = redact_secrets(None, "info", {"event": "llm_call", "prompt_tokens": 120})
    assert event["prompt_tokens"] == 120
