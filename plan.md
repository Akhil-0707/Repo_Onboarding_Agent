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

## Phase 7 — Q&A chat — ✅ Completed (2026-10-02)
- [x] Threads + messages models/APIs
- [x] Streaming chat agent (SSE: tokens, tool steps, citations, retract)
- [x] Citation parsing/validation; "not found" behaviour (look-first nudge)
- [x] Starter questions (chat panel + Overview)
- [x] Chat panel UI (collapsible tool steps, citation chips, threads, offline disabled)
- [x] Tests (227 backend, 82 frontend); real-model + uvicorn checks
- [x] Embedding warm-up in the API process
- [x] Push + CI

## Phase 8 — Cost tracking, rate limits, caching, error polish — ✅ Completed (2026-10-03)
- [x] Usage/cost per repo and per user; Settings page
- [x] Per-user rate limit (5 new analyses/hour; cache hits exempt)
- [x] Private-repo cache access rule (periodic GitHub re-check, revoke on 404)
- [x] Re-analyze, delete; consistent errors everywhere (JSON 404 catch-all)
- [x] Stale job sweeper (heartbeats + beat task)
- [x] Tests (238 backend, 88 frontend)
- [x] Push + CI

## Phase 9 — Coverage, E2E, README, demo seed — ✅ Completed (2026-10-03)
- [x] Fill test coverage gaps (backend 93% in CI, frontend floors enforced)
- [x] Playwright E2E main flow with mocked backend (CI job)
- [x] `seed_demo` management command
- [x] README (architecture diagram, setup, env vars, design tradeoffs, limitations, screenshot placeholders)
- [x] Final CI green, push

## After Phase 9 — real-model follow-ups (Qwen3-8B on Kaggle) — ✅ Completed (2026-10-03)
- [x] Kaggle vLLM server verified (torchaudio/CUDA fix, notebook v2026-10-03.3); stack switched to Qwen3-8B
- [x] Real chat checks on Qwen3-8B (cited answer, honest "not found")
- [x] Full 5-section analysis of commander.js on Qwen3-8B, compared with qwen3:4b-instruct
- [x] Repair fixes from that run (tour range focusing, glossary location check, architecture umbrella pruning) + chat list numbering
- [x] README screenshots regenerated from the 8B output
- [x] Verify the glossary prompt change (no package-script names) with one Glossary re-run on Qwen3-8B

## Chat rate limit — ✅ Completed (2026-10-03)
- [x] Per-user chat question limit (`RATE_LIMIT_CHAT_QUESTIONS`, default 30/hour), counted only after the pre-checks pass
- [x] 429 `rate_limited` envelope with `retry_after_seconds` from the stream endpoint; question text given back in the UI
- [x] Chat quota in `GET /api/usage` and on the Settings page
- [x] Creating a conversation checks the quota without counting (no empty conversations)
- [x] Tests (274 backend, 95 frontend) + live check on Qwen3-8B

## Celery dev auto-reload — ✅ Completed (2026-10-03)
- [x] `entrypoint.sh` runs worker/beat under `watchfiles --filter python` when `CELERY_RELOAD` is set (production path unchanged)
- [x] Pin `watchfiles` in `requirements-dev.txt`
- [x] Verified live: editing a task file restarts the worker and beat; non-Python edits ignored; clean stop

## Production deployment — ✅ Completed (2026-10-03)
- [x] `config.settings.prod`: DEBUG forced off, fail fast on development secrets, HTTPS-only cookies and redirect, proxy SSL header, HSTS opt-in, quiet DisallowedHost
- [x] `docker-compose.prod.yml` + `.env.production.example` (single host, only nginx published)
- [x] nginx: keep the proxy's `X-Forwarded-Proto`, immutable caching for hashed assets
- [x] `docs/deployment.md` (reverse proxy, model server, backups, security checklist, sizing, troubleshooting), linked from the README
- [x] Tests (prod settings) + prod stack run locally and checked end to end

## Production CI — ✅ Completed (2026-10-07)
- [x] `scripts/prod-smoke-test.sh` (12 HTTP checks + optional live-SSE check through nginx), proven to fail on a buffering proxy
- [x] `production` CI job: build prod images, start `docker-compose.prod.yml` with throwaway secrets, run the smoke test
- [x] Deployment guide and README point at the script

## UI redesign (Graphite) — ✅ Completed (2026-10-12)
- [x] Gradient options presented; developer chose Graphite (monochrome) with dark as the default theme
- [x] Design tokens and shared utilities in `index.css` (buttons, fields, surfaces, labels, stagger, brand gradient)
- [x] Minimal restyle of every page and component (hairline rings instead of borders, one primary button per view)
- [x] Transitions: page fade-up, staggered lists, sliding tab underline, chat slide-in, pop-in menus, smooth progress bars; `prefers-reduced-motion` respected
- [x] Mermaid diagrams follow the theme; emoji icons replaced with SVG
- [x] Tests (97 frontend incl. Mermaid contract for the recolouring), E2E, README screenshots re-shot
- [x] Motion slowed ~1.5x on the developer's request (2026-10-12)

## Cursor effects and live background — ✅ Completed (2026-10-12)
- [x] Spotlight glow following the cursor on every surface (fill + edge)
- [x] 3D tilt toward the cursor on clickable cards, eased per frame for smoothness
- [x] Live background: drifting, linked dots pushed aside by the cursor; fading cursor trace
- [x] Dots brightened; dark theme base changed to black
- [x] Touch and reduced-motion fallbacks; tests (114 frontend); checked in the running app
- [x] Workspace tiles use the same tilting card as the homepage (2026-10-13)

## UI/UX pass — ✅ Completed (2026-10-13)
- [x] Audit of the real app (signed-in test user, desktop + phone width)
- [x] AI text renders inline code and bold instead of raw backticks
- [x] Dashboard badge shows the AI analysis state; failed/missing sections explain why and offer Re-analyze
- [x] Phone layout: file drawer closed by default, compact workspace bar and header, no horizontal overflow
- [x] Opaque dark surfaces (no background lines through cards/diagrams); graphite code highlight; full-width header in the workspace
- [x] Cursor trace: 60% shorter, dimmer, one smooth ribbon
- [x] Tests (122 frontend, coverage floors met) + E2E main flow
- [x] Architecture diagram: import arrows labelled only for strong links (5+); stored diagrams re-rendered by the API

## README screenshots (current design) — ✅ Completed (2026-10-13)
- [x] Fresh snapshot of commander.js (Qwen3-8B) replayed in the real UI; all six images re-shot and checked
- [x] Screenshot spec: reduced motion (no cursor effects in the shots), dashboard limited to fully analysed repos
- [x] Fixed: architecture diagrams laid out ~10x too large with reduced motion (CSS reset skips SVG) + E2E regression test

## UI sounds — ✅ Completed (2026-10-13)
- [x] Web Audio sound engine (no audio files): click ticks for tabs, cards and controls; card hover tone; cursor-trail whoosh
- [x] Starts after the first user gesture; mute toggle in the header, remembered per browser
- [x] Tests (132 frontend) + checked in a real browser

## Chat: faster and smoother — ✅ Completed (2026-10-13)
- [x] Measured real answers: time went into a "decide to search" round trip, discarded pre-search drafts and slow decoding
- [x] Question searched before the first model call (one call for most answers; 37.3 s → 19.1 s live); concise-first prompt
- [x] Streamed answer rendered like the final one and revealed at an even, adaptive pace; finished answer settles without a jump
- [x] Thinking dots, stick-to-bottom auto-scroll, transparent chat panel, soft arrival chime
- [x] Cursor-trail sound removed; click ticks softer and shorter
- [x] Tests (281 backend, 140 frontend incl. StrictMode regression) + browser check with a bursty stream + E2E
- [x] Line-by-line answers instead of the typing effect: whole lines/sentences, unrolling answer box (2026-10-13)
- [x] Chat answers shown exactly as they stream (no typing pace, caret or line reveal) (2026-10-13)

## Guided Tour on demand — ✅ Completed (2026-10-13)
- [x] Tour skipped by normal analyses (measured: 174-239 s of model time per analysis on Qwen3-8B)
- [x] `POST repos/{id}/analysis/tour/generate`: writes only the tour, free and shared; 409 while an analysis runs
- [x] Status, progress, sweeper, 48 h give-up and Re-analyze count only wanted sections
- [x] Tour tab and tour mode: "Create the guided tour" card with the time it takes; progress while written
- [x] Tests (282 backend, frontend incl. the request card)
