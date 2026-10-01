# Backend image used by the API (uvicorn), the Celery worker and Celery beat.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git is needed to shallow-clone analysed repositories (never to run their code).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY --chown=app:app . .

USER app
# tree-sitter grammars are downloaded on first use; bake them into the image instead.
RUN python -c "import tree_sitter_language_pack as t; t.download(['python','javascript','typescript','tsx','java','go'])"
EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["web"]
