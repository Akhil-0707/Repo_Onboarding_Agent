#!/bin/sh
set -e

role="${1:-web}"

case "$role" in
  web)
    python manage.py migrate --noinput
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
      ${UVICORN_RELOAD:+--reload} --proxy-headers
    ;;
  worker)
    exec celery -A config worker --loglevel "${LOG_LEVEL:-INFO}" \
      --concurrency "${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A config beat --loglevel "${LOG_LEVEL:-INFO}" \
      --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
