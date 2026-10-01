"""Embedding providers behind a small interface, plus batching with retry/backoff."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from django.conf import settings

from apps.common.logging import get_logger
from apps.search.embeddings.base import EmbeddingError, EmbeddingProvider

logger = get_logger(__name__)

__all__ = [
    "EmbeddingError",
    "EmbeddingProvider",
    "embed_in_batches",
    "get_embedding_provider",
    "set_embedding_provider",
]

_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        if settings.EMBEDDING_PROVIDER == "openai":
            from apps.search.embeddings.openai_compat import OpenAICompatibleEmbeddingProvider

            _provider = OpenAICompatibleEmbeddingProvider()
        else:
            from apps.search.embeddings.local import SentenceTransformerProvider

            _provider = SentenceTransformerProvider()
    return _provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    global _provider
    _provider = provider


def embed_in_batches(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    batch_size: int | None = None,
    max_retries: int | None = None,
    backoff_base: float = 1.0,
    on_batch: Callable[[int, int], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    """Embed ``texts`` in batches, retrying each failed batch with exponential backoff.

    ``on_batch(done, total)`` is called after every successful batch (progress reporting).
    """
    batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
    retries = settings.EMBEDDING_MAX_RETRIES if max_retries is None else max_retries
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        for attempt in range(retries + 1):
            try:
                result = provider.embed_documents(batch)
                break
            except EmbeddingError:
                raise
            except Exception as exc:
                if attempt >= retries:
                    raise EmbeddingError(
                        f"Embedding failed after {retries + 1} attempts ({type(exc).__name__})."
                    ) from exc
                jitter = random.uniform(0.5, 1.0)  # noqa: S311 - not crypto
                delay = min(30.0, backoff_base * 2**attempt) * jitter
                logger.warning(
                    "embedding_batch_retry", attempt=attempt + 1, error=type(exc).__name__
                )
                sleep(delay)
        if len(result) != len(batch):
            raise EmbeddingError("Embedding provider returned the wrong number of vectors.")
        vectors.extend(result)
        if on_batch:
            on_batch(len(vectors), len(texts))
    return vectors
