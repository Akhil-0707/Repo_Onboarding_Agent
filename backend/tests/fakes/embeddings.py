"""Deterministic embedding provider for tests: hashed bag of code tokens, L2-normalised.

Texts sharing identifiers get similar vectors, so vector search behaves plausibly without
downloading a model.
"""

from __future__ import annotations

import hashlib
import math

from apps.search.backends import code_tokens
from apps.search.embeddings import EmbeddingProvider


class HashingEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions
        self.calls: list[int] = []

    @property
    def model_name(self) -> str:
        return "test-hashing-embedder"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in code_tokens(text):
            digest = hashlib.md5(token.encode(), usedforsecurity=False).digest()
            vector[int.from_bytes(digest[:4], "little") % self._dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
