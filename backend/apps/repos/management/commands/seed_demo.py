"""Analyse a small public repository as a demo user so it is cached for everyone.

Anyone who then analyses the same URL gets the finished result instantly (a cache hit, free of
the rate limit). ``GITHUB_API_TOKEN`` (optional) is stored, encrypted, on the demo user only, so
seeding is not throttled by GitHub's anonymous limit of 60 requests per hour.
"""

from __future__ import annotations

import os
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.crypto import encrypt_token
from apps.accounts.models import User
from apps.common.errors import ApiError
from apps.repos.models import TERMINAL_JOB_STATUSES, IngestionJob, JobStatus, UserRepository
from apps.repos.services import start_analysis

DEFAULT_REPO = "https://github.com/pallets/itsdangerous"


class Command(BaseCommand):
    help = "Seed a demo analysis (cached for every user) and optionally add it to dashboards."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--repo", default=DEFAULT_REPO, help=f"Default: {DEFAULT_REPO}")
        parser.add_argument("--username", default="demo", help="Demo user (created if missing)")
        parser.add_argument(
            "--add-to",
            action="append",
            default=[],
            metavar="USERNAME",
            help="Also put the repository on this existing user's dashboard (repeatable)",
        )
        parser.add_argument("--wait", action="store_true", help="Follow the job until it ends")
        parser.add_argument("--timeout", type=int, default=1800, help="Seconds to wait (--wait)")

    def handle(self, *args: Any, **options: Any) -> None:
        others = []
        for name in options["add_to"]:
            other = User.objects.filter(username=name).first()
            if other is None:
                raise CommandError(f"No user named '{name}'.")
            others.append(other)

        user, created = User.objects.get_or_create(
            username=options["username"], defaults={"first_name": "Demo"}
        )
        if created:
            user.set_unusable_password()
        token = os.environ.get("GITHUB_API_TOKEN", "").strip()
        if token:
            user.github_token_encrypted = encrypt_token(token)
        user.save()

        try:
            result = start_analysis(user, options["repo"])  # operators are not rate-limited
        except ApiError as exc:
            raise CommandError(str(exc.detail)) from exc
        repo = result.repository
        for other in others:
            UserRepository.objects.get_or_create(user=other, repository=repo)
            self.stdout.write(f"Added {repo.full_name} to @{other.username}'s dashboard.")

        if result.cached:
            self.stdout.write(self.style.SUCCESS(f"{repo} is already analysed (cached)."))
            return
        job = result.job
        self.stdout.write(f"Started {repo} (job {job.pk if job else '-'}).")
        if options["wait"] and job is not None:
            self._follow(str(job.pk), options["timeout"])

    def _follow(self, job_id: str, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            job = IngestionJob.objects.get(pk=job_id)
            running = next((s for s in job.steps if s["status"] in {"running", "waiting"}), None)
            line = f"{job.status} {job.progress}%" + (f" - {running['label']}" if running else "")
            if line != last:
                self.stdout.write(line)
                last = line
            if job.status in TERMINAL_JOB_STATUSES or job.status == JobStatus.WAITING_FOR_MODEL:
                if job.status == JobStatus.FAILED:
                    raise CommandError(f"Analysis failed: {job.error}")
                if job.status == JobStatus.WAITING_FOR_MODEL:
                    self.stdout.write(
                        "The code is indexed; the AI analysis waits for the model server and "
                        "resumes automatically."
                    )
                self.stdout.write(self.style.SUCCESS("Demo repository ready."))
                return
            time.sleep(2)
        raise CommandError(f"Still running after {timeout} s; check the dashboard.")
