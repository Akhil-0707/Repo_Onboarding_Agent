from .base import *  # noqa: F403
from .base import DATABASES, MONGODB_DB

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"

DATABASES["default"]["TEST"] = {"NAME": f"test_{MONGODB_DB}"}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

LLM_BASE_URL = "http://llm.invalid/v1"
LLM_API_KEY = "test-key"
LLM_MAX_RETRIES = 1
LLM_BACKOFF_BASE = 0.01
LLM_BACKOFF_MAX = 0.02
LLM_RUNTIME_CONFIG_TTL = 0.0
