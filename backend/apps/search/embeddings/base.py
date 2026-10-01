from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Embedding failed after retries (message is safe to show to users)."""


class EmbeddingProvider(ABC):
    """Turns text into fixed-size, L2-normalised vectors."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...
