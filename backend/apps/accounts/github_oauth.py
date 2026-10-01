"""Minimal GitHub OAuth web-flow client (authorize URL, code exchange, profile fetch)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from django.conf import settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105 - endpoint, not a secret
API_URL = "https://api.github.com"

BASE_SCOPES = ("read:user",)
PRIVATE_REPO_SCOPES = ("read:user", "repo")


class GitHubOAuthError(Exception):
    """The OAuth exchange or profile fetch failed. Message is safe to show to users."""


@dataclass(frozen=True)
class GitHubToken:
    access_token: str
    scopes: tuple[str, ...]

    def __repr__(self) -> str:  # never print the token
        return f"GitHubToken(scopes={self.scopes!r})"


@dataclass(frozen=True)
class GitHubProfile:
    id: int
    login: str
    name: str
    email: str
    avatar_url: str


class GitHubOAuthClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    @staticmethod
    def authorize_url(state: str, *, private: bool) -> str:
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_OAUTH_REDIRECT_URI,
            "scope": " ".join(PRIVATE_REPO_SCOPES if private else BASE_SCOPES),
            "state": state,
            "allow_signup": "true",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> GitHubToken:
        try:
            response = httpx.post(
                TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_OAUTH_REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise GitHubOAuthError("Could not reach GitHub") from exc
        payload = response.json() if response.status_code == 200 else {}
        token = payload.get("access_token")
        if not token:
            raise GitHubOAuthError(payload.get("error_description") or "GitHub sign-in failed")
        scopes = tuple(s for s in str(payload.get("scope", "")).replace(",", " ").split() if s)
        return GitHubToken(access_token=token, scopes=scopes)

    def fetch_profile(self, token: GitHubToken) -> GitHubProfile:
        try:
            response = httpx.get(
                f"{API_URL}/user",
                headers={
                    "Authorization": f"Bearer {token.access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise GitHubOAuthError("Could not reach GitHub") from exc
        if response.status_code != 200:
            raise GitHubOAuthError("Could not read your GitHub profile")
        data = response.json()
        return GitHubProfile(
            id=int(data["id"]),
            login=str(data["login"]),
            name=str(data.get("name") or ""),
            email=str(data.get("email") or ""),
            avatar_url=str(data.get("avatar_url") or ""),
        )


def get_oauth_client() -> GitHubOAuthClient:
    """Factory so tests can monkeypatch the client."""
    return GitHubOAuthClient()
