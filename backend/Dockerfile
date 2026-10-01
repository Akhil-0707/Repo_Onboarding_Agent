# Backend image used by the API (uvicorn), the Celery worker and Celery beat.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/app/.cache/huggingface

# git is needed to shallow-clone analysed repositories (never to run their code).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /home/app/.cache/huggingface \
    && chown -R app:app /home/app/.cache
WORKDIR /app

# Local embeddings: CPU-only torch (the default wheel pulls ~3 GB of CUDA libraries).
# Installed first so code/requirement changes do not invalidate this heavy layer.
ARG INSTALL_ML=true
COPY requirements-ml.txt ./
RUN if [ "$INSTALL_ML" = "true" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 \
      && pip install -r requirements-ml.txt; \
    fi

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY --chown=app:app . .

USER app
EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["web"]
