# RepoGuide — Handover

Living document. Update after every meaningful step. A fresh session should be able to continue from here alone.

## Current status
- **Phase:** 3 ✅ complete. **Next: Phase 4** (embeddings, vector + full-text indexes, hybrid search, agent tools).
- **Last commit:** see `git log -1` (Phase 3 closed on 2026-10-01).
- **In progress:** nothing; ready to start Phase 4.

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
| **tree-sitter pinned to 0.25.2** + official grammar wheels (`tree-sitter-python/javascript/typescript/java/go`) instead of `tree-sitter-language-pack` | 0.26.0 corrupted heap memory under GC pressure (segfaults in Celery workers, garbage values); the language pack also downloads grammars at runtime. Official wheels are static and deterministic. Regression test: `test_parsing_survives_garbage_collection_pressure` |
| Keep the bytes passed to `Parser.parse()` alive while walking | `Node.text` reads that buffer directly; a temporary is a use-after-free |
| Clone = `git init` + `fetch --depth 1 origin <sha>` + checkout | Exact resolved commit; hooks disabled, `core.symlinks=false`, no submodules/LFS/tags, token via `GIT_CONFIG_*` env (never in URL/.git/config) |
| Files > 500 KB are **skipped and logged**, not fatal; repo size (API pre-check + working tree post-check) and file count (5,000) **fail** the job | Failing a whole repo for one big asset would be hostile; spec limits still enforced |
| One Celery task runs all clone-dependent steps; Mongo-only stages (embed, analyze) will be chained tasks | The clone lives on one worker's local disk |
| Job progress written with atomic PyMongo updates (array filters, capped logs) + Redis pub/sub; step timestamps are ISO strings | ORM JSONField re-serialises with `json.dumps` on read (datetimes would break it) |
| SSE stream: subscribe first, then snapshot, then incremental events; snapshot again on every 15 s keep-alive | No lost events; clients self-heal |
| `get_db()` uses `connections[...].database` | `get_database()` returns a logging proxy in DEBUG that isn't a real `Database` |
| Removing a repo only unlinks it from the user's dashboard | Snapshots are a shared cache keyed by commit SHA |
| Celery worker/beat auto-reload in dev (`watchfiles`, `CELERY_RELOAD=1`) | Workers otherwise keep running stale code |
| `redis` pinned to 6.4.0 | kombu (Celery 5.6) caps redis-py below 7 |
| TypeScript **6.0.x** (not 7) | typescript-eslint 8.71 supports TS < 6.1 |
| Embeddings: `BAAI/bge-small-en-v1.5` on CPU (Phase 4) | Fast, no `trust_remote_code`; hybrid search compensates |
| Architecture map: model outputs JSON graph, server renders Mermaid (Phase 6) | Small models often write invalid Mermaid |
| Shiki (not Monaco) for code viewing | Read-only viewer; much lighter |
| Hand-written GitHub OAuth (`apps/accounts/github_oauth.py`, `views.py`) | Avoids allauth/social-auth model incompatibilities with Mongo |
| OAuth callback → SPA gets a **one-time code** (60 s, cache) → `POST /api/auth/exchange` | Tokens never appear in URLs/history |
| Access token in memory; refresh token httpOnly cookie on `/api/auth/` (SameSite=Lax) | XSS can't read the refresh token; cookie scoped to auth endpoints |
| Revocation via `User.token_version` + `ver` JWT claim (`VersionedJWTAuthentication`) | simplejwt's blacklist app migrations use integer PKs (incompatible with Mongo ObjectIds) |
| Cookie endpoints (refresh/logout) require header `X-RepoGuide-Client: web` | CSRF defence: cross-site forms can't set custom headers |
| GitHub token encrypted with MultiFernet (`TOKEN_ENCRYPTION_KEYS`; dev falls back to a SECRET_KEY-derived key only when DEBUG) | Encryption at rest + key rotation |
| OAuth redirect URI defaults to `{FRONTEND_URL}/api/auth/github/callback` | Goes through the Vite proxy/nginx so cookies stay same-origin |
| SSE via async Django views + fetch-stream on frontend | Needs Authorization header and POST (EventSource can't) |
| `est_cost` from configurable per-1k prices, default 0 | Self-hosted model; tokens + latency are the primary metrics |

## Completed
- **Phase 3:** ingestion pipeline (resolve → cache by url+SHA → sandboxed clone → filter → detect → tree-sitter parse → chunk → store files/blobs/chunks/edges) with live progress (Mongo + Redis → SSE); repo API (create/list/detail/delete, job, tree, file content with line ranges + GitHub links); frontend dashboard, live progress page, workspace (file tree, Shiki code viewer with range highlight + symbol jump, tab/chat placeholders). Fixture repos for py/ts/go/java. Verified for real in Docker on `tj/commander.js` (218 files, 424 symbols, 1,086 chunks, 136 internal edges). Tests: 116 backend, 60 frontend.
- **Phase 2:** GitHub OAuth (login/callback with signed state cookie, open-redirect-safe `next`), encrypted token storage, one-time exchange code, JWT access + rotating refresh cookie, logout revokes all sessions, `/api/me`; frontend AuthProvider (silent refresh, single-flight, 401 retry), login/callback pages, RequireAuth, user menu, settings GitHub status. Tests: 58 backend, 33 frontend.
- **Phase 1:** repo + tracking files; Django/Mongo scaffold; common layer (structlog redaction, request ids, error envelope, pagination); custom User; Celery + beat (LLM health probe); LLMClient (timeouts/retries/backoff/offline, streaming, tool-call assembly); runtime config + `set_llm_url` + admin; `/api/health` and `/api/llm/health`; fake OpenAI-compatible server and 35 backend tests; React shell (router, theme, model banner, API client, state views) with 23 tests; Docker Compose stack; Kaggle notebook/script/guide; CI (all green).

## Known issues / TODOs / blockers
- The vLLM 0.30.0 + T4 combination is unverified (needs a Kaggle run). The documented fallback is 0.18.1.
- Phase 4 will add ML dependencies (sentence-transformers + CPU torch) to the backend image; keep the API image slim if possible (build arg).

## Next steps (Phase 4)
1. `apps/search/embeddings/`: `EmbeddingProvider` interface; `SentenceTransformerProvider` (CPU, `BAAI/bge-small-en-v1.5`, 384-d) and `OpenAICompatibleEmbeddingProvider`; batching with retry/backoff. Needs `sentence-transformers` + CPU-only torch in the **worker** image (keep the API image slim via a build arg).
2. Embed step chained after ingestion (`embed_repository(repo_id)`), with progress reporting (add an `embed` step to `PIPELINE_STEPS`).
3. `ensure_search_indexes` command: Atlas Vector Search index on `code_chunks.embedding` (filter `repo_id`) + Atlas Search index (content/symbol/path, `repo_id` token); wait until queryable.
4. `apps/search/store.py` + `hybrid.py`: `$vectorSearch` + `$search`, merged with RRF (k=60); in-memory fake for unit tests.
5. Agent tools (read-only, scoped to repo): list_directory, read_file, search_code, grep (google-re2), get_symbol, get_dependencies, get_repo_metadata, with JSON schemas.
6. Tests: RRF, tools on fixture data, provider batching/retry.

## Known follow-ups (later phases)
- **Stale job sweeper (Phase 8):** a worker hard crash (SIGKILL/OOM) can leave a job `running`; add a beat task that fails jobs with no progress for N minutes.
- **Dev GitHub rate limit:** unauthenticated API calls (test users without a GitHub token) share 60 req/h per IP. Real users resolve with their OAuth token. Consider an optional server `GITHUB_API_TOKEN` fallback for `seed_demo` (Phase 9).

## Gotchas
- **Local-only tooling files** are ignored through `.git/info/exclude`, never via the shared `.gitignore`.
- The project lives under OneDrive: `node_modules` stays in a Docker named volume; Vite uses polling inside Docker (`VITE_USE_POLLING`).
- Files written by Python on Windows get CRLF; `.gitattributes` normalizes to LF on commit.
- Atlas Local search indexes build asynchronously; wait for them before querying.
- Kaggle sessions time out, so the model can vanish at any time. Everything must tolerate `ModelOfflineError`.
- `openai` 3.x uses `httpx2` internally (its logger is `httpx2`).
- After adding npm packages, run `docker compose exec frontend npm install` (node_modules lives in a named volume).
- Local test session without GitHub OAuth: issue a refresh token for a user via `manage.py shell` (`apps.accounts.services.issue_tokens`) and set it as the `rg_refresh` cookie (path `/api/auth/`) on localhost:5173.
- Windows Python scripts that edit files must pass `encoding="utf-8"` (default is cp1252).

## Progress log
- 2026-10-01: Plan approved; repo initialised with remote `origin` (github.com/Akhil-0707/Repo_Onboarding_Agent).
- 2026-10-01: Backend scaffold, LLM client + health, tests (33 local passing, 2 mongo skipped).
- 2026-10-01: Frontend shell + tests; Docker Compose; Kaggle server; CI. Pushed; CI green (35 backend incl. Mongo, 23 frontend).
- 2026-10-01: **Phase 1 complete.**
- 2026-10-01: **Phase 3 complete**: ingestion pipeline + live progress + workspace/code viewer; found & fixed a tree-sitter 0.26 memory-corruption bug (pinned 0.25.2); real ingestion verified in Docker.
- 2026-10-01: History rewritten (force-push, with approval) to remove a tooling mention from an early `.gitignore`.
- 2026-10-01: **Phase 2 complete**: OAuth/JWT/encryption backend + frontend auth; verified the login redirect round-trip through the Vite proxy in the running stack.
- 2026-10-01: First local `docker compose up` verified (all services healthy, beat→worker health probe, set_llm_url in container). Backend host port moved to 8010 (8000 used by another local project); all host ports configurable.
