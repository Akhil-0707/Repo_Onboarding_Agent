"""HTTP clients for GitHub (API + OAuth), token encryption configuration, the Redis event bus
and small periodic tasks. No network: ``httpx`` calls are replaced with scripted responses."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.accounts import crypto
from apps.accounts.github_oauth import GitHubOAuthClient, GitHubOAuthError, GitHubToken
from apps.common.events import RedisEventBus
from apps.ingestion.errors import GitHubTokenRejectedError, IngestionError, RepositoryNotFoundError
from apps.ingestion.github import GitHubCodeHost, RepoRef

SHA = "0123456789abcdef0123456789abcdef01234567"
REPO = {
    "full_name": "Acme/Widget",
    "default_branch": "trunk",
    "description": None,
    "private": True,
    "size": 2048,
    "html_url": "https://github.com/Acme/Widget",
}

Handler = Callable[[str, dict[str, str]], httpx.Response]


def respond(status: int, body: Any = None, text: str | None = None, **headers: str) -> Any:
    def make(url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        if text is not None:
            return httpx.Response(status, text=text, headers=headers, request=request)
        return httpx.Response(status, json=body, headers=headers, request=request)

    return make


class Calls(list[tuple[str, dict[str, str]]]):
    """Recorded ``httpx.get`` calls, plus the queue of scripted replies."""

    def __init__(self) -> None:
        super().__init__()
        self.script: list[Any] = []


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Scripted ``httpx.get``: pops one response factory per call and records the calls."""
    calls = Calls()

    def fake_get(url: str, headers: dict[str, str] | None = None, **_: Any) -> httpx.Response:
        calls.append((url, dict(headers or {})))
        item = calls.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


def script(calls: Any, *items: Any) -> None:
    calls.script.extend(items)


# --- GitHub REST API -------------------------------------------------------------------------


def test_resolve_reads_repo_metadata_and_head_commit(github: Any) -> None:
    script(github, respond(200, REPO), respond(200, text=SHA + "\n"))
    info = GitHubCodeHost().resolve(RepoRef("acme", "widget"), "tok")
    assert (info.owner, info.name, info.default_branch, info.head_sha) == (
        "Acme", "Widget", "trunk", SHA,
    )  # fmt: skip
    assert info.private is True and info.size_kb == 2048 and info.description == ""
    assert info.url_key == "github.com/acme/widget"
    assert github[0][0].endswith("/repos/acme/widget")
    assert github[1][0].endswith("/repos/Acme/Widget/commits/trunk")
    assert github[0][1]["Authorization"] == "Bearer tok"
    assert github[1][1]["Accept"] == "application/vnd.github.sha"


def test_rejected_token_falls_back_to_anonymous(github: Any) -> None:
    script(github, respond(401, {}), respond(200, REPO), respond(200, text=SHA))
    info = GitHubCodeHost().resolve(RepoRef("acme", "widget"), "revoked")
    assert info.head_sha == SHA
    assert "Authorization" in github[0][1] and "Authorization" not in github[1][1]


@pytest.mark.parametrize(
    "anonymous_reply",
    [
        respond(403, {}, **{"x-ratelimit-remaining": "0"}),  # shared per-IP limit used up
        respond(404, {}),  # a private repository is invisible without the token
    ],
)
def test_rejected_token_is_reported_when_the_anonymous_retry_fails(
    github: Any, anonymous_reply: Any
) -> None:
    script(github, respond(401, {}), anonymous_reply)
    with pytest.raises(GitHubTokenRejectedError, match="sign in with GitHub again"):
        GitHubCodeHost().resolve(RepoRef("acme", "widget"), "revoked")


@pytest.mark.parametrize(
    ("reply", "error", "message"),
    [
        (respond(404, {}), RepositoryNotFoundError, "Repository not found"),
        (respond(403, {}, **{"x-ratelimit-remaining": "0"}), IngestionError, "rate limit"),
        (respond(429, {}, **{"x-ratelimit-remaining": "0"}), IngestionError, "rate limit"),
        (respond(403, {}), IngestionError, r"error \(403\)"),
        (respond(502, {}), IngestionError, r"error \(502\)"),
        (httpx.ConnectError("boom"), IngestionError, "Could not reach GitHub"),
    ],
)
def test_github_errors_are_translated(github: Any, reply: Any, error: type, message: str) -> None:
    script(github, reply)
    with pytest.raises(error, match=message):
        GitHubCodeHost().resolve(RepoRef("acme", "widget"), None)


def test_unexpected_commit_response_is_an_error(github: Any) -> None:
    script(github, respond(200, REPO), respond(200, text="<html>not a sha</html>"))
    with pytest.raises(IngestionError, match="latest commit"):
        GitHubCodeHost().resolve(RepoRef("acme", "widget"), None)


# --- GitHub OAuth ----------------------------------------------------------------------------


def test_authorize_url_scopes(settings: Any) -> None:
    public = GitHubOAuthClient.authorize_url("s1", private=False)
    private = GitHubOAuthClient.authorize_url("s2", private=True)
    assert "client_id=test-client-id" in public and "state=s1" in public
    assert "repo" not in public.split("scope=")[1].split("&")[0]
    assert "repo" in private.split("scope=")[1].split("&")[0]


def oauth_post(monkeypatch: pytest.MonkeyPatch, reply: Any) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def fake_post(url: str, data: dict[str, Any] | None = None, **_: Any) -> httpx.Response:
        sent.append(dict(data or {}))
        if isinstance(reply, Exception):
            raise reply
        return reply(url)

    monkeypatch.setattr(httpx, "post", fake_post)
    return sent


def test_exchange_code_returns_token_and_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = oauth_post(
        monkeypatch, respond(200, {"access_token": "gho_x", "scope": "repo,read:user"})
    )
    token = GitHubOAuthClient().exchange_code("abc")
    assert token.access_token == "gho_x" and token.scopes == ("repo", "read:user")
    assert sent[0]["code"] == "abc" and sent[0]["client_secret"] == "test-client-secret"


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (respond(200, {"error_description": "The code is wrong."}), "The code is wrong."),
        (respond(500, {"access_token": "ignored"}), "GitHub sign-in failed"),
        (httpx.ReadTimeout("slow"), "Could not reach GitHub"),
    ],
)
def test_exchange_code_failures(monkeypatch: pytest.MonkeyPatch, reply: Any, message: str) -> None:
    oauth_post(monkeypatch, reply)
    with pytest.raises(GitHubOAuthError, match=message):
        GitHubOAuthClient().exchange_code("abc")


def test_fetch_profile(github: Any) -> None:
    script(github, respond(200, {"id": 7, "login": "ada", "name": None, "avatar_url": "a.png"}))
    profile = GitHubOAuthClient().fetch_profile(GitHubToken("gho_x", ()))
    assert (profile.id, profile.login, profile.name, profile.email) == (7, "ada", "", "")
    assert github[0][1]["Authorization"] == "Bearer gho_x"

    script(github, respond(401, {}), httpx.ConnectError("down"))
    with pytest.raises(GitHubOAuthError, match="profile"):
        GitHubOAuthClient().fetch_profile(GitHubToken("bad", ()))
    with pytest.raises(GitHubOAuthError, match="reach"):
        GitHubOAuthClient().fetch_profile(GitHubToken("gho_x", ()))


# --- token encryption configuration ----------------------------------------------------------


@pytest.fixture
def fresh_cipher() -> Any:
    crypto._fernet.cache_clear()
    yield
    crypto._fernet.cache_clear()


def test_invalid_encryption_key_is_a_configuration_error(settings: Any, fresh_cipher: None) -> None:
    settings.TOKEN_ENCRYPTION_KEYS = ["not-a-fernet-key"]
    with pytest.raises(ImproperlyConfigured, match="invalid key"):
        crypto.encrypt_token("secret")


def test_missing_keys_only_allowed_in_debug(settings: Any, fresh_cipher: None) -> None:
    settings.TOKEN_ENCRYPTION_KEYS = []
    settings.DEBUG = False
    with pytest.raises(ImproperlyConfigured, match="must be set"):
        crypto.encrypt_token("secret")
    settings.DEBUG = True
    ciphertext = crypto.encrypt_token("secret")
    assert ciphertext != "secret" and crypto.decrypt_token(ciphertext) == "secret"
    assert crypto.encrypt_token("") == "" and crypto.decrypt_token("") == ""


# --- Redis event bus (real Redis; skipped when none is reachable) ----------------------------


def _redis_url() -> str | None:
    import redis
    from django.conf import settings

    try:
        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
        return str(settings.REDIS_URL)
    except Exception:
        return None


def test_redis_event_bus_delivers_events_and_ticks() -> None:
    url = _redis_url()
    if url is None:
        pytest.skip("Redis not reachable")
    bus = RedisEventBus(url)
    channel = f"test:{uuid.uuid4().hex}"

    async def run() -> list[Any]:
        subscription = bus.subscribe(channel, tick=0.3)
        received = [await anext(subscription)]  # subscribed
        bus.publish(channel, {"type": "step", "n": 1})
        received.append(await anext(subscription))
        received.append(await anext(subscription))  # nothing published: keep-alive tick
        await subscription.aclose()
        return received

    assert asyncio.run(run()) == [None, {"type": "step", "n": 1}, None]


def test_redis_publish_failures_are_swallowed() -> None:
    bus = RedisEventBus("redis://127.0.0.1:1/0")  # nothing listens on port 1
    bus.publish("anything", {"type": "log"})  # best effort: must not raise


# --- periodic tasks --------------------------------------------------------------------------


def test_llm_health_probe_task_refreshes_the_cache(fake_llm: Any) -> None:
    from django.core.cache import cache

    from apps.llm.health import CACHE_KEY
    from apps.llm.tasks import probe_llm_health

    result = probe_llm_health()
    assert result["online"] is True and result["model"] == "fake-model"
    assert cache.get(CACHE_KEY)["online"] is True


# --- service health + management commands (MongoDB) ------------------------------------------


@pytest.mark.mongo
@pytest.mark.django_db
def test_service_health_reports_degraded_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.core.cache import cache
    from rest_framework.test import APIClient

    ok = APIClient().get("/api/health")
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok", "mongo": True, "cache": True}

    def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "set", broken)
    degraded = APIClient().get("/api/health")
    assert degraded.status_code == 503
    assert degraded.json() == {"status": "degraded", "mongo": True, "cache": False}


@pytest.mark.mongo
@pytest.mark.django_db
def test_ensure_indexes_command_is_idempotent() -> None:
    from io import StringIO

    from django.core.management import call_command

    for _ in range(2):
        out = StringIO()
        call_command("ensure_indexes", stdout=out)
        assert "Indexes ensured:" in out.getvalue()
