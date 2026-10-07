# Deploying RepoGuide

This guide runs RepoGuide on one Linux host with Docker Compose, behind a reverse proxy that
terminates HTTPS. `docker-compose.yml` is for development only (source mounts, auto-reload,
dev dependencies, published database ports); production uses
[`docker-compose.prod.yml`](../docker-compose.prod.yml) and the settings module
`config.settings.prod`.

## What runs

| Service | Role | Notes |
|---|---|---|
| `frontend` | nginx: the built React app, and a proxy for `/api/` | The only published port (HTTP, bound to `127.0.0.1:8080` by default). Streams SSE unbuffered. |
| `backend` | uvicorn (ASGI): REST API, SSE progress and chat streams | Runs migrations and creates indexes on every start. Chat answers run in threads of this process. Loads the embedding model at startup. |
| `worker` | Celery: clone, parse, embed, analyse | Needs `git`, outbound HTTPS to GitHub and the model server, and temp disk for shallow clones. Each process loads the embedding model. |
| `beat` | Celery beat: model health probe (30 s), resume analyses waiting for the model (60 s), stale-job sweeper (5 min) | Run **exactly one**. |
| `mongo` | Application data, code chunks, vectors | Must support **Atlas Search and Vector Search** (`$search`, `$vectorSearch`). |
| `redis` | Celery broker, cache, rate-limit history, live progress pub/sub | Disposable: see [Data and backups](#data-and-backups). |
| model server | Any OpenAI-compatible endpoint with tool calling (vLLM recommended) | Not part of the stack. See [Model server](#model-server). |

## 1. Prepare

1. **A host** with Docker Engine and the Compose plugin, a DNS name pointing at it, and ports
   80/443 open for the reverse proxy. Measured memory for the stack is under
   [Sizing](#sizing).
2. **A GitHub OAuth App** (<https://github.com/settings/developers>):
   - Homepage URL: `https://repoguide.example.com`
   - Authorization callback URL: `https://repoguide.example.com/api/auth/github/callback`
3. **The environment file.** On the server:
   ```bash
   cp .env.production.example .env
   ```
   Fill in every value in `.env`. The production settings refuse to start without a strong
   `DJANGO_SECRET_KEY` (50+ characters), `TOKEN_ENCRYPTION_KEYS`, the GitHub OAuth credentials
   and an `https://` `FRONTEND_URL`, and say which one is missing. Keep `localhost` in
   `DJANGO_ALLOWED_HOSTS`: the backend health check uses it. Tuning options (agent limits,
   embeddings, job timeouts) are documented in [`.env.example`](../.env.example).

## 2. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

`frontend` starts once `backend` reports healthy. On first start:

- the backend creates collections, indexes and the Atlas Search / Vector Search indexes. The
  search indexes build in the background; until they are queryable, search falls back to
  whichever side is ready;
- the embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB) is downloaded once into the
  `hf_cache` volume.

Check it with the smoke test, on the server (it talks to the nginx port directly, so it works
before the HTTPS proxy is set up):

```bash
scripts/prod-smoke-test.sh repoguide.example.com --sse
```

It checks the app page and asset caching, service health, the HTTP-to-HTTPS redirect, that data
needs a signed-in user, that unknown hosts are refused, that the admin and development sign-in
links are unavailable and, with `--sse`, that progress events stream through nginx live (it
creates a temporary user and job and deletes them). CI runs the same script against a freshly
built production stack on every push.

## 3. HTTPS and the reverse proxy

Put a TLS-terminating proxy in front of `frontend` (host nginx, Caddy, Traefik, a cloud load
balancer). Whatever you use, it must:

- send `X-Forwarded-Proto: https` and the original `Host` header. Django uses them to tell the
  request was HTTPS; without the header every API call is redirected to HTTPS again (a loop);
- **not buffer** `text/event-stream` responses (ingestion progress and chat answers stream);
- allow idle connections of at least 30 s (the streams send a keep-alive comment every 15 s,
  and a chat answer can take a minute or more).

Example for nginx on the host:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name repoguide.example.com;
    ssl_certificate     /etc/letsencrypt/live/repoguide.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/repoguide.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_read_timeout 1h;
    }
}

server {
    listen 80;
    server_name repoguide.example.com;
    return 301 https://$host$request_uri;
}
```

Once HTTPS works for every page, consider HSTS: set `SECURE_HSTS_SECONDS=3600`, check the site,
then raise it (e.g. `31536000`). Browsers remember HSTS, so a mistake is hard to undo.

## Model server

The Kaggle notebook in [`kaggle/`](../kaggle/README.md) is a free demo setup: its sessions end
and the tunnel URL changes every time. For production, run the model on a server that stays up
and give it a stable HTTPS URL and an API key. The settings that RepoGuide is tested with
(see `kaggle/serve_model.py`):

```bash
vllm serve Qwen/Qwen3-8B --served-model-name Qwen/Qwen3-8B \
  --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser hermes \
  --api-key "$VLLM_API_KEY"
```

Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` in `.env`. A URL saved with
`manage.py set_llm_url` is stored in the database and **overrides** `LLM_BASE_URL`; to switch
servers later, use the command again:

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py set_llm_url https://llm.example.com/v1
```

The app keeps working while the model is offline: repositories are still ingested and
browsable, analyses wait (`waiting_for_model`) and resume automatically for up to
`ANALYSIS_MAX_WAIT_HOURS` (48), and chat is disabled with a banner.

## Data and backups

- **MongoDB holds everything that matters**: users (with encrypted GitHub tokens), repositories
  and analyses, file contents, chunks and vectors, chat threads, agent logs. Back up the
  `MONGODB_DB` database regularly, e.g.
  `docker compose -f docker-compose.prod.yml exec mongo mongodump --username repoguide --password '<password>' --authenticationDatabase admin --db repoguide --archive > repoguide.archive`.
  Search indexes are recreated by the backend on start.
- **Keep `TOKEN_ENCRYPTION_KEYS` with the backup.** Without the key, stored GitHub tokens cannot
  be decrypted and users must sign in again.
- **Redis can be lost** without losing data: queued tasks disappear (the sweeper fails jobs
  stuck in the queue after `INGEST_QUEUED_TIMEOUT_MINUTES`, and **Re-analyze** restarts them),
  rate-limit counters reset, and users keep their sessions (refresh tokens are signed JWTs).
- **The bundled `mongodb-atlas-local` image** is the simplest way to get Atlas Search on one
  host, but MongoDB positions it for development and testing. For important data, use MongoDB
  Atlas: set `MONGODB_URI` in `.env` and remove the `mongo` service and the
  `depends_on: mongo` entries from `docker-compose.prod.yml`.

## Security checklist

- `config.settings.prod` forces `DEBUG` off whatever the environment says. That also disables
  the development-only `login_link` and `export_snapshot` commands.
- Cookies are HTTPS-only (refresh token, CSRF, session) and plain HTTP is redirected
  (`SECURE_SSL_REDIRECT`; `/api/health` is exempt for container health checks).
- Only `/api/` reaches Django through nginx: the Django admin is not exposed. Use management
  commands (`docker compose ... exec backend python manage.py ...`) for operations.
- The OpenAPI schema and docs (`/api/schema/`, `/api/docs/`) are public: they describe the
  endpoints, not data. Every data endpoint requires a signed-in user.
- Requests with a `Host` that is not in `DJANGO_ALLOWED_HOSTS` get `400` and are not logged
  (scanners send them constantly).
- MongoDB and Redis are not published on the host. If you use external ones, require
  authentication and TLS.
- Analysed repositories are untrusted input: they are shallow-cloned without hooks, symlinks,
  submodules or LFS, never executed, size-limited (`INGEST_MAX_*`) and deleted after ingestion.
  The worker still downloads arbitrary content, so keep it on a host with nothing else
  sensitive.
- Secrets live only in `.env` (mode `600`, owned by the deploy user). Rotate
  `TOKEN_ENCRYPTION_KEYS` by putting the new key first and keeping the old ones after it.
  Changing `JWT_SIGNING_KEY` signs everyone out.
- Logs are JSON, with tokens and keys redacted.

## Operations

- **Health:** `GET /api/health` (MongoDB + Redis) and `GET /api/llm/health` (model server).
- **Logs:** `docker compose -f docker-compose.prod.yml logs -f backend worker`.
- **Upgrade:** `git pull`, then `docker compose -f docker-compose.prod.yml up -d --build`.
  Migrations and index changes run when the backend starts. Running analyses checkpoint and
  continue after a worker restart (re-enqueue with **Re-analyze** if a job was stopped).
- **Scale ingestion:** raise `CELERY_CONCURRENCY` or run more workers
  (`up -d --scale worker=2`). Keep one `beat` and one `backend` (the backend runs migrations at
  start). Every worker process holds its own copy of the embedding model.
- **Limits:** `RATE_LIMIT_NEW_ANALYSES` (5/hour) and `RATE_LIMIT_CHAT_QUESTIONS` (30/hour) per
  user. One model server answers everyone, so lower the chat limit if answers queue up.

## Sizing

Measured on 2026-10-03 on the development stack after analysing three repositories, including
`tj/commander.js` and `pallets/itsdangerous` (the production stack at idle used the same or
less):

| Component | Memory |
|---|---|
| `backend` (embedding model loaded) | ~430 MiB |
| `worker`, per process that has embedded code | ~600 MiB peak (the default `CELERY_CONCURRENCY=2` means two such processes) |
| `beat` | ~140 MiB |
| `mongo` (atlas-local, including the search process) | ~1.3 GiB |
| `redis` | ~25 MiB |
| `frontend` (nginx) | ~16 MiB |

Plan for **4 GB of RAM as a minimum and 8 GB to be comfortable**, 2+ CPU cores (embedding runs on
the CPU), and disk for the ~2.4 GB backend image plus MongoDB data (300 MB for those three
repositories). The model server needs its own GPU machine: Qwen3-8B in fp16 ran on 2× T4
(16 GB each) with tensor parallelism.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Backend exits with `ImproperlyConfigured: Production settings: …` | A required value in `.env` is missing or still a development value; the message names it. |
| `400 Bad Request` from every API call | The public host name is not in `DJANGO_ALLOWED_HOSTS`. |
| API calls redirect to themselves forever | The proxy does not send `X-Forwarded-Proto: https`. |
| GitHub sign-in fails with "redirect_uri is not associated" | The OAuth App's callback URL differs from `{FRONTEND_URL}/api/auth/github/callback`. |
| Progress or chat answers appear all at once at the end | A proxy buffers `text/event-stream`; disable buffering for `/api/`. |
| "The AI model is offline" | `GET /api/llm/health` shows the error; check `LLM_BASE_URL`/`LLM_API_KEY`, or a URL stored by `set_llm_url`. |
| Search finds nothing right after the first start | Search indexes are still building; `docker compose ... logs backend` shows their status. |
