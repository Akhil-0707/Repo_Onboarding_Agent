# RepoGuide — Phase Plan

Status legend: `- [x]` pending, `- [x]` done. A phase heading gets `✅ Completed (date, commit)` when every task under it is done.

---

## Phase 1 — Scaffolding, infrastructure, LLM health, Kaggle server — ✅ Completed (2026-10-01)
- [x] Git repo, `.gitignore`, `.gitattributes`, `plan.md`, `HANDOVER.md`
- [x] Backend project: Django 5.2 + django-mongodb-backend, settings split (base/dev/test), custom `User` with Mongo app configs, migrations
- [x] Common layer: PyMongo handle, structured logging with secret redaction, error envelope, pagination
- [x] Celery app + Redis broker + beat schedule skeleton
- [x] `LLMClient` interface + OpenAI-compatible implementation (timeouts, retries, backoff, `ModelOfflineError`)
- [x] Runtime LLM settings (Mongo-backed, TTL cache) + `manage.py set_llm_url` + admin
- [x] `/api/llm/health` endpoint (Redis-cached) + OpenAPI docs (drf-spectacular)
- [x] Backend tests (health endpoint, runtime config, LLM client against fake OpenAI-compatible server)
- [x] Frontend: Vite + React + TS + Tailwind + Router + TanStack Query shell, theme toggle, model-offline banner
- [x] Frontend lint/format/test tooling (ESLint, Prettier, Vitest + RTL)
- [x] Docker Compose (mongo atlas-local, redis, backend, worker, beat, frontend), Dockerfiles, `.env.example` _(verified locally 2026-10-01)_
- [x] Kaggle `serve_model.py`, `serve_model.ipynb`, `kaggle/README.md`
- [x] GitHub Actions CI (ruff, black, pytest, eslint, prettier, tsc, vitest)
- [x] Lint + tests green, commit, push

## Phase 2 — GitHub OAuth, JWT, users, dashboard skeleton
- [ ] GitHub OAuth login/callback, one-time exchange code, user upsert
- [ ] Fernet-encrypted GitHub token at rest (MultiFernet), never logged
- [ ] JWT access (memory) + refresh (httpOnly cookie) with rotation; `/api/me`, logout
- [ ] Frontend auth context, login button, callback page, protected routes, silent refresh
- [ ] Dashboard skeleton (empty/loading/error states)
- [ ] Tests (OAuth flow with mocked GitHub, token encryption, JWT endpoints, auth components)

## Phase 3 — Ingestion pipeline with live progress
- [ ] Repo create API + URL validation + GitHub resolve (default branch, HEAD SHA, size, visibility)
- [ ] Cache by `(repo_url, commit_sha)`
- [ ] Sandboxed shallow clone with limits (200 MB / 5,000 files / 500 KB) and no code execution
- [ ] File filter (ignored dirs, lockfiles, binaries, minified, vendored, `.gitignore`)
- [ ] Language + framework detection from extensions and manifests
- [ ] tree-sitter parsing (Python, JS/TS, Java, Go): symbols + imports; dependency graph
- [ ] Symbol-aware chunking with size cap + overlap; line-based fallback
- [ ] Store files, blobs, chunks, dependency edges
- [ ] Step progress to Mongo + Redis pub/sub; SSE stream endpoint
- [ ] Frontend: create flow, ingestion progress page (live steps + logs)
- [ ] File tree + content APIs; FileTree + CodeViewer (Shiki, line highlight, GitHub link)
- [ ] Fixture repos + tests (filter, chunking, parsing, depgraph, API)

## Phase 4 — Embeddings, vector + full-text indexes, hybrid search
- [ ] `EmbeddingProvider` interface; sentence-transformers (CPU) + OpenAI-compatible impls
- [ ] Batched embedding with retry/backoff
- [ ] `ensure_search_indexes` command (vector + Atlas Search), wait for queryable
- [ ] Hybrid search (`$vectorSearch` + `$search`, RRF)
- [ ] Agent tools: list_directory, read_file, search_code, grep, get_symbol, get_dependencies, get_repo_metadata
- [ ] Tests (RRF, tools against fixture data, in-memory search backend)

## Phase 5 — Analysis agent: Overview, Start Here, Glossary
- [ ] Agent loop: tool schema validation, repair step, plain-text tool-call fallback, iteration + token budgets
- [ ] Pydantic section schemas + structured-output retry with validation errors
- [ ] Citation validator (paths/line ranges against the file index)
- [ ] Deterministic pre-analysis digest
- [ ] Agent logs (tool calls, tokens, latency) to Mongo
- [ ] Checkpointing per section; `waiting_for_model` status; beat-driven resume
- [ ] Overview, Start Here, Glossary sections + UI tabs
- [ ] Tests: agent loop with mocked LLM, fake OpenAI server (tool calls, malformed repair, timeouts, offline/resume)

## Phase 6 — Architecture map, Guided Tour, tour mode
- [ ] Architecture JSON graph → deterministic Mermaid render
- [ ] Guided Tour with enforced flow-trace step
- [ ] Architecture tab (Mermaid, strict security) + Tour tab
- [ ] Tour mode page (stepper, progress bar, ←/→ keys, code + explanation)
- [ ] Tests

## Phase 7 — Q&A chat
- [ ] Threads + messages models/APIs
- [ ] Streaming chat agent (SSE: tokens, tool steps, citations)
- [ ] Citation parsing/validation; "not found" behaviour
- [ ] Starter questions
- [ ] Chat panel UI (collapsible tool steps, citation chips, threads, offline disabled)
- [ ] Tests

## Phase 8 — Cost tracking, rate limits, caching, error polish
- [ ] Usage/cost per repo and per user; Settings page
- [ ] Per-user rate limit (5 new analyses/hour; cache hits exempt)
- [ ] Private-repo cache access rule
- [ ] Re-analyze, delete; consistent errors everywhere
- [ ] Tests

## Phase 9 — Coverage, E2E, README, demo seed
- [ ] Fill test coverage gaps
- [ ] Playwright E2E main flow with mocked backend
- [ ] `seed_demo` management command
- [ ] README (architecture diagram, setup, env vars, design tradeoffs, limitations, screenshot placeholders)
- [ ] Final CI green, push
