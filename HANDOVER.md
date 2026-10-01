# RepoGuide — Handover

Living document. Update after every meaningful step. A fresh session should be able to continue from here alone.

## Current status
- **Phase:** 1 ✅ complete. **Next: Phase 2** (GitHub OAuth, JWT, dashboard skeleton).
- **Last commit:** see `git log -1` (Phase 1 closed on 2026-10-01; CI green on `main`).
- **In progress:** nothing; ready to start Phase 2.

## How to run

### Full stack (Docker)
```bash
cp .env.example .env            # fill DJANGO_SECRET_KEY, MONGO_ROOT_PASSWORD, LLM_* values
docker compose up --build       # mongo (atlas-local 8.0), redis, backend, worker, beat, frontend
```
- Frontend http://localhost:5173 (Vite dev; proxies `/api` to the backend)
- API http://localhost:8010 (host port; container port 8000), docs at `/api/docs/`, service health at `/api/health`, model health at `/api/llm/health`
- Point at a new model URL: `docker compose exec backend python manage.py set_llm_url <url>`

### Backend locally (Windows)
```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest          # mongo-marked tests skip if Mongo is not reachable
.venv/Scripts/ruff check . && .venv/Scripts/black --check .
```
- `makemigrations` needs a reachable Mongo (it checks migration history). If Docker is down, run it with
  `MigrationLoader.check_consistent_history` patched to a no-op (that's how the 0001 migrations were generated).

### Frontend locally
```bash
cd frontend && npm install
npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
```

### Model server
See `kaggle/README.md`. The notebook is generated from `kaggle/serve_model.py` by `python kaggle/build_notebook.py`. Edit the `.py`, then regenerate.

## Environment variables
All documented in `.env.example`. Key ones: `DJANGO_SECRET_KEY`, `MONGO_ROOT_USER/PASSWORD`, `MONGODB_DB`,
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_DISABLE_THINKING`, `LLM_GUIDED_JSON`, `RATE_LIMIT_NEW_ANALYSES`.
Settings are read in `backend/config/settings/base.py` via the `env*` helpers.

## Key decisions (and why)
| Decision | Reason |
|---|---|
| Django **5.2 LTS** + `django-mongodb-backend` 5.2.4 | Spec says Django 5.x; backend is GA since 5.2.0; simplejwt supports up to 5.2 |
| Contrib apps via `config/apps.py` Mongo configs + `mongo_migrations/` (from the official project template) | Required by django-mongodb-backend (ObjectId PKs) |
| Signed-cookie sessions, no sessions app | Sessions only serve the admin; avoids an extra collection |
| ORM for app entities, **PyMongo repository layer** (`apps/common/mongo.get_db`) for chunks/blobs/edges/logs | Bulk writes + `$vectorSearch`/`$search` aggregations; shares the backend's client |
| `blobs` collection (content-addressed by git blob SHA), planned for Phase 3 | Clone is deleted after ingestion but the viewer and agent tools need file contents |
| LLM: **Qwen3-8B**, vLLM 0.30.0 (fallback 0.18.1), fp16, TP=2 on Kaggle 2×T4, `hermes` parser | Reliable tool calling, fits T4 memory; T4 has no bf16 |
| `LLMClient` does its own retries (SDK `max_retries=0`) | Bounded, logged retries; terminal `ModelOfflineError` drives "waiting for model" |
| Streams that end without `finish_reason` raise `ModelOfflineError` | A dying tunnel closes the socket cleanly; treat it as an interruption |
| Runtime model URL in `runtime_settings` (10 s TTL cache) | Kaggle tunnel URL changes per session; no container restarts |
| `/api/llm/health` is public, never exposes URL/key | Landing page needs the offline banner before login |
| Log redaction: sensitive keys (non-numeric values) + token-shaped strings | Never leak GitHub/LLM tokens; keep `prompt_tokens` counts readable |
| `redis` pinned to 6.4.0 | kombu (Celery 5.6) caps redis-py below 7 |
| TypeScript **6.0.x** (not 7) | typescript-eslint 8.71 supports TS < 6.1 |
| Embeddings: `BAAI/bge-small-en-v1.5` on CPU (Phase 4) | Fast, no `trust_remote_code`; hybrid search compensates |
| Architecture map: model outputs JSON graph, server renders Mermaid (Phase 6) | Small models often write invalid Mermaid |
| Shiki (not Monaco) for code viewing | Read-only viewer; much lighter |
| Hand-written GitHub OAuth (Phase 2) | Avoids allauth/social-auth model incompatibilities with Mongo |
| SSE via async Django views + fetch-stream on frontend | Needs Authorization header and POST (EventSource can't) |
| `est_cost` from configurable per-1k prices, default 0 | Self-hosted model; tokens + latency are the primary metrics |

## Completed
- **Phase 1:** repo + tracking files; Django/Mongo scaffold; common layer (structlog redaction, request ids, error envelope, pagination); custom User; Celery + beat (LLM health probe); LLMClient (timeouts/retries/backoff/offline, streaming, tool-call assembly); runtime config + `set_llm_url` + admin; `/api/health` and `/api/llm/health`; fake OpenAI-compatible server and 35 backend tests; React shell (router, theme, model banner, API client, state views) with 23 tests; Docker Compose stack; Kaggle notebook/script/guide; CI (all green).

## Known issues / TODOs / blockers
- The vLLM 0.30.0 + T4 combination is unverified (needs a Kaggle run). The documented fallback is 0.18.1.
- Phase 4 will add ML dependencies (sentence-transformers + CPU torch) to the backend image; keep the API image slim if possible (build arg).

## Next steps (Phase 2)
1. `apps/accounts`: GitHub OAuth login/callback views (httpx), state param in a signed cookie, user upsert.
2. Fernet encryption helper (`TOKEN_ENCRYPTION_KEY`, MultiFernet) and add it to `.env.example`.
3. One-time exchange code (cache, 60 s), then issue JWT access + refresh (httpOnly cookie), `/api/auth/refresh`, `/api/auth/logout`, `/api/me`.
4. Frontend: AuthProvider (access token in memory, silent refresh), login button, `/auth/callback` page, protected routes, dashboard skeleton.
5. Tests with mocked GitHub.

## Gotchas
- **Local-only tooling files** are ignored through `.git/info/exclude`, never via the shared `.gitignore`.
- The project lives under OneDrive: `node_modules` stays in a Docker named volume; Vite uses polling inside Docker (`VITE_USE_POLLING`).
- Files written by Python on Windows get CRLF; `.gitattributes` normalizes to LF on commit.
- Atlas Local search indexes build asynchronously; wait for them before querying.
- Kaggle sessions time out, so the model can vanish at any time. Everything must tolerate `ModelOfflineError`.
- `openai` 3.x uses `httpx2` internally (its logger is `httpx2`).

## Progress log
- 2026-10-01: Plan approved; repo initialised with remote `origin` (github.com/Akhil-0707/Repo_Onboarding_Agent).
- 2026-10-01: Backend scaffold, LLM client + health, tests (33 local passing, 2 mongo skipped).
- 2026-10-01: Frontend shell + tests; Docker Compose; Kaggle server; CI. Pushed; CI green (35 backend incl. Mongo, 23 frontend).
- 2026-10-01: **Phase 1 complete.**
- 2026-10-01: First local `docker compose up` verified (all services healthy, beat→worker health probe, set_llm_url in container). Backend host port moved to 8010 (8000 used by another local project); all host ports configurable.
