#!/bin/sh
# Smoke test for a running docker-compose.prod.yml stack, run on the host it runs on:
#
#   scripts/prod-smoke-test.sh <public host name> [--sse]
#
# It talks to the frontend container directly (HTTP_BIND:HTTP_PORT, default 127.0.0.1:8080),
# so no TLS proxy is needed. --sse also checks that progress events stream through nginx without
# buffering; it creates a temporary user, repository and job, and deletes them again.
# COMPOSE overrides the compose command (default: docker compose -f docker-compose.prod.yml).
set -eu

HOST="${1:?usage: $0 <public host name> [--sse]}"
SSE="${2:-}"
BASE="http://${HTTP_BIND:-127.0.0.1}:${HTTP_PORT:-8080}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
failures=0

check() { # description, expected, actual
    if [ "$2" = "$3" ]; then
        echo "ok   $1"
    else
        echo "FAIL $1: expected '$2', got '$3'"
        failures=$((failures + 1))
    fi
}
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
header() { # name, curl args...
    name="$1"
    shift
    curl -s -o /dev/null -D - "$@" | tr -d '\r' |
        awk -v n="$name" 'tolower($1) == tolower(n) ":" { sub(/^[^:]*: /, ""); print; exit }'
}
https() { curl -s -H "Host: $HOST" -H "X-Forwarded-Proto: https" "$@"; }

echo "Smoke test of $BASE as $HOST"

check "app page" 200 "$(status -H "Host: $HOST" "$BASE/")"
check "app page is revalidated" "no-cache" "$(header Cache-Control -H "Host: $HOST" "$BASE/")"
asset="$(curl -s -H "Host: $HOST" "$BASE/" | grep -o '/assets/[^"]*\.js' | head -n 1)"
check "built asset is cached for good" "public, max-age=31536000, immutable" \
    "$(header Cache-Control -H "Host: $HOST" "$BASE$asset")"

check "service health over plain HTTP" '{"status":"ok","mongo":true,"cache":true}' \
    "$(curl -s -H "Host: $HOST" "$BASE/api/health")"
check "plain HTTP API calls redirect" 301 "$(status -H "Host: $HOST" "$BASE/api/llm/health")"
check "redirect target" "https://$HOST/api/llm/health" \
    "$(header Location -H "Host: $HOST" "$BASE/api/llm/health")"
check "API behind the TLS proxy" 200 "$(https -o /dev/null -w '%{http_code}' "$BASE/api/llm/health")"
check "data needs a signed-in user" 401 "$(https -o /dev/null -w '%{http_code}' "$BASE/api/me")"
check "unknown Host is refused" 400 "$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Host: unknown.invalid" -H "X-Forwarded-Proto: https" "$BASE/api/llm/health")"
admin="$(https "$BASE/admin/" | grep -c 'id="root"' || true)"
check "Django admin is not routed (app page instead)" 1 "$admin"

if $COMPOSE exec -T backend python manage.py login_link smoke-test >/dev/null 2>&1; then
    check "development sign-in links are disabled" refused allowed
else
    check "development sign-in links are disabled" refused refused
fi

if [ "$SSE" = "--sse" ]; then
    # Three progress events 1.5 s apart must each arrive within a second of being sent. The
    # client accepts gzip like a browser does: compressing event streams also holds them back.
    result="$($COMPOSE exec -T backend python manage.py shell -v 0 -c "
import threading, time, urllib.request, zlib
from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.ingestion.progress import JobReporter, initial_steps
from apps.repos.models import IngestionJob, JobStatus, Repository, UserRepository
user = User.objects.create(username='smoke-test-sse', github_id=999999999)
repo = Repository.objects.create(
    url='https://github.com/smoke/test', url_key='github.com/smoke/test#' + '0' * 40,
    owner='smoke', name='test', default_branch='main', commit_sha='0' * 40)
try:
    UserRepository.objects.create(user=user, repository=repo)
    job = IngestionJob.objects.create(
        repository=repo, user=user, status=JobStatus.RUNNING, steps=initial_steps())
    request = urllib.request.Request(
        f'http://frontend/api/repos/{repo.pk}/job/stream',
        headers={'Host': '$HOST', 'X-Forwarded-Proto': 'https', 'Accept-Encoding': 'gzip',
                 'Authorization': 'Bearer ' + issue_tokens(user).access})
    start, arrived = time.time(), []
    def read():
        with urllib.request.urlopen(request, timeout=30) as stream:
            gzipped = stream.headers.get('Content-Encoding') == 'gzip'
            inflate = zlib.decompressobj(16 + zlib.MAX_WBITS)
            text = b''
            while len(arrived) < 3:
                chunk = stream.read1(65536)
                if not chunk:
                    return
                text += inflate.decompress(chunk) if gzipped else chunk
                while len(arrived) < text.count(b'event: log'):
                    arrived.append(time.time() - start)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    time.sleep(1.5)
    reporter, sent = JobReporter(str(job.pk)), []
    for i in range(3):
        reporter.log('clone', f'smoke test {i}')
        sent.append(time.time() - start)
        time.sleep(1.5)
    reader.join(timeout=10)
    lags = [round(a - s, 2) for a, s in zip(arrived, sent)]
    print('live' if len(lags) == 3 and max(lags) < 1.0 else f'buffered {lags}')
finally:
    repo.delete()
    user.delete()
" 2>&1 | tail -n 1)"
    check "progress events stream live through nginx" live "$result"
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed"
    exit 1
fi
echo "All checks passed"
