"""Encryption at rest for GitHub OAuth tokens.

``TOKEN_ENCRYPTION_KEYS`` is a comma-separated list of Fernet keys: the first encrypts, all of
them decrypt, so keys can be rotated by prepending a new one.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.common.logging import get_logger

logger = get_logger(__name__)


class TokenDecryptionError(Exception):
    """Stored ciphertext could not be decrypted (wrong/rotated-out key or tampering)."""


def _derive_dev_key(secret: str) -> bytes:
    digest = hashlib.sha256(f"repoguide-token-key:{secret}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...], fallback_secret: str) -> MultiFernet:
    if keys:
        try:
            return MultiFernet([Fernet(key.encode()) for key in keys])
        except ValueError as exc:
            raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEYS contains an invalid key") from exc
    if not settings.DEBUG:
        raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEYS must be set outside of DEBUG mode")
    logger.warning("token_encryption_dev_key", detail="deriving key from SECRET_KEY (dev only)")
    return MultiFernet([Fernet(_derive_dev_key(fallback_secret))])


def _cipher() -> MultiFernet:
    return _fernet(tuple(settings.TOKEN_ENCRYPTION_KEYS), settings.SECRET_KEY)


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError("Stored token cannot be decrypted") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode()
