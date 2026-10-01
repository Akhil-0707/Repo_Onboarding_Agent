"""Base settings shared by every environment.

All configuration comes from environment variables (see the repo-level ``.env.example``).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from apps.common.logging import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env(name, str(default)))


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")

INSTALLED_APPS = [
    "config.apps.MongoAdminConfig",
    "config.apps.MongoAuthConfig",
    "config.apps.MongoContentTypesConfig",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_mongodb_backend",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.common",
    "apps.accounts",
    "apps.llm",
]

MIDDLEWARE = [
    "apps.common.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Sessions are only used by the Django admin; signed cookies avoid a sessions collection.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- MongoDB -----------------------------------------------------------------------------
MONGODB_URI = env("MONGODB_URI", "mongodb://localhost:27017/?directConnection=true")
MONGODB_DB = env("MONGODB_DB", "repoguide")

DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": MONGODB_URI,
        "NAME": MONGODB_DB,
    },
}
DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --- Redis / cache / Celery --------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "repoguide",
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 60 * 60)
CELERY_BEAT_SCHEDULE = {
    "probe-llm-health": {
        "task": "apps.llm.tasks.probe_llm_health",
        "schedule": env_float("LLM_HEALTH_PROBE_SECONDS", 30.0),
    },
}

# --- Internationalisation / static -------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- HTTP / CORS -------------------------------------------------------------------------
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", FRONTEND_URL)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# --- DRF ---------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.errors.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "new_analysis": env("RATE_LIMIT_NEW_ANALYSES", "5/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "RepoGuide API",
    "DESCRIPTION": "Onboard developers onto any GitHub codebase.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
}

# --- LLM (self-hosted, OpenAI-compatible) ------------------------------------------------
# These are defaults; runtime overrides live in the ``runtime_settings`` collection
# (see ``manage.py set_llm_url``) so the tunnel URL can change without restarts.
LLM_BASE_URL = env("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = env("LLM_API_KEY", "")
LLM_MODEL = env("LLM_MODEL", "Qwen/Qwen3-8B")
LLM_CONNECT_TIMEOUT = env_float("LLM_CONNECT_TIMEOUT", 10.0)
LLM_READ_TIMEOUT = env_float("LLM_READ_TIMEOUT", 120.0)
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 3)
LLM_BACKOFF_BASE = env_float("LLM_BACKOFF_BASE", 1.5)
LLM_BACKOFF_MAX = env_float("LLM_BACKOFF_MAX", 30.0)
LLM_DISABLE_THINKING = env_bool("LLM_DISABLE_THINKING", True)
LLM_GUIDED_JSON = env_bool("LLM_GUIDED_JSON", True)
LLM_HEALTH_TIMEOUT = env_float("LLM_HEALTH_TIMEOUT", 5.0)
LLM_HEALTH_CACHE_SECONDS = env_int("LLM_HEALTH_CACHE_SECONDS", 15)
LLM_RUNTIME_CONFIG_TTL = env_float("LLM_RUNTIME_CONFIG_TTL", 10.0)
LLM_COST_PER_1K_INPUT = env_float("LLM_COST_PER_1K_INPUT", 0.0)
LLM_COST_PER_1K_OUTPUT = env_float("LLM_COST_PER_1K_OUTPUT", 0.0)

# --- Logging -----------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOG_JSON = env_bool("LOG_JSON", True)
LOGGING_CONFIG = None
configure_logging(level=LOG_LEVEL, json=LOG_JSON)
