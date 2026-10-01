"""Hybrid retrieval: vector search + full-text search merged with Reciprocal Rank Fusion.

RRF score = sum over retrievers of 1 / (k + rank). It needs no score calibration between
cosine similarity and BM25, which is why it suits mixing the two. Either retriever can fail
(index still building, embedding model unavailable) and search degrades to the other.
"""

from __future__ import annotations

from django.conf import settings

from apps.common.logging import get_logger
from apps.search.backends import Hit, SearchBackend, get_search_backend
from apps.search.embeddings import EmbeddingProvider, get_embedding_provider

logger = get_logger(__name__)

CANDIDATES = 30


def reciprocal_rank_fusion(
    rankings: dict[str, list[Hit]], k: int | None = None, limit: int = 10
) -> list[Hit]:
    k = settings.SEARCH_RRF_K if k is None else k
    merged: dict[str, Hit] = {}
    for source, hits in rankings.items():
        for rank, hit in enumerate(hits, start=1):
            entry = merged.get(hit.chunk_id)
            if entry is None:
                entry = Hit(**{**hit.__dict__, "score": 0.0, "sources": {}})
                merged[hit.chunk_id] = entry
            entry.score += 1.0 / (k + rank)
            entry.sources[source] = rank
    ordered = sorted(merged.values(), key=lambda h: (-h.score, h.path, h.start_line))
    return ordered[:limit]


def hybrid_search(
    repo_id: str,
    query: str,
    *,
    limit: int = 10,
    backend: SearchBackend | None = None,
    embedder: EmbeddingProvider | None = None,
) -> list[Hit]:
    backend = backend or get_search_backend()
    rankings: dict[str, list[Hit]] = {}
    try:
        vector = (embedder or get_embedding_provider()).embed_query(query)
        rankings["vector"] = backend.vector_search(repo_id, vector, CANDIDATES)
    except Exception as exc:
        logger.warning("vector_search_unavailable", error=f"{type(exc).__name__}: {exc}"[:200])
    try:
        rankings["text"] = backend.text_search(repo_id, query, CANDIDATES)
    except Exception as exc:
        logger.warning("text_search_unavailable", error=f"{type(exc).__name__}: {exc}"[:200])
    return reciprocal_rank_fusion(rankings, limit=limit)
