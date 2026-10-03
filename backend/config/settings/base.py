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


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me-0123456789")
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
    "apps.repos",
    "apps.ingestion",
    "apps.search",
    "apps.agents",
    "apps.analysis",
    "apps.chat",
    "apps.usage",
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
    "resume-waiting-analyses": {
        "task": "apps.analysis.tasks.resume_waiting_analyses",
        "schedule": env_float("ANALYSIS_RESUME_SECONDS", 60.0),
    },
    "sweep-stale-jobs": {
        "task": "apps.ingestion.tasks.sweep_stale_jobs",
        "schedule": env_float("INGEST_SWEEP_SECONDS", 300.0),
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
        "apps.accounts.authentication.VersionedJWTAuthentication",
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

# --- GitHub OAuth / auth cookies ---------------------------------------------------------
GITHUB_CLIENT_ID = env("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = env("GITHUB_CLIENT_SECRET", "")
# Default goes through the frontend origin (Vite proxy / nginx) so cookies stay same-origin.
GITHUB_OAUTH_REDIRECT_URI = env(
    "GITHUB_OAUTH_REDIRECT_URI", f"{FRONTEND_URL}/api/auth/github/callback"
)
# Comma-separated Fernet keys; first encrypts, all decrypt (rotation). Required unless DEBUG.
TOKEN_ENCRYPTION_KEYS = env_list("TOKEN_ENCRYPTION_KEYS", "")
AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", not DEBUG)
AUTH_REFRESH_COOKIE = "rg_refresh"
AUTH_REFRESH_COOKIE_PATH = "/api/auth/"
AUTH_OAUTH_STATE_COOKIE = "rg_oauth"
AUTH_EXCHANGE_CODE_TTL = 60
# Cookie-authenticated endpoints (refresh, logout) require this header: browsers cannot add
# custom headers to cross-site form posts, so it acts as CSRF protection.
AUTH_CLIENT_HEADER = "X-RepoGuide-Client"

SPECTACULAR_SETTINGS = {
    "TITLE": "RepoGuide API",
    "DESCRIPTION": "Onboard developers onto any GitHub codebase.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
}

# --- Ingestion ---------------------------------------------------------------------------
INGEST_MAX_REPO_MB = env_int("INGEST_MAX_REPO_MB", 200)
INGEST_MAX_FILES = env_int("INGEST_MAX_FILES", 5000)
INGEST_MAX_FILE_KB = env_int("INGEST_MAX_FILE_KB", 500)
INGEST_CLONE_TIMEOUT = env_int("INGEST_CLONE_TIMEOUT", 300)
INGEST_WORKDIR = env("INGEST_WORKDIR", "")  # empty: system temp dir
INGEST_STALE_MINUTES = env_int("INGEST_STALE_MINUTES", 30)  # running job with no progress
INGEST_QUEUED_TIMEOUT_MINUTES = env_int("INGEST_QUEUED_TIMEOUT_MINUTES", 360)
# Private repositories: re-confirm the user's GitHub access this often; if GitHub is down,
# serve cached results for up to the grace period after the last confirmation.
PRIVATE_ACCESS_RECHECK_HOURS = env_int("PRIVATE_ACCESS_RECHECK_HOURS", 6)
PRIVATE_ACCESS_GRACE_HOURS = env_int("PRIVATE_ACCESS_GRACE_HOURS", 168)
GITHUB_API_URL = env("GITHUB_API_URL", "https://api.github.com")

# --- Embeddings & search -----------------------------------------------------------------
# "local": sentence-transformers on CPU in the worker; "openai": any OpenAI-compatible endpoint.
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", "local")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIMENSIONS = env_int("EMBEDDING_DIMENSIONS", 384)
EMBEDDING_BATCH_SIZE = env_int("EMBEDDING_BATCH_SIZE", 64)
EMBEDDING_MAX_RETRIES = env_int("EMBEDDING_MAX_RETRIES", 3)
EMBEDDING_THREADS = env_int("EMBEDDING_THREADS", 0)  # 0 = torch default
# bge models expect this instruction on short retrieval queries (not on documents).
EMBEDDING_QUERY_PREFIX = env(
    "EMBEDDING_QUERY_PREFIX", "Represent this sentence for searching relevant passages: "
)
EMBEDDING_DOCUMENT_PREFIX = env("EMBEDDING_DOCUMENT_PREFIX", "")
EMBEDDING_BASE_URL = env("EMBEDDING_BASE_URL", "")
EMBEDDING_API_KEY = env("EMBEDDING_API_KEY", "")
SEARCH_VECTOR_INDEX = "chunks_vector"
SEARCH_TEXT_INDEX = "chunks_text"
SEARCH_RRF_K = env_int("SEARCH_RRF_K", 60)

# --- Analysis agent ----------------------------------------------------------------------
ANALYSIS_MAX_ITERATIONS = env_int("ANALYSIS_MAX_ITERATIONS", 6)
ANALYSIS_TOKEN_BUDGET = env_int("ANALYSIS_TOKEN_BUDGET", 300_000)
ANALYSIS_MAX_REPAIRS = env_int("ANALYSIS_MAX_REPAIRS", 2)
ANALYSIS_MAX_CONTEXT_CHARS = env_int("ANALYSIS_MAX_CONTEXT_CHARS", 40_000)
ANALYSIS_MAX_WAIT_HOURS = env_int("ANALYSIS_MAX_WAIT_HOURS", 48)

# Q&A chat agent
CHAT_MAX_ITERATIONS = env_int("CHAT_MAX_ITERATIONS", 5)
CHAT_TOKEN_BUDGET = env_int("CHAT_TOKEN_BUDGET", 60_000)  # per answer
CHAT_MAX_CONTEXT_CHARS = env_int("CHAT_MAX_CONTEXT_CHARS", 36_000)
CHAT_ANSWER_MAX_TOKENS = env_int("CHAT_ANSWER_MAX_TOKENS", 1500)
CHAT_HISTORY_TURNS = env_int("CHAT_HISTORY_TURNS", 4)  # older turns are summarised
CHAT_MAX_QUESTION_CHARS = env_int("CHAT_MAX_QUESTION_CHARS", 4000)

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
