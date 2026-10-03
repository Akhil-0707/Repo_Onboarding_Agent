# RepoGuide — Handover

Living document. Update after every meaningful step. A fresh session should be able to continue from here alone.

## Current status
- **Phase:** 9 complete. **All planned phases (1–9) are done.** Possible next work is listed under "Next steps (after Phase 9)".
- **Last commit:** see `git log -1`.
- **Local stack model:** still pointed at **Ollama** `qwen3:4b-instruct` (`set_llm_url http://host.docker.internal:11434 --model qwen3:4b-instruct`), kept on purpose for local testing. Revert when no longer needed (delete the `llm.base_url`/`llm.model` rows in `runtime_settings` via admin, or `set_llm_url` with the Kaggle tunnel).

## ▶ Resume here (fresh session)
1. All phases are complete. Confirm CI for the last push is green (`gh run list --limit 1`), then pick from "Next steps (after Phase 9)" below.
2. To re-run the analysis on the local commander.js snapshot (only missing sections are generated):
   `docker compose exec backend python manage.py shell` → create an `IngestionJob` for the repo with `initial_steps()` (all steps except `analyze` marked done, status running) → `apps.analysis.tasks.analyze_repository.delay(str(job.pk))`.
3. Running backend tests locally against the Docker Mongo needs credentials:
   `MONGODB_URI="mongodb://repoguide:repoguide@localhost:27017/?directConnection=true&authSource=admin" .venv/Scripts/python -m pytest`.
4. If `.venv/Scripts/black` says "Permission denied" (OneDrive/AV lock on the .exe), run `.venv/Scripts/python -m black` instead.
5. Backend code edits auto-reload the Celery worker (watchfiles): don't edit backend files while a real analysis is running, or it restarts mid-run. If that happens, restart the worker and re-enqueue `analyze_repository` for the same job: it resumes from `Analysis.checkpoint`.
6. Browser checks of authenticated pages need a session for a local test user; the assistant's tooling may refuse to inject tokens into the browser. Log in yourself (GitHub OAuth) or set the `rg_refresh` cookie manually.

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
| Embeddings: `EmbeddingProvider` (`apps/search/embeddings`), local `SentenceTransformerProvider` (bge-small, 384-d, normalised, query prefix) or `OpenAICompatibleEmbeddingProvider`; `embed_in_batches` retries with backoff | Ingestion never depends on the Kaggle model; swappable |
| ML deps in `requirements-ml.txt` (CPU-only torch 2.14.1 from the PyTorch CPU index) — installed in the Docker image, **not** in CI/unit tests (they use `tests/fakes/embeddings.HashingEmbeddingProvider`) | Avoids ~3 GB of CUDA libs and a 1 GB install in CI |
| Embedding vectors reused across snapshots via `embed_hash` = sha256(model + text) | Re-analysing a new commit only embeds changed chunks |
| Pipeline is a Celery chain `ingest → embed → finalize`; each stage no-ops if the job already failed | Works identically in eager tests and real workers; no reliance on `Ignore` semantics |
| Atlas indexes: `chunks_vector` (cosine, filter `repo_id`) + `chunks_text` with custom `code` analyzer (regexSplit + wordDelimiterGraph → `getUserById` → get/user/by/id) | Identifier-aware keyword search; verified on real mongot |
| `ensure_search_indexes` compares definitions as a *subset* of what Atlas stores | Atlas adds defaults (`indexOptions`, `norms`); equality would rebuild on every start |
| Hybrid search = `$vectorSearch` + `$search` merged with RRF (k=60); each side may fail and search degrades to the other | Robust while indexes build or the embedder is unavailable |
| Agent tools (`apps/agents/tools.py`): Pydantic arg models (extra=forbid) → JSON schemas; `execute_tool` never raises and returns repair-friendly errors (incl. the expected schema); outputs capped at 8k chars and wrapped in `<repo_content>` with breakout escaping; `grep` uses RE2 (no ReDoS) | Small-model safeguards + prompt-injection defence |
| Analysis = per-section *research loop* (tools, ≤6 iterations) → *structured JSON* (Pydantic schema, guided `response_format` with fallback, ≤2 repair retries) → *reference repair* (`apps/agents/citations.py`) | Short focused prompts per section suit an 8B model; nothing hallucinated survives |
| Deterministic digest (`apps/agents/digest.py`): README excerpt, scripts, layout, entry points, most-imported files | Fewer tool calls, better small-model output |
| Pipeline chain is now `ingest → embed → mark_indexed → analyze`; repo becomes `ready` (browsable) after embeddings; the job stays open until the analysis ends | Users can read code while the AI works or waits |
| `ModelOfflineError` → checkpoint (`Analysis.checkpoint`: section, phase research/structure, messages, iteration) → job `waiting_for_model`; beat `resume_waiting_analyses` (60 s) atomically claims and re-enqueues; gives up after `ANALYSIS_MAX_WAIT_HOURS` (48) | Kaggle sessions disappear; finished sections are never redone |
| Every LLM/tool call logged to `agent_logs` (tokens, latency, tool, args); usage + `est_cost` on `Analysis` | Spec: track tokens/latency instead of $ |
| `redis` pinned to 6.4.0 | kombu (Celery 5.6) caps redis-py below 7 |
| TypeScript **6.0.x** (not 7) | typescript-eslint 8.71 supports TS < 6.1 |
| Embeddings: `BAAI/bge-small-en-v1.5` on CPU (Phase 4) | Fast, no `trust_remote_code`; hybrid search compensates |
| Architecture map: model outputs a JSON graph (modules + edges), server verifies paths and renders Mermaid (`apps/agents/mermaid.py`, labels sanitised, node ids prefixed `m_`) | Small models write invalid Mermaid; repo text can't inject Mermaid/HTML |
| Architecture edges seeded from `dependency_edges` aggregated to modules (dashed "N imports" edges); model edges get an `imports` count as evidence | The map reflects the real code even when the model misses links |
| Default-kinded modules get an inferred kind (tests/utils/docs/data/config/ui by name; the module owning the main entry point becomes `entry`) | Small models label everything `core` |
| Flow trace enforced after repair by `ensure_flow_trace`: if no stop is labelled, the model picks which of its own stops form the trace (tiny JSON), else the tour is re-prompted | Real run: the 4B model rewrote a whole tour 3x (~100 s each) and never added the label; the pick takes ~2 s |
| `generate_structured(accept=...)`: reference repair + section checks run inside the retry loop; `SectionCheckError` (an `OutputRejectedError`) is fed back to the model | Unusable output gets fixed instead of failing the section |
| Structured-output calls **stream** (`stream_chat` with `response_format`) | Read timeout then applies between chunks: a slow model writing 1.6k tokens (128 s locally) is no longer mistaken for an offline server (which looped forever via resume) |
| Mermaid **11.x** (not 12.0), lazy-loaded chunk, `securityLevel: "strict"`, `htmlLabels: false` | 12.0 pulls a vulnerable lodash-es via chevrotain; Mermaid is big, load it only on the Architecture tab |
| Tour mode at `/repos/:id/tour?step=N` (1-based, clamped), ←/→ keys ignored while typing | Shareable step links |
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
| Chat agent runs in a thread inside the ASGI process, events handed to the SSE response via an asyncio queue; client disconnect → agent stops at its next step and saves "interrupted" | Simple, no Celery round-trip for interactive latency; long answers hold one thread each (revisit if load grows) |
| Every chat turn streams; `TokenGate` holds back text that starts like tool-call markup; `retract` event drops drafts that turned out not to be the answer | Live tokens without leaking `<tool_call>` text; `done` carries the authoritative, citation-checked text |
| `require_tool_use` for chat: an answer given before any tool call is discarded once with a "look first" nudge | Real 4B run answered "not found… I searched for X" without searching |
| Citations `[path:start-end]`: path-like bracketed refs to missing files are stripped, real ones normalised/clamped, real backticked paths upgraded, fenced code untouched; UI makes chips only from server-validated citations | No hallucinated references survive |
| History: last `CHAT_HISTORY_TURNS` turns verbatim + deterministic digest of older turns (no extra LLM call); failed answers excluded | Fits the 16k window without summarisation latency |
| Chat stream view is `csrf_exempt` (Bearer header auth only, never cookies); chat tests use `enforce_csrf_checks=True` | Django's CSRF middleware 403'd real browser POSTs while the test client hid it |
| Answer rendering: small safe Markdown subset (`AnswerText`), no HTML, no new dependency | Model output is untrusted |
| New-analysis rate limit consumed **inside** the service, right before work is enqueued (`on_new_work` hook → `apps/repos/quota.py`, DRF `SimpleRateThrottle` history in the cache) | A DRF view throttle runs before we know whether the request is a cache hit; cache hits must stay free and throttled requests must not leave half-created repos |
| Re-analyze: newer commit → new snapshot replaces the old one on *this user's* dashboard; same commit → only unfinished AI sections are retried (analysis-only job); fully done → 200 `cached` no-op; active job → 409 | Snapshots are a shared cache: a finished analysis is never redone for everyone |
| Private repos: `UserRepository.access_checked_at`; `get_user_repository` re-confirms with GitHub every 6 h; 404 from GitHub unlinks the repo; GitHub outage → serve if confirmed within 7 days, else 502 | Spec: cached private analyses only while the user's token confirms access |
| Usage: analysis usage attributed to users who *started work* on a snapshot; chat usage is personal; cost via `apps/llm/cost.py` (prices default 0 → "≈$0 (self-hosted)") | Cache hits are free, so they cost the opener nothing |
| Stale-job sweeper (beat, 5 min): running jobs silent for 30 min (`heartbeat_at`, written on every progress update) or queued for 6 h are stopped; if the repo is already browsable only the unfinished AI sections fail (checkpoint kept for Re-analyze) | Worker SIGKILL/OOM no longer leaves jobs spinning forever |
| Unknown `/api/` URLs → JSON envelope via a catch-all route (works with DEBUG on) plus `handler404/500` | Consistent errors everywhere |
| Playwright E2E runs the production build (`vite preview`) with every `/api` call mocked in the browser (`e2e/fakeApi.ts`, stateful) | Real Chromium exercises Mermaid, SSE, keyboard tour mode and chat without any backend services |
| Coverage floors in CI: backend `--cov-fail-under=90` (at 93%), frontend Vitest thresholds just below current numbers | Regressions in coverage fail the build |
| `seed_demo` stores an optional `GITHUB_API_TOKEN` on the demo user only (never a global fallback) | A global server token could resolve private repos for users without access |
| `login_link` (DEBUG only) prints a one-time sign-in link using the OAuth exchange code | Explore a local stack without registering a GitHub OAuth app; the developer runs it, tokens never pass through tooling |
| README screenshots = real API responses (`export_snapshot`, recorded in-process by the real views) replayed in the real UI by Playwright (`npm run screenshots`) | Real output, reproducible, no signed-in browser needed |
| `set_llm_url` without `--model` clears the model override; adopts the server's only model if the configured one is not served; explains 401/403 (API key) | Switching Ollama → vLLM used to keep `qwen3:4b-instruct` and fail |
| Architecture repair ignores previously derived edges and re-derives them | Idempotent: re-applying repair to stored output used to turn dashed import edges into plain ones |
| Embedding model warmed in the ASGI process at startup (`config/asgi.py`, `EMBEDDING_WARMUP=1` default) | First chat search no longer pays ~10 s |

## Completed
- **Phase 9:** tests for the GitHub REST/OAuth clients (error translation, token fallback), encryption configuration, the real Redis event bus, health endpoint and management commands; real Shiki highlighting and ingestion page states; CI coverage floors and a Redis service; Playwright E2E (main flow: landing → dashboard → live progress → workspace tabs incl. real Mermaid → tour mode by keyboard → streamed cited chat → dashboard; plus offline chat) in a new CI job; `seed_demo` command; full README (architecture diagram, setup, model server, config, API, development, trade-offs, security, limitations, screenshot placeholders). Tests: 263 backend (93% coverage in CI), 94 frontend, 2 E2E.
- **Phase 8:** per-user new-analysis rate limit (cache hits free; 429 `rate_limited` with `retry_after_seconds`), `POST /api/repos/{id}/reanalyze`, usage endpoints (`GET /api/usage` incl. rate-limit status and pricing, `GET /api/repos/{id}/usage`), private-repo access re-checks, stale-job sweeper with job heartbeats, JSON 404 catch-all; frontend Settings usage section (tokens, model time, cost, quota, per-repo table) and workspace Re-analyze action with outcome notices. Live checks: real usage on commander.js (58,729 analysis tokens / 17 calls), Re-analyze surfaced GitHub's unauthenticated rate limit as a clean 502, JSON 404 in dev. Tests: 238 backend, 88 frontend.
- **Phase 7:** `apps/chat` (Thread/Message models, CRUD + messages API, streaming endpoint `POST /api/repos/{id}/threads/{tid}/messages/stream` with events start/tool_start/tool_end/token/retract/citation/done/error; 503 `model_offline` and 409 `repo_not_ready` before streaming), agent loop streaming mode, citation processing, history digest, embedding warm-up; frontend chat panel (threads select/new/delete, starter questions incl. from Overview, live research steps, streamed draft, cited answers with chips into the code viewer, Stop, offline banner). Real checks with Ollama qwen3:4b-instruct on commander.js: 4-tool answer with 2 validated citations in 53 s; honest "not found" after a real search; through uvicorn first token 7.3 s, disconnect mid-answer recorded as interrupted. Tests: 227 backend, 82 frontend.
- **Phase 6:** Architecture (JSON graph → verified modules/edges → import-seeded edges → server Mermaid) and Guided Tour (8–12 stops, enforced flow trace, symbol-pinned ranges, kind-prefix cleanup) sections; output re-prompting via `accept`; streamed structured output; frontend Architecture tab (lazy strict Mermaid, clickable nodes highlight module cards, file chips), Tour tab and tour mode page (stepper, progress bar, ←/→, code + explanation); Mermaid contract test runs the real parser on the server's output format. Real run on commander.js with Ollama qwen3:4b-instruct: architecture 6 modules / 9 edges (3 of 6 model edges confirmed by imports, 3 import edges added), tour 9 stops; a 1.6k-token tour JSON took 128 s and only succeeded after switching to streaming; resume from the `structure` checkpoint verified for real. Tests: 202 backend, 74 frontend.
- **Phase 5:** real-model smoke test with local Ollama `qwen3:4b-instruct` on commander.js: all 3 sections done in 339 s, 9 LLM calls, ~30k tokens, tool calls well-formed (5–6 per research turn), no repairs needed. Output quality findings fixed: the model writes `1-1` line ranges for whole files and invents round line numbers for glossary terms → reference repair now drops `1-1`, prefers the symbol index (exact case first), and drops ranges whose lines don't mention the term.
- **Phase 5 (code):** text tool-call parser, `AgentLoop` (validation repair, budgets, compaction, checkpoint hook, logging), `generate_structured`, section schemas (Overview incl. 4 starter questions, StartHere, Glossary), citation validator/repair, digest + prompts, `apps/analysis` (model, runner, tasks, API `GET /api/repos/{id}/analysis[/{section}]`), frontend Overview/Start Here/Glossary tabs with citation chips that open the code viewer, waiting-for-model UI. Tests: 185 backend (incl. end-to-end over HTTP with the fake OpenAI server: malformed-call repair, outage mid-run, resume from checkpoint) + 65 frontend, all passing locally.
- **Phase 4:** embedding providers + batching/retry, embed stage chained after ingestion (vector reuse across snapshots), Atlas vector + text indexes (`ensure_search_indexes`, run at web startup), hybrid search with RRF, 7 agent tools with strict schemas. Verified in Docker on commander.js with the real bge-small model (1,086 chunks; hybrid queries ~50 ms after the first model load; whole pipeline 219 s on CPU). Tests: 143 backend (incl. real Atlas `$vectorSearch`/`$search`), 60 frontend.
- **Phase 3:** ingestion pipeline (resolve → cache by url+SHA → sandboxed clone → filter → detect → tree-sitter parse → chunk → store files/blobs/chunks/edges) with live progress (Mongo + Redis → SSE); repo API (create/list/detail/delete, job, tree, file content with line ranges + GitHub links); frontend dashboard, live progress page, workspace (file tree, Shiki code viewer with range highlight + symbol jump, tab/chat placeholders). Fixture repos for py/ts/go/java. Verified for real in Docker on `tj/commander.js` (218 files, 424 symbols, 1,086 chunks, 136 internal edges). Tests: 116 backend, 60 frontend.
- **Phase 2:** GitHub OAuth (login/callback with signed state cookie, open-redirect-safe `next`), encrypted token storage, one-time exchange code, JWT access + rotating refresh cookie, logout revokes all sessions, `/api/me`; frontend AuthProvider (silent refresh, single-flight, 401 retry), login/callback pages, RequireAuth, user menu, settings GitHub status. Tests: 58 backend, 33 frontend.
- **Phase 1:** repo + tracking files; Django/Mongo scaffold; common layer (structlog redaction, request ids, error envelope, pagination); custom User; Celery + beat (LLM health probe); LLMClient (timeouts/retries/backoff/offline, streaming, tool-call assembly); runtime config + `set_llm_url` + admin; `/api/health` and `/api/llm/health`; fake OpenAI-compatible server and 35 backend tests; React shell (router, theme, model banner, API client, state views) with 23 tests; Docker Compose stack; Kaggle notebook/script/guide; CI (all green).

## Known issues / TODOs / blockers
- The vLLM 0.30.0 + T4 combination is unverified (needs a Kaggle run). The documented fallback is 0.18.1.
- Phase 4 will add ML dependencies (sentence-transformers + CPU torch) to the backend image; keep the API image slim if possible (build arg).

## Next steps (after Phase 9)
Done since Phase 9: real README screenshots, `login_link`, `export_snapshot`, smarter `set_llm_url`, flow-trace pick, idempotent architecture repair; `pallets/itsdangerous` analysed for real (5/5 sections).
Waiting on the developer:
1. **Look at the app signed in**: `docker compose exec backend python manage.py login_link` → open the printed link within 60 s.
2. **Kaggle run**: follow `kaggle/README.md`; put `LLM_API_KEY` in `.env` (create it; one line is enough), `docker compose up -d`, then `set_llm_url <tunnel URL>`. That also switches the stack away from Ollama. Then re-run the smoke tests (re-analyse a repo, ask a chat question) on Qwen3-8B.
Later candidates: chat answers in dedicated workers if load grows; a chat rate limit; production deployment notes (HTTPS, `AUTH_COOKIE_SECURE`, `TOKEN_ENCRYPTION_KEYS`, nginx buffering off for SSE).

## Known follow-ups (later phases)
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
- Git Bash rewrites `/tmp/...` arguments passed to `docker compose exec` into Windows paths: prefix those commands with `MSYS_NO_PATHCONV=1` (but not `docker compose cp`, whose host-side path needs the conversion).
- The Celery worker's auto-reload can lag behind edits; after changing agent/analysis code, `docker compose restart worker` before a real run (a stale worker produced an old error message once).
- GitHub's anonymous API limit (60 requests/hour per IP) is shared by every local tool; `seed_demo` accepts `GITHUB_API_TOKEN`, signed-in users use their own token.
- Playwright clears `frontend/test-results/` at the start of each run; keep snapshot files elsewhere.

## Progress log
- 2026-10-01: Plan approved; repo initialised with remote `origin` (github.com/Akhil-0707/Repo_Onboarding_Agent).
- 2026-10-01: Backend scaffold, LLM client + health, tests (33 local passing, 2 mongo skipped).
- 2026-10-01: Frontend shell + tests; Docker Compose; Kaggle server; CI. Pushed; CI green (35 backend incl. Mongo, 23 frontend).
- 2026-10-01: **Phase 1 complete.**
- 2026-10-03: Post-Phase 9: real screenshots, login_link, export_snapshot, set_llm_url model switching, flow-trace pick (real 4B: 1.6 s vs three failed ~100 s rewrites), idempotent architecture repair; itsdangerous analysed 5/5.
- 2026-10-03: **Phase 9 complete**: coverage (93% backend in CI), Playwright E2E in CI, seed_demo, README. All phases done.
- 2026-10-03: **Phase 8 complete**: limits, re-analysis, usage, private access re-checks, sweeper, JSON 404s.
- 2026-10-02: **Phase 7 complete**: Q&A chat; real runs found two bugs fixed here (answers without searching; CSRF 403 on the stream POST).
- 2026-10-01: **Phase 6 complete**: architecture map + guided tour + tour mode; real-model run surfaced the 120 s read-timeout trap for long JSON (fixed by streaming).
- 2026-10-01: **Phase 5 complete**: real smoke test with Ollama qwen3:4b-instruct passed after restarting the worker (stale task registry); reference repair tightened from what the real output showed.
- 2026-10-01: Phase 5 code + tests committed locally.
- 2026-10-01: **Phase 4 complete**: embeddings, Atlas vector/text indexes, hybrid search (RRF), agent tools; real-model verification in Docker.
- 2026-10-01: **Phase 3 complete**: ingestion pipeline + live progress + workspace/code viewer; found & fixed a tree-sitter 0.26 memory-corruption bug (pinned 0.25.2); real ingestion verified in Docker.
- 2026-10-01: History rewritten (force-push, with approval) to remove a tooling mention from an early `.gitignore`.
- 2026-10-01: **Phase 2 complete**: OAuth/JWT/encryption backend + frontend auth; verified the login redirect round-trip through the Vite proxy in the running stack.
- 2026-10-01: First local `docker compose up` verified (all services healthy, beat→worker health probe, set_llm_url in container). Backend host port moved to 8010 (8000 used by another local project); all host ports configurable.
