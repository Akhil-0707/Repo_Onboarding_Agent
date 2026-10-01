"""sentence-transformers on CPU, inside the worker (no dependency on the Kaggle model server)."""

from __future__ import annotations

import threading
from typing import Any

from django.conf import settings

from apps.common.logging import get_logger
from apps.search.embeddings.base import EmbeddingError, EmbeddingProvider

logger = get_logger(__name__)

_models: dict[str, Any] = {}
_lock = threading.Lock()


def _load(model_name: str) -> Any:
    with _lock:
        if model_name not in _models:
            try:
                import torch
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on the image
                raise EmbeddingError(
                    "Local embeddings need sentence-transformers (see requirements-ml.txt)."
                ) from exc
            if settings.EMBEDDING_THREADS:
                torch.set_num_threads(settings.EMBEDDING_THREADS)
            logger.info("embedding_model_loading", model=model_name)
            _models[model_name] = SentenceTransformer(model_name, device="cpu")
        return _models[model_name]


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str | None = None, dimensions: int | None = None) -> None:
        self._model_name = model_name or settings.EMBEDDING_MODEL
        self._dimensions = dimensions or settings.EMBEDDING_DIMENSIONS

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = _load(self._model_name)
        vectors = model.encode(
            texts,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if vectors.shape[1] != self._dimensions:
            raise EmbeddingError(
                f"Model {self._model_name} produces {vectors.shape[1]}-d vectors but "
                f"EMBEDDING_DIMENSIONS is {self._dimensions}."
            )
        return [row.tolist() for row in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = settings.EMBEDDING_DOCUMENT_PREFIX
        return self._encode([f"{prefix}{t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"{settings.EMBEDDING_QUERY_PREFIX}{text}"])[0]
