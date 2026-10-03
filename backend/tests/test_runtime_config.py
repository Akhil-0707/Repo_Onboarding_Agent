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


def run_set_llm_url(*args: str) -> str:
    from io import StringIO

    out = StringIO()
    call_command("set_llm_url", *args, stdout=out)
    return out.getvalue()


def test_switching_servers_drops_the_old_model_and_adopts_a_single_served_one(
    fake_llm: object, settings: object
) -> None:
    from apps.llm.config import KEY_MODEL

    RuntimeSetting.objects.create(key=KEY_MODEL, value="qwen3:4b-instruct")  # previous server
    fake_llm.models = ["Qwen/Qwen3-8B-AWQ"]  # type: ignore[attr-defined]

    output = run_set_llm_url(fake_llm.url)  # type: ignore[attr-defined]

    assert "using its only model, 'Qwen/Qwen3-8B-AWQ'" in output
    assert "is online" in output
    assert get_llm_config(refresh=True).model == "Qwen/Qwen3-8B-AWQ"


def test_matching_default_model_needs_no_override(fake_llm: object) -> None:
    from apps.llm.config import KEY_MODEL

    RuntimeSetting.objects.create(key=KEY_MODEL, value="stale-model")
    output = run_set_llm_url(fake_llm.url)  # type: ignore[attr-defined]
    assert "Model 'fake-model' is online" in output
    assert not RuntimeSetting.objects.filter(key=KEY_MODEL).exists()


def test_rejected_api_key_gets_a_clear_hint(fake_llm: object, settings: object) -> None:
    fake_llm.models_status = 401  # type: ignore[attr-defined]
    settings.LLM_API_KEY = ""  # type: ignore[attr-defined]
    output = run_set_llm_url(fake_llm.url)  # type: ignore[attr-defined]
    assert "rejected the API key" in output and "LLM_API_KEY is currently empty" in output


def test_explicit_model_is_kept_with_a_list_when_not_served(fake_llm: object) -> None:
    fake_llm.models = ["a", "b"]  # type: ignore[attr-defined]
    output = run_set_llm_url(fake_llm.url, "--model", "c")  # type: ignore[attr-defined]
    assert "It serves: a, b. Pass --model." in output
    assert get_llm_config(refresh=True).model == "c"
