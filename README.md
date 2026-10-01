# RepoGuide

**An AI agent that onboards developers onto any GitHub codebase.** Paste a repository URL and
RepoGuide clones and analyzes it, then produces:

- a **Repo Overview** (what it does, stack, structure, how to run it);
- an interactive **Architecture Map** (Mermaid);
- a **"Start Here" reading list** of the most important files;
- a **Guided Tour** that walks through the code, including a request/command flow trace;
- a **Glossary** of project-specific terms linked to their definitions;
- a **Q&A chat** that answers with clickable `path:start-end` citations.

The LLM is a **self-hosted open model** (Qwen3-8B on vLLM) running on a free Kaggle GPU
notebook. Everything is designed for that server to disappear at any time.

> 🚧 Under active development. See [`plan.md`](plan.md) for phase progress.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.13, Django 5.2, Django REST Framework, drf-spectacular |
| Database | MongoDB (`django-mongodb-backend` + PyMongo), Atlas Vector Search + Atlas Search via `mongodb-atlas-local` |
| Jobs | Celery + Redis (worker and beat) |
| LLM | vLLM OpenAI-compatible server on Kaggle 2× T4, via the `openai` SDK behind an `LLMClient` interface |
| Embeddings | `sentence-transformers` on CPU (swappable `EmbeddingProvider`) |
| Parsing | tree-sitter (Python, JS/TS, Java, Go) |
| Frontend | React 19, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS |

## Quick start (Docker Compose)

```bash
cp .env.example .env          # then edit secrets
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8010/api/docs/
- Model health: http://localhost:8010/api/llm/health

Start the model server by following [`kaggle/README.md`](kaggle/README.md), then point the
running stack at it:

```bash
docker compose exec backend python manage.py set_llm_url https://<your-tunnel>.trycloudflare.com
```

## Development

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && black --check . && pytest

# Frontend
cd frontend
npm install
npm run lint && npm run typecheck && npm test
```

Tests marked `mongo` need MongoDB (`docker compose up mongo`). They are skipped locally when it
is not reachable, and are required in CI.

## Repository layout

```
backend/    Django project (config/) and apps (accounts, llm, common, ...)
frontend/   React single-page app
kaggle/     vLLM model server notebook + guide
```

_Architecture diagram, screenshots, design decisions and known limitations will be documented
here as the phases land._
