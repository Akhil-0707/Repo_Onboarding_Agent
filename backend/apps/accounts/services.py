"""Account logic: GitHub user upsert, one-time exchange codes and JWT issuing/rotation."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import TOKEN_VERSION_CLAIM
from apps.accounts.crypto import decrypt_token, encrypt_token
from apps.accounts.github_oauth import GitHubProfile, GitHubToken
from apps.accounts.models import User
from apps.common.logging import get_logger

logger = get_logger(__name__)

EXCHANGE_PREFIX = "auth:exchange:"


class InvalidSession(Exception):
    """Refresh token missing, expired, malformed or revoked."""


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


def _unique_username(login: str, github_id: int) -> str:
    if not User.objects.filter(username=login).exclude(github_id=github_id).exists():
        return login
    # Someone else holds this login (e.g. a renamed GitHub account); disambiguate.
    return f"{login}-{github_id}"


@transaction.atomic
def upsert_github_user(profile: GitHubProfile, token: GitHubToken) -> User:
    user = User.objects.filter(github_id=profile.id).first()
    created = user is None
    if user is None:
        user = User(github_id=profile.id)
        user.set_unusable_password()
    user.username = _unique_username(profile.login, profile.id)
    first, _, last = profile.name.partition(" ")
    user.first_name, user.last_name = first[:150], last[:150]
    if profile.email:
        user.email = profile.email
    user.avatar_url = profile.avatar_url
    user.github_token_encrypted = encrypt_token(token.access_token)
    user.github_scopes = " ".join(token.scopes)
    user.save()
    logger.info(
        "github_user_upserted", user_id=str(user.pk), created=created, scopes=user.github_scopes
    )
    return user


def get_github_token(user: User) -> str:
    """Decrypt the user's GitHub token for server-side GitHub calls only.

    Never log it, return it from an API, or pass it to the LLM.
    """
    return decrypt_token(user.github_token_encrypted)


def create_exchange_code(user: User) -> str:
    code = secrets.token_urlsafe(32)
    cache.set(f"{EXCHANGE_PREFIX}{code}", str(user.pk), timeout=settings.AUTH_EXCHANGE_CODE_TTL)
    return code


def redeem_exchange_code(code: str) -> User | None:
    key = f"{EXCHANGE_PREFIX}{code}"
    user_id = cache.get(key)
    if not user_id or not cache.delete(key):  # delete() == False: already redeemed
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


def issue_tokens(user: User) -> TokenPair:
    refresh = RefreshToken.for_user(user)
    refresh[TOKEN_VERSION_CLAIM] = user.token_version
    return TokenPair(access=str(refresh.access_token), refresh=str(refresh))


def rotate_refresh_token(raw_refresh: str) -> tuple[User, TokenPair]:
    try:
        token = RefreshToken(raw_refresh)  # type: ignore[arg-type]
    except TokenError as exc:
        raise InvalidSession("Invalid or expired session") from exc
    user = User.objects.filter(pk=token.get("user_id"), is_active=True).first()
    if user is None or token.get(TOKEN_VERSION_CLAIM) != user.token_version:
        raise InvalidSession("Session revoked")
    return user, issue_tokens(user)


def revoke_all_sessions(user: User) -> None:
    User.objects.filter(pk=user.pk).update(token_version=F("token_version") + 1)
    user.refresh_from_db(fields=["token_version"])
