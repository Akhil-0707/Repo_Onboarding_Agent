from __future__ import annotations

import threading

from apps.common.logging import get_logger
from apps.search.embeddings import get_embedding_provider

logger = get_logger(__name__)


def _warm() -> None:
    try:
        get_embedding_provider().embed_query("warm up")
        logger.info("embedding_model_warmed_up")
    except Exception as exc:  # search degrades to keyword-only; never break startup
        logger.warning("embedding_warmup_failed", error=str(exc))


def warm_up_embeddings() -> threading.Thread:
    thread = threading.Thread(target=_warm, name="embedding-warmup", daemon=True)
    thread.start()
    return thread
