from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.llm.config import KEY_BASE_URL, KEY_MODEL, normalize_base_url, set_runtime_value
from apps.llm.health import check_llm_health


class Command(BaseCommand):
    help = (
        "Point RepoGuide at a new model server URL (e.g. a fresh Kaggle tunnel) without "
        "restarting containers. '/v1' is appended if missing."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("url", help="Base URL, e.g. https://abc.trycloudflare.com")
        parser.add_argument("--model", help="Optionally override the served model name")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            base_url = normalize_base_url(options["url"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        set_runtime_value(KEY_BASE_URL, base_url)
        if options.get("model"):
            set_runtime_value(KEY_MODEL, options["model"])
        self.stdout.write(self.style.SUCCESS(f"LLM base URL set to {base_url}"))

        status = check_llm_health(force=True)
        if status.online:
            self.stdout.write(
                self.style.SUCCESS(f"Model '{status.model}' is online ({status.latency_ms} ms).")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Saved, but the model is not reachable yet: {status.error}. "
                    "Waiting jobs resume automatically once it is."
                )
            )
