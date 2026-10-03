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


def test_login_link_is_single_use_and_debug_only(settings: Any) -> None:
    from rest_framework.test import APIClient

    settings.DEBUG = True
    out = StringIO()
    call_command("login_link", "dev", "--next", "/repos/x", stdout=out)
    url = out.getvalue().strip().splitlines()[-1]
    assert url.startswith("http://testserver-frontend/auth/callback?code=")
    assert "next=%2Frepos%2Fx" in url
    code = url.split("code=")[1].split("&")[0]
    assert not User.objects.get(username="dev").has_usable_password()

    client = APIClient()
    exchange = {"code": code}
    first = client.post(
        "/api/auth/exchange", exchange, format="json", HTTP_X_REPOGUIDE_CLIENT="web"
    )
    assert first.status_code == 200 and first.json()["user"]["username"] == "dev"
    again = client.post(
        "/api/auth/exchange", exchange, format="json", HTTP_X_REPOGUIDE_CLIENT="web"
    )
    assert again.status_code in {400, 401}

    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("login_link", "dev", stdout=StringIO())


def test_export_snapshot_records_real_responses(
    host: FakeCodeHost, settings: Any, tmp_path: Path
) -> None:
    import json

    from apps.chat.models import Message, Thread

    settings.DEBUG = True
    ada = User.objects.create(username="ada", github_id=12)
    seed("--repo", "acme/py_app", "--add-to", "ada")
    repo = Repository.objects.get(name="py_app")
    thread = Thread.objects.create(user=ada, repository=repo, title="Q")
    Message.objects.create(thread=thread, role="user", content="Where?")
    Message.objects.create(
        thread=thread, role="assistant", content="Here [app/routes.py:1-3].",
        citations=[{"path": "app/routes.py", "start_line": 1, "end_line": 3}],
    )  # fmt: skip

    out = tmp_path / "snapshot.json"
    call_command("export_snapshot", "ada", "acme/py_app", "--out", str(out), stdout=StringIO())
    data = json.loads(out.read_text(encoding="utf-8"))
    base = f"/api/repos/{repo.pk}"
    assert data["repo_id"] == str(repo.pk)
    assert {"/api/repos", base, f"{base}/analysis", f"{base}/tree", "/api/usage"} <= set(
        data["responses"]
    )
    assert data["responses"][f"{base}/threads/{thread.pk}"]["messages"][1]["content"]
    assert f"{base}/files?path=app%2Froutes.py" in data["responses"]  # cited by the chat
    assert f"{base}/files?path=app%2Fmain.py" in data["responses"]  # cited by the analysis

    with pytest.raises(CommandError, match="not on @ada"):
        call_command("export_snapshot", "ada", "acme/other", "--out", str(out))
