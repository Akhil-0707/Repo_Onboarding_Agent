"""Embeddings from any OpenAI-compatible ``/v1/embeddings`` endpoint (e.g. vLLM on Kaggle)."""

from __future__ import annotations

import math

import openai
from django.conf import settings

from apps.search.embeddings.base import EmbeddingError, EmbeddingProvider


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        dimensions: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model_name = model_name or settings.EMBEDDING_MODEL
        self._dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self._client = openai.OpenAI(
            base_url=base_url or settings.EMBEDDING_BASE_URL,
            api_key=api_key or settings.EMBEDDING_API_KEY or "not-set",
            timeout=timeout,
            max_retries=0,  # retries are handled by embed_in_batches
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(model=self._model_name, input=texts)
        except openai.APIStatusError as exc:
            if exc.status_code < 500 and exc.status_code != 429:
                raise EmbeddingError(f"Embedding request rejected ({exc.status_code}).") from exc
            raise
        vectors = [
            _normalise(list(item.embedding))
            for item in sorted(response.data, key=lambda d: d.index)
        ]
        if vectors and len(vectors[0]) != self._dimensions:
            raise EmbeddingError(
                f"Embedding endpoint returned {len(vectors[0])}-d vectors; "
                f"EMBEDDING_DIMENSIONS is {self._dimensions}."
            )
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([f"{settings.EMBEDDING_DOCUMENT_PREFIX}{t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"{settings.EMBEDDING_QUERY_PREFIX}{text}"])[0]
