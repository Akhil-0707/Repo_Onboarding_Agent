"""Runtime LLM settings persisted in MongoDB (needs a running MongoDB)."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.llm.config import KEY_BASE_URL, get_llm_config
from apps.llm.models import RuntimeSetting

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]


def test_runtime_override_wins_over_env(settings: object) -> None:
    settings.LLM_BASE_URL = "http://env-default/v1"  # type: ignore[attr-defined]
    assert get_llm_config(refresh=True).base_url == "http://env-default/v1"

    RuntimeSetting.objects.create(key=KEY_BASE_URL, value="https://tunnel.example/v1")
    assert get_llm_config(refresh=True).base_url == "https://tunnel.example/v1"


def test_set_llm_url_command_persists_and_normalizes(settings: object) -> None:
    settings.LLM_HEALTH_TIMEOUT = 0.2  # type: ignore[attr-defined]
    call_command("set_llm_url", "https://abc.trycloudflare.com")

    assert RuntimeSetting.objects.get(key=KEY_BASE_URL).value == "https://abc.trycloudflare.com/v1"
    assert get_llm_config().base_url == "https://abc.trycloudflare.com/v1"
