from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.ingestion.index_store import ensure_indexes


class Command(BaseCommand):
    help = "Create MongoDB indexes for the PyMongo-managed collections (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        names = ensure_indexes()
        self.stdout.write(self.style.SUCCESS(f"Indexes ensured: {', '.join(names)}"))
