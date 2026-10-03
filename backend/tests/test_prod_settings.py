"""Production settings refuse development secrets and force HTTPS-only behaviour (no MongoDB).

Each case imports the settings module in a fresh interpreter so the test settings stay intact.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
GOOD = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "TOKEN_ENCRYPTION_KEYS": "fake-key-checked-only-when-used",
    "GITHUB_CLIENT_ID": "id",
    "GITHUB_CLIENT_SECRET": "secret",
    "FRONTEND_URL": "https://repoguide.example.com",
}
PRINT = (
    "import logging; import config.settings.prod as s; "
    "print(s.DEBUG, s.SECURE_SSL_REDIRECT, s.AUTH_COOKIE_SECURE, s.SESSION_COOKIE_SECURE, "
    "s.CSRF_COOKIE_SECURE, s.SECURE_PROXY_SSL_HEADER[0], s.SECURE_HSTS_SECONDS, "
    "logging.getLogger('django.security.DisallowedHost').level)"
)


def run(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in GOOD and k != "DJANGO_DEBUG"}
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", PRINT], cwd=BACKEND, env=env, capture_output=True, text=True
    )


def test_production_settings_are_secure() -> None:
    result = run({**GOOD, "DJANGO_DEBUG": "true"})  # ignored in production
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["False", "True", "True", "True", "True",
                                     "HTTP_X_FORWARDED_PROTO", "0", "50"]  # fmt: skip


def test_production_settings_refuse_development_secrets() -> None:
    result = run({"FRONTEND_URL": "http://localhost:5173"})
    assert result.returncode != 0
    for problem in ("DJANGO_SECRET_KEY", "TOKEN_ENCRYPTION_KEYS", "GITHUB_CLIENT_ID",
                    "FRONTEND_URL must be the public https://"):  # fmt: skip
        assert problem in result.stderr
