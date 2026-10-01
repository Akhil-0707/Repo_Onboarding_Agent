from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from django.conf import settings

from apps.llm import config as llm_config
from tests.fakes.openai_server import FakeOpenAIServer


def _mongo_reachable() -> bool:
    from pymongo import MongoClient

    try:
        MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:
        return False


_MONGO_OK: bool | None = None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    global _MONGO_OK
    if not any(item.get_closest_marker("mongo") for item in items):
        return
    _MONGO_OK = _mongo_reachable()
    if _MONGO_OK:
        return
    if os.environ.get("REQUIRE_MONGO") == "1":
        raise pytest.UsageError("REQUIRE_MONGO=1 but MongoDB is not reachable")
    skip = pytest.mark.skip(reason="MongoDB not reachable (start docker compose mongo)")
    for item in items:
        if item.get_closest_marker("mongo"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolate_llm_config(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never touch the runtime_settings collection unless marked ``mongo``."""
    llm_config.invalidate_cache()
    if request.node.get_closest_marker("mongo") is None:
        monkeypatch.setattr(llm_config, "_load_overrides", lambda: {})


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_llm(settings: pytest.FixtureRequest) -> Iterator[FakeOpenAIServer]:
    server = FakeOpenAIServer().start()
    server.models = ["fake-model"]
    settings.LLM_BASE_URL = server.url  # type: ignore[attr-defined]
    settings.LLM_MODEL = "fake-model"  # type: ignore[attr-defined]
    settings.LLM_API_KEY = "test-key"  # type: ignore[attr-defined]
    llm_config.invalidate_cache()
    yield server
    server.stop()
    llm_config.invalidate_cache()
