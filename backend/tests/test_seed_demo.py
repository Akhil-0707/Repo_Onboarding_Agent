"""``manage.py seed_demo`` (needs MongoDB)."""

from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.accounts.services import get_github_token
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.github import set_code_host
from apps.repos.models import Repository, UserRepository
from tests.conftest_fixtures import FIXTURES
from tests.fakes.github import FakeCodeHost

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> Any:
    index_store.ensure_indexes()
    for name in (index_store.FILES, index_store.CHUNKS, index_store.EDGES):
        index_store.collection(name).delete_many({})
    fake = FakeCodeHost()
    set_code_host(fake)
    set_event_bus(InMemoryEventBus())

    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / url.rsplit("/", 1)[-1], destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)
    yield fake
    set_code_host(None)
    set_event_bus(None)


def seed(*args: str) -> str:
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def test_seed_analyses_as_demo_user_and_shares_it(
    host: FakeCodeHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    ada = User.objects.create(username="ada", github_id=11)
    monkeypatch.setenv("GITHUB_API_TOKEN", "ghp_server_token")

    output = seed("--repo", "acme/py_app", "--add-to", "ada", "--wait")

    demo = User.objects.get(username="demo")
    assert not demo.has_usable_password()
    assert get_github_token(demo) == "ghp_server_token"  # stored encrypted, demo user only
    assert host.tokens == ["ghp_server_token"]
    repo = Repository.objects.get(name="py_app")
    assert repo.status == "ready"
    assert UserRepository.objects.filter(user=ada, repository=repo).exists()
    assert "done 100%" in output and "Demo repository ready." in output

    again = seed("--repo", "acme/py_app")
    assert "already analysed (cached)" in again
    assert Repository.objects.filter(name="py_app").count() == 1


def test_seed_errors(host: FakeCodeHost) -> None:
    with pytest.raises(CommandError, match="No user named 'nobody'"):
        seed("--add-to", "nobody")
    with pytest.raises(CommandError, match="not found"):
        seed("--repo", "acme/missing")
    with pytest.raises(CommandError, match="GitHub repository URL"):
        seed("--repo", "not a url")
