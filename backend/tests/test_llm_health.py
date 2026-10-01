from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.llm.config import normalize_base_url
from apps.llm.health import check_llm_health
from tests.fakes.openai_server import FakeOpenAIServer


def test_health_online(fake_llm: FakeOpenAIServer) -> None:
    status = check_llm_health(force=True)
    assert status.online is True
    assert status.model == "fake-model"
    assert status.latency_ms is not None


def test_health_offline_when_server_errors(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.models_status = 503
    status = check_llm_health(force=True)
    assert status.online is False
    assert status.error == "HTTP 503"


def test_health_offline_when_wrong_api_key(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.required_api_key = "another-key"
    status = check_llm_health(force=True)
    assert status.online is False
    assert status.error == "HTTP 401"


def test_health_offline_when_model_not_served(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.models = ["something-else"]
    status = check_llm_health(force=True)
    assert status.online is False
    assert "not served" in (status.error or "")


def test_health_unreachable(settings: object) -> None:
    settings.LLM_BASE_URL = "http://127.0.0.1:9/v1"  # type: ignore[attr-defined]
    settings.LLM_HEALTH_TIMEOUT = 0.3  # type: ignore[attr-defined]
    status = check_llm_health(force=True)
    assert status.online is False
    assert status.error is not None and status.error.startswith("unreachable")


def test_health_is_cached(fake_llm: FakeOpenAIServer) -> None:
    assert check_llm_health(force=True).online is True
    fake_llm.models_status = 503
    assert check_llm_health().online is True  # served from cache
    assert check_llm_health(force=True).online is False


def test_health_endpoint_shape_and_no_url_leak(fake_llm: FakeOpenAIServer) -> None:
    response = APIClient().get("/api/llm/health?refresh=1")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"online", "model", "latency_ms", "checked_at", "error"}
    assert data["online"] is True
    assert fake_llm.url not in response.content.decode()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://abc.trycloudflare.com", "https://abc.trycloudflare.com/v1"),
        ("https://abc.trycloudflare.com/", "https://abc.trycloudflare.com/v1"),
        ("https://abc.trycloudflare.com/v1/", "https://abc.trycloudflare.com/v1"),
        ("http://localhost:11434/v1", "http://localhost:11434/v1"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize("raw", ["ftp://x", "not a url", "https://"])
def test_normalize_base_url_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(raw)
