from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A RepoGuide user. Accounts are created through GitHub OAuth (Phase 2)."""

    github_id = models.BigIntegerField(null=True, blank=True, unique=True)
    avatar_url = models.URLField(blank=True, default="")
    # Fernet ciphertext of the GitHub OAuth token. Never serialised, never logged.
    github_token_encrypted = models.TextField(blank=True, default="")
    github_scopes = models.CharField(max_length=255, blank=True, default="")
    # Bumped on logout: every JWT carries the version it was issued with, so bumping it
    # revokes all outstanding access and refresh tokens without a blacklist table.
    token_version = models.PositiveIntegerField(default=0)

    @property
    def github_connected(self) -> bool:
        return bool(self.github_token_encrypted)

    @property
    def has_private_repo_access(self) -> bool:
        return "repo" in self.github_scopes.split()

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.username
