# RepoGuide — Handover

Living document. Update after every meaningful step. A fresh session should be able to continue from here alone.

## Current status
- **Phase:** 1 — Scaffolding (in progress)
- **Last commit:** (see `git log -1`)
- **In progress:** initial repo setup

## How to run
_Filled in as the scaffold lands._

## Key decisions (and why)
| Decision | Reason |
|---|---|
| Django **5.2 LTS** + `django-mongodb-backend` 5.2.x | Spec requires Django 5.x; backend is GA since 5.2.0 (2025-09); simplejwt supports up to 5.2 |
| ORM for app entities, **PyMongo repository layer** for chunks/blobs/edges/logs | Bulk writes + `$vectorSearch`/`$search` aggregations are simplest in PyMongo; ORM keeps admin/auth/DRF |
| `blobs` collection (content-addressed by git blob SHA) | Clone is deleted after ingestion but viewer/agent tools need file contents |
| LLM: **Qwen3-8B**, vLLM, fp16, TP=2 on Kaggle 2×T4, `hermes` tool parser | Reliable tool calling, fits T4 memory; T4 has no bf16 |
| Embeddings: `BAAI/bge-small-en-v1.5` on CPU | Fast, no `trust_remote_code`; hybrid search compensates for not being code-specific |
| Architecture map: model outputs JSON graph, server renders Mermaid | Small models produce invalid Mermaid syntax often |
| Shiki (not Monaco) for code viewing | Read-only viewer; much lighter |
| Hand-written GitHub OAuth | Avoids allauth/social-auth model incompatibilities with Mongo |
| SSE via async Django views + fetch-stream on frontend | Needs Authorization header and POST (EventSource can't) |
| `est_cost` uses configurable per-1k prices, default 0 | Self-hosted model; tokens + latency are the primary metrics |

## Completed
- Plan approved (see `plan.md`).

## Known issues / TODOs / blockers
- None yet.

## Next steps
- Finish Phase 1 tasks in `plan.md`.

## Gotchas
- Project lives under OneDrive: keep `node_modules` in a Docker named volume; OneDrive sync can lock files.
- Atlas Local search indexes build asynchronously; wait for them before querying.
- Kaggle sessions time out — the model can vanish any time; everything must tolerate `ModelOfflineError`.

## Progress log
- 2026-10-01 — Plan approved; repo initialised with remote `origin` (github.com/Akhil-0707/Repo_Onboarding_Agent).
