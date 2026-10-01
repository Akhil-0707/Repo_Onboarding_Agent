# RepoGuide — Phase Plan

Status legend: `- [ ]` pending, `- [x]` done. A phase heading gets `✅ Completed (date, commit)` when every task under it is done.

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

## Phase 2 — GitHub OAuth, JWT, users, dashboard skeleton — ✅ Completed (2026-10-01)
- [x] GitHub OAuth login/callback, one-time exchange code, user upsert
- [x] Fernet-encrypted GitHub token at rest (MultiFernet), never logged
- [x] JWT access (memory) + refresh (httpOnly cookie) with rotation; `/api/me`, logout (revocation via per-user `token_version`)
- [x] Frontend auth context, login button, callback page, protected routes, silent refresh
- [x] Dashboard skeleton (empty/loading/error states)
- [x] Tests (OAuth flow with mocked GitHub, token encryption, JWT endpoints, auth components)

## Phase 3 — Ingestion pipeline with live progress — ✅ Completed (2026-10-01)
- [x] Repo create API + URL validation + GitHub resolve (default branch, HEAD SHA, size, visibility)
- [x] Cache by `(repo_url, commit_sha)`
- [x] Sandboxed shallow clone with limits (200 MB / 5,000 files / 500 KB) and no code execution
- [x] File filter (ignored dirs, lockfiles, binaries, minified, vendored, `.gitignore`)
- [x] Language + framework detection from extensions and manifests
- [x] tree-sitter parsing (Python, JS/TS, Java, Go): symbols + imports; dependency graph (tree-sitter 0.25.2 + official grammar wheels)
- [x] Symbol-aware chunking with size cap + overlap; line-based fallback
- [x] Store files, blobs, chunks, dependency edges
- [x] Step progress to Mongo + Redis pub/sub; SSE stream endpoint
- [x] Frontend: create flow, ingestion progress page (live steps + logs)
- [x] File tree + content APIs; FileTree + CodeViewer (Shiki, line highlight, GitHub link)
- [x] Fixture repos + tests (filter, chunking, parsing, depgraph, API)

## Phase 4 — Embeddings, vector + full-text indexes, hybrid search — ✅ Completed (2026-10-01)
- [x] `EmbeddingProvider` interface; sentence-transformers (CPU) + OpenAI-compatible impls
- [x] Batched embedding with retry/backoff
- [x] `ensure_search_indexes` command (vector + Atlas Search), wait for queryable
- [x] Hybrid search (`$vectorSearch` + `$search`, RRF)
- [x] Agent tools: list_directory, read_file, search_code, grep, get_symbol, get_dependencies, get_repo_metadata
- [x] Tests (RRF, tools against fixture data, in-memory search backend)

## Phase 5 — Analysis agent: Overview, Start Here, Glossary — ✅ Completed (2026-10-01)
- [x] Agent loop: tool schema validation, repair step, plain-text tool-call fallback, iteration + token budgets
- [x] Pydantic section schemas + structured-output retry with validation errors
- [x] Citation validator (paths/line ranges against the file index)
- [x] Deterministic pre-analysis digest
- [x] Agent logs (tool calls, tokens, latency) to Mongo
- [x] Checkpointing per section; `waiting_for_model` status; beat-driven resume
- [x] Overview, Start Here, Glossary sections + UI tabs
- [x] Tests: agent loop with mocked LLM, fake OpenAI server (tool calls, malformed repair, timeouts, offline/resume)
- [x] Real-model smoke test (local Ollama qwen3:4b-instruct): 3/3 sections; reference repair tuned from the real output
- [x] Push + CI

## Phase 6 — Architecture map, Guided Tour, tour mode — ✅ Completed (2026-10-01)
- [x] Architecture JSON graph → deterministic Mermaid render (verified paths, import-seeded edges, sanitised labels)
- [x] Guided Tour with enforced flow-trace step (schema validator + re-prompt)
- [x] Architecture tab (Mermaid, strict security) + Tour tab
- [x] Tour mode page (stepper, progress bar, ←/→ keys, code + explanation)
- [x] Tests (202 backend, 74 frontend incl. a real-Mermaid parse contract test)
- [x] Real-model run (Ollama qwen3:4b-instruct): fixed long-JSON read timeouts by streaming structured output
- [x] Push + CI

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
