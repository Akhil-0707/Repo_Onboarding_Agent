"""Development only: record the API responses a user sees for one repository.

The output (JSON: request path -> response body) lets the frontend's screenshot script replay a
real analysis in the real UI without a running backend or a signed-in browser
(``npm run screenshots``). Responses are produced by the actual views, in-process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.repos.models import UserRepository


def _paths(value: Any) -> set[str]:
    """Every ``path`` mentioned in a section/message payload."""
    found: set[str] = set()
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str) and not path.endswith("/"):
            found.add(path)
        for key, item in value.items():
            if key == "paths" and isinstance(item, list):
                found.update(p for p in item if isinstance(p, str) and not p.endswith("/"))
            else:
                found |= _paths(item)
    elif isinstance(value, list):
        for item in value:
            found |= _paths(item)
    return found


class Command(BaseCommand):
    help = "DEBUG only: record a repository's API responses for the screenshot script."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")
        parser.add_argument("repo", help="owner/name of a repository on the user's dashboard")
        parser.add_argument("--out", required=True, help="Output JSON file")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("export_snapshot only works with DEBUG on (local development).")
        user = User.objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"No user named '{options['username']}'.")
        owner, _, name = options["repo"].partition("/")
        link = (
            UserRepository.objects.select_related("repository")
            .filter(user=user, repository__owner__iexact=owner, repository__name__iexact=name)
            .order_by("-created_at")
            .first()
        )
        if link is None:
            raise CommandError(f"{options['repo']} is not on @{user.username}'s dashboard.")
        repo_id = str(link.repository.pk)

        client = APIClient(SERVER_NAME="localhost")
        client.force_authenticate(user)
        responses: dict[str, Any] = {}

        def get(path: str) -> Any:
            response = client.get(path)
            if response.status_code != 200:
                raise CommandError(f"GET {path} returned {response.status_code}")
            responses[path] = response.json()
            return responses[path]

        base = f"/api/repos/{repo_id}"
        get("/api/repos")
        get(base)
        get(f"{base}/job")
        analysis = get(f"{base}/analysis")
        get(f"{base}/tree")
        get("/api/usage")
        cited = _paths(analysis)
        threads = get(f"{base}/threads")["results"]
        for thread in threads[:3]:
            detail = get(f"{base}/threads/{thread['id']}")
            cited |= _paths(detail["messages"])
        for path in sorted(cited):
            get(f"{base}/files?{urlencode({'path': path})}")

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"repo_id": repo_id, "responses": responses}, indent=1), encoding="utf-8"
        )
        self.stdout.write(f"Recorded {len(responses)} responses for {options['repo']} -> {out}")
