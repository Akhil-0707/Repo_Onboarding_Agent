from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

TOKEN_VERSION_CLAIM = "ver"  # noqa: S105 - claim name, not a secret


class VersionedJWTAuthentication(JWTAuthentication):
    """JWT auth that rejects tokens issued before the user's last logout."""

    def get_user(self, validated_token: Any) -> Any:
        user = super().get_user(validated_token)
        if validated_token.get(TOKEN_VERSION_CLAIM) != user.token_version:
            raise AuthenticationFailed("Session expired. Please sign in again.", code="revoked")
        return user
