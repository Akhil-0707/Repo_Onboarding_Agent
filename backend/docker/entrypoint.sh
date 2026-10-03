#!/bin/sh
set -e

role="${1:-web}"

# Dev only (CELERY_RELOAD set): run Celery under watchfiles so it restarts when
# Python files under /app change. Otherwise Celery runs directly.
run_celery() {
  if [ -n "$CELERY_RELOAD" ]; then
    exec watchfiles --filter python "$*" /app
  fi
  exec "$@"
}

case "$role" in
  web)
    python manage.py migrate --noinput
    python manage.py ensure_indexes
    python manage.py ensure_search_indexes || echo "search indexes not ready yet; search degrades until they are"
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
      ${UVICORN_RELOAD:+--reload} --proxy-headers
    ;;
  worker)
    run_celery celery -A config worker --loglevel "${LOG_LEVEL:-INFO}" \
      --concurrency "${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    run_celery celery -A config beat --loglevel "${LOG_LEVEL:-INFO}" \
      --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
