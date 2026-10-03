from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.llm.config import (
    KEY_BASE_URL,
    KEY_MODEL,
    clear_runtime_value,
    normalize_base_url,
    set_runtime_value,
)
from apps.llm.health import check_llm_health


class Command(BaseCommand):
    help = (
        "Point RepoGuide at a new model server URL (e.g. a fresh Kaggle tunnel) without "
        "restarting containers. '/v1' is appended if missing. Without --model, the model comes "
        "from LLM_MODEL, or is the server's only model if it serves exactly one."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("url", help="Base URL, e.g. https://abc.trycloudflare.com")
        parser.add_argument("--model", help="Model name to use on this server")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            base_url = normalize_base_url(options["url"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        set_runtime_value(KEY_BASE_URL, base_url)
        model = options.get("model")
        if model:
            set_runtime_value(KEY_MODEL, model)
        else:
            # A new server: never keep a model chosen for the previous one.
            clear_runtime_value(KEY_MODEL)
        self.stdout.write(self.style.SUCCESS(f"LLM base URL set to {base_url}"))

        status = check_llm_health(force=True)
        if not status.online and not model and len(status.served_models) == 1:
            only = status.served_models[0]
            set_runtime_value(KEY_MODEL, only)
            self.stdout.write(
                f"'{status.model}' is not served here; using its only model, '{only}'."
            )
            status = check_llm_health(force=True)

        if status.online:
            self.stdout.write(
                self.style.SUCCESS(f"Model '{status.model}' is online ({status.latency_ms} ms).")
            )
            return
        hint = ""
        if status.error in {"HTTP 401", "HTTP 403"}:
            hint = (
                " The server rejected the API key: set LLM_API_KEY in .env to the server's key "
                "(the VLLM_API_KEY Kaggle secret), then run `docker compose up -d`."
            )
            if not settings.LLM_API_KEY:
                hint += " LLM_API_KEY is currently empty."
        elif status.served_models:
            hint = f" It serves: {', '.join(status.served_models[:10])}. Pass --model."
        self.stdout.write(
            self.style.WARNING(
                f"Saved, but the model is not reachable yet: {status.error}.{hint} "
                "Waiting jobs resume automatically once it is."
            )
        )
