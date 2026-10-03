"""Development only: print a one-time sign-in link for a local user.

Uses the same single-use exchange code as the GitHub OAuth callback (valid for
``AUTH_EXCHANGE_CODE_TTL`` seconds), so a local stack can be explored without registering a
GitHub OAuth app. Refuses to run unless ``DEBUG`` is on.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services import create_exchange_code


class Command(BaseCommand):
    help = "DEBUG only: print a one-time sign-in link (creates the user if missing)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username", nargs="?", default="dev")
        parser.add_argument("--next", default="/dashboard", help="Page to open after sign-in")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("login_link only works with DEBUG on (local development).")
        user, created = User.objects.get_or_create(username=options["username"])
        if created:
            user.set_unusable_password()
            user.save()
        query = urlencode({"code": create_exchange_code(user), "next": options["next"]})
        ttl = settings.AUTH_EXCHANGE_CODE_TTL
        self.stdout.write(
            f"Open within {ttl} seconds (single use) to sign in as @{user.username}:\n"
            f"{settings.FRONTEND_URL}/auth/callback?{query}"
        )
