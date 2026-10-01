from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.search.indexes import ensure_search_indexes


class Command(BaseCommand):
    help = "Create/update the Atlas Vector Search and Atlas Search indexes on code_chunks."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--wait", action="store_true", help="Block until queryable")
        parser.add_argument("--timeout", type=float, default=180.0)

    def handle(self, *args: Any, **options: Any) -> None:
        actions = ensure_search_indexes(wait=options["wait"], timeout=options["timeout"])
        summary = ", ".join(f"{name}: {action}" for name, action in actions.items())
        self.stdout.write(self.style.SUCCESS(f"Search indexes: {summary}"))
