from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts import crypto, views
from apps.accounts.crypto import TokenDecryptionError, decrypt_token, encrypt_token
from apps.accounts.github_oauth import (
    GitHubOAuthClient,
    GitHubOAuthError,
    GitHubProfile,
    GitHubToken,
)
from apps.accounts.views import safe_next

GITHUB_TOKEN = "gho_" + "x" * 36


class FakeGitHub(GitHubOAuthClient):
    def __init__(
        self,
        *,
        profile: GitHubProfile | None = None,
        scopes: tuple[str, ...] = ("read:user",),
        fail: bool = False,
    ) -> None:
        super().__init__()
        self.profile = profile or GitHubProfile(
            id=4242, login="octo", name="Octo Cat", email="octo@example.com", avatar_url=""
        )
        self.scopes = scopes
        self.fail = fail
        self.codes: list[str] = []

    def exchange_code(self, code: str) -> GitHubToken:
        self.codes.append(code)
        if self.fail:
            raise GitHubOAuthError("bad_verification_code")
        return GitHubToken(access_token=GITHUB_TOKEN, scopes=self.scopes)

    def fetch_profile(self, token: GitHubToken) -> GitHubProfile:
        return self.profile


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    fake = FakeGitHub()
    monkeypatch.setattr(views, "get_oauth_client", lambda: fake)
    return fake


def web_client() -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_REPOGUIDE_CLIENT="web")
    return client


def start_login(client: APIClient, **params: str) -> str:
    response = client.get("/api/auth/github/login", params)
    assert response.status_code == 302
    return parse_qs(urlparse(response["Location"]).query)["state"][0]


def complete_login(client: APIClient, github: FakeGitHub) -> dict:
    state = start_login(client, next="/repos/1")
    callback = client.get("/api/auth/github/callback", {"code": "gh-code", "state": state})
    assert callback.status_code == 302
    query = parse_qs(urlparse(callback["Location"]).query)
    assert query["next"] == ["/repos/1"]
    exchange = client.post("/api/auth/exchange", {"code": query["code"][0]}, format="json")
    assert exchange.status_code == 200, exchange.content
    return exchange.json()


# --- encryption (no DB) ----------------------------------------------------------------------


def test_token_encryption_roundtrip_and_ciphertext_hides_token() -> None:
    ciphertext = encrypt_token(GITHUB_TOKEN)
    assert GITHUB_TOKEN not in ciphertext
    assert decrypt_token(ciphertext) == GITHUB_TOKEN


def test_key_rotation_keeps_old_ciphertexts_readable(settings: object) -> None:
    old_ciphertext = encrypt_token(GITHUB_TOKEN)
    settings.TOKEN_ENCRYPTION_KEYS = [  # type: ignore[attr-defined]
        Fernet.generate_key().decode(),
        *settings.TOKEN_ENCRYPTION_KEYS,  # type: ignore[attr-defined]
    ]
    crypto._fernet.cache_clear()
    assert decrypt_token(old_ciphertext) == GITHUB_TOKEN


def test_tampered_ciphertext_is_rejected() -> None:
    ciphertext = encrypt_token(GITHUB_TOKEN)
    with pytest.raises(TokenDecryptionError):
        decrypt_token(ciphertext[:-4] + "AAAA")


def test_github_token_repr_hides_value() -> None:
    assert GITHUB_TOKEN not in repr(GitHubToken(access_token=GITHUB_TOKEN, scopes=("repo",)))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/repos/1", "/repos/1"),
        (None, "/dashboard"),
        ("https://evil.com", "/dashboard"),
        ("//evil.com", "/dashboard"),
        ("/\\evil.com", "/dashboard"),
    ],
)
def test_safe_next_blocks_open_redirects(value: str | None, expected: str) -> None:
    assert safe_next(value) == expected


# --- OAuth redirect (no DB) ------------------------------------------------------------------


def test_login_redirects_to_github_with_state_cookie() -> None:
    client = APIClient()
    response = client.get("/api/auth/github/login")
    assert response.status_code == 302
    location = urlparse(response["Location"])
    query = parse_qs(location.query)
    assert location.netloc == "github.com"
    assert query["client_id"] == [settings.GITHUB_CLIENT_ID]
    assert query["scope"] == ["read:user"]
    assert query["state"][0]
    cookie = response.cookies[settings.AUTH_OAUTH_STATE_COOKIE]
    assert cookie["httponly"]


def test_login_requests_repo_scope_for_private_access() -> None:
    response = APIClient().get("/api/auth/github/login", {"private": "1"})
    assert parse_qs(urlparse(response["Location"]).query)["scope"] == ["read:user repo"]


def test_login_without_configuration_redirects_with_error(settings: object) -> None:
    settings.GITHUB_CLIENT_ID = ""  # type: ignore[attr-defined]
    response = APIClient().get("/api/auth/github/login")
    assert "error=" in response["Location"]


def test_callback_rejects_state_mismatch(github: FakeGitHub) -> None:
    client = APIClient()
    start_login(client)
    response = client.get("/api/auth/github/callback", {"code": "c", "state": "forged"})
    assert "error=" in response["Location"]
    assert github.codes == []  # never exchanged


def test_callback_without_state_cookie_is_rejected(github: FakeGitHub) -> None:
    response = APIClient().get("/api/auth/github/callback", {"code": "c", "state": "s"})
    assert "error=" in response["Location"]


def test_refresh_requires_client_header() -> None:
    response = APIClient().post("/api/auth/refresh")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_me_requires_authentication() -> None:
    response = APIClient().get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


# --- full flow (MongoDB) ---------------------------------------------------------------------


@pytest.mark.mongo
@pytest.mark.django_db
class TestSessionFlow:
    def test_login_creates_user_with_encrypted_token(self, github: FakeGitHub) -> None:
        from apps.accounts.models import User

        data = complete_login(web_client(), github)

        assert data["user"]["username"] == "octo"
        assert data["user"]["github_connected"] is True
        assert data["user"]["private_repo_access"] is False
        assert "github_token_encrypted" not in data["user"]
        user = User.objects.get(github_id=4242)
        assert user.github_token_encrypted
        assert GITHUB_TOKEN not in user.github_token_encrypted
        assert decrypt_token(user.github_token_encrypted) == GITHUB_TOKEN

    def test_second_login_updates_same_user(self, github: FakeGitHub) -> None:
        from apps.accounts.models import User

        complete_login(web_client(), github)
        github.scopes = ("read:user", "repo")
        data = complete_login(web_client(), github)

        assert User.objects.filter(github_id=4242).count() == 1
        assert data["user"]["private_repo_access"] is True

    def test_exchange_code_is_single_use(self, github: FakeGitHub) -> None:
        client = web_client()
        state = start_login(client)
        callback = client.get("/api/auth/github/callback", {"code": "c", "state": state})
        code = parse_qs(urlparse(callback["Location"]).query)["code"][0]

        assert client.post("/api/auth/exchange", {"code": code}, format="json").status_code == 200
        second = client.post("/api/auth/exchange", {"code": code}, format="json")
        assert second.status_code == 400
        assert second.json()["error"]["code"] == "invalid_code"

    def test_access_token_authenticates_me(self, github: FakeGitHub) -> None:
        client = web_client()
        access = complete_login(client, github)["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = client.get("/api/me")
        assert response.status_code == 200
        assert response.json()["username"] == "octo"

    def test_refresh_rotates_cookie(self, github: FakeGitHub) -> None:
        client = web_client()
        complete_login(client, github)
        first_cookie = client.cookies[settings.AUTH_REFRESH_COOKIE].value

        response = client.post("/api/auth/refresh")

        assert response.status_code == 200
        assert response.json()["access"]
        assert client.cookies[settings.AUTH_REFRESH_COOKIE].value != first_cookie

    def test_logout_revokes_refresh_and_access_tokens(self, github: FakeGitHub) -> None:
        client = web_client()
        access = complete_login(client, github)["access"]
        stolen_refresh = client.cookies[settings.AUTH_REFRESH_COOKIE].value

        assert client.post("/api/auth/logout").status_code == 204

        attacker = web_client()
        attacker.cookies[settings.AUTH_REFRESH_COOKIE] = stolen_refresh
        assert attacker.post("/api/auth/refresh").status_code == 401
        attacker.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        assert attacker.get("/api/me").status_code == 401

    def test_github_failure_redirects_with_error(self, github: FakeGitHub) -> None:
        github.fail = True
        client = web_client()
        state = start_login(client)
        response = client.get("/api/auth/github/callback", {"code": "c", "state": state})
        assert "error=bad_verification_code" in response["Location"]
