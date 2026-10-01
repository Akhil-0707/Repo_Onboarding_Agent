"""Vector and full-text retrieval over ``code_chunks`` behind a swappable interface."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from bson import ObjectId
from django.conf import settings

from apps.ingestion.index_store import CHUNKS, collection

HIT_FIELDS = {"_id": 1, "path": 1, "language": 1, "symbol": 1, "kind": 1}
HIT_FIELDS |= {"start_line": 1, "end_line": 1, "content": 1}


@dataclass
class Hit:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    content: str
    symbol: str | None = None
    kind: str | None = None
    language: str | None = None
    score: float = 0.0
    sources: dict[str, int] = field(default_factory=dict)
    """Rank (1-based) of this chunk in each retriever that returned it."""

    @classmethod
    def from_doc(cls, doc: dict[str, Any], score: float = 0.0) -> Hit:
        return cls(
            chunk_id=str(doc["_id"]),
            path=doc["path"],
            start_line=int(doc["start_line"]),
            end_line=int(doc["end_line"]),
            content=doc.get("content", ""),
            symbol=doc.get("symbol"),
            kind=doc.get("kind"),
            language=doc.get("language"),
            score=float(score),
        )


class SearchBackend(ABC):
    @abstractmethod
    def vector_search(self, repo_id: str, vector: list[float], limit: int) -> list[Hit]: ...

    @abstractmethod
    def text_search(self, repo_id: str, query: str, limit: int) -> list[Hit]: ...


class AtlasSearchBackend(SearchBackend):
    def vector_search(self, repo_id: str, vector: list[float], limit: int) -> list[Hit]:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": settings.SEARCH_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": vector,
                    "numCandidates": max(limit * 10, 100),
                    "limit": limit,
                    "filter": {"repo_id": ObjectId(repo_id)},
                }
            },
            {"$project": {**HIT_FIELDS, "score": {"$meta": "vectorSearchScore"}}},
        ]
        return [
            Hit.from_doc(doc, doc.get("score", 0.0))
            for doc in collection(CHUNKS).aggregate(pipeline)
        ]

    def text_search(self, repo_id: str, query: str, limit: int) -> list[Hit]:
        pipeline = [
            {
                "$search": {
                    "index": settings.SEARCH_TEXT_INDEX,
                    "compound": {
                        "filter": [{"equals": {"path": "repo_id", "value": ObjectId(repo_id)}}],
                        "should": [
                            {"text": {"query": query, "path": "content"}},
                            {
                                "text": {
                                    "query": query,
                                    "path": "symbol",
                                    "score": {"boost": {"value": 3}},
                                }
                            },
                            {
                                "text": {
                                    "query": query,
                                    "path": "path",
                                    "score": {"boost": {"value": 2}},
                                }
                            },
                        ],
                        "minimumShouldMatch": 1,
                    },
                }
            },
            {"$limit": limit},
            {"$project": {**HIT_FIELDS, "score": {"$meta": "searchScore"}}},
        ]
        return [
            Hit.from_doc(doc, doc.get("score", 0.0))
            for doc in collection(CHUNKS).aggregate(pipeline)
        ]


_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def code_tokens(text: str) -> set[str]:
    """Approximation of the Atlas ``code`` analyzer (used by the in-memory backend)."""
    tokens: set[str] = set()
    for word in _WORD.findall(text):
        tokens.add(word.lower())
        tokens.update(part.lower() for part in _CAMEL.findall(word))
    return tokens


class InMemorySearchBackend(SearchBackend):
    """Brute-force search over chunks loaded from Mongo (tests, or when indexes are missing)."""

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self._documents = documents

    def _docs(self, repo_id: str) -> list[dict[str, Any]]:
        if self._documents is not None:
            return [d for d in self._documents if str(d["repo_id"]) == str(repo_id)]
        projection = {**HIT_FIELDS, "embedding": 1, "repo_id": 1}
        return list(collection(CHUNKS).find({"repo_id": ObjectId(repo_id)}, projection))

    def vector_search(self, repo_id: str, vector: list[float], limit: int) -> list[Hit]:
        scored = []
        for doc in self._docs(repo_id):
            embedding = doc.get("embedding")
            if not embedding:
                continue
            dot = sum(a * b for a, b in zip(vector, embedding, strict=False))
            norm = math.sqrt(sum(a * a for a in embedding)) * math.sqrt(sum(b * b for b in vector))
            scored.append((dot / (norm or 1.0), doc))
        scored.sort(key=lambda item: -item[0])
        return [Hit.from_doc(doc, score) for score, doc in scored[:limit]]

    def text_search(self, repo_id: str, query: str, limit: int) -> list[Hit]:
        wanted = code_tokens(query)
        if not wanted:
            return []
        scored = []
        for doc in self._docs(repo_id):
            content = code_tokens(doc.get("content", ""))
            symbol = code_tokens(doc.get("symbol") or "")
            path = code_tokens(doc.get("path", ""))
            score = len(wanted & content) + 3 * len(wanted & symbol) + 2 * len(wanted & path)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["start_line"]))
        return [Hit.from_doc(doc, score) for score, doc in scored[:limit]]


_backend: SearchBackend | None = None


def get_search_backend() -> SearchBackend:
    global _backend
    if _backend is None:
        _backend = AtlasSearchBackend()
    return _backend


def set_search_backend(backend: SearchBackend | None) -> None:
    global _backend
    _backend = backend
