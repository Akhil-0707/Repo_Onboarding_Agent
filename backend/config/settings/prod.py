"""Production settings: HTTPS-only cookies and redirects, and no start with development secrets.

Select with ``DJANGO_SETTINGS_MODULE=config.settings.prod`` (``docker-compose.prod.yml`` does).
TLS is expected to end at a reverse proxy that sets ``X-Forwarded-Proto``; see
``docs/deployment.md``.
"""

import logging

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import (
    FRONTEND_URL,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    SECRET_KEY,
    TOKEN_ENCRYPTION_KEYS,
    env_bool,
    env_int,
)

DEBUG = False  # never from the environment: DEBUG also enables `login_link`

_problems = []
if SECRET_KEY.startswith("dev-insecure") or len(SECRET_KEY) < 50:
    _problems.append("DJANGO_SECRET_KEY must be a random value of at least 50 characters")
if not TOKEN_ENCRYPTION_KEYS:
    _problems.append("TOKEN_ENCRYPTION_KEYS must hold at least one Fernet key")
if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
    _problems.append("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are required to sign in")
if not FRONTEND_URL.startswith("https://"):
    _problems.append("FRONTEND_URL must be the public https:// address of the site")
if _problems:
    raise ImproperlyConfigured("Production settings: " + "; ".join(_problems) + ".")

# TLS ends at the reverse proxy, which tells Django the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_REDIRECT_EXEMPT = [r"^api/health$"]  # container health checks speak plain HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
AUTH_COOKIE_SECURE = True
# HSTS is opt-in: once browsers have seen it they refuse plain HTTP for this long.
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)

# Scanners send arbitrary Host headers; Django answers 400 anyway, so skip the traceback.
logging.getLogger("django.security.DisallowedHost").setLevel(logging.CRITICAL)
