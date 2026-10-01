"""Pipeline stage: embed every chunk of a repository snapshot.

Vectors are reused across snapshots: each chunk stores ``embed_hash`` (model + exact text),
so re-analysing a new commit only embeds chunks that actually changed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from bson import ObjectId
from pymongo import UpdateOne

from apps.common.logging import get_logger
from apps.ingestion.index_store import CHUNKS, collection
from apps.ingestion.progress import JobReporter
from apps.search.embeddings import EmbeddingError, embed_in_batches, get_embedding_provider

logger = get_logger(__name__)

MAX_EMBED_CHARS = 4000
LOOKUP_BATCH = 1000
WRITE_BATCH = 500


def embedding_text(chunk: dict[str, Any]) -> str:
    header = f"File: {chunk['path']}\n"
    if chunk.get("symbol"):
        header += f"Symbol: {chunk['symbol']}\n"
    return f"{header}{chunk.get('content', '')}"[:MAX_EMBED_CHARS]


def embed_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()


def _cached_vectors(hashes: list[str]) -> dict[str, list[float]]:
    found: dict[str, list[float]] = {}
    unique = list(dict.fromkeys(hashes))
    for start in range(0, len(unique), LOOKUP_BATCH):
        cursor = collection(CHUNKS).find(
            {
                "embed_hash": {"$in": unique[start : start + LOOKUP_BATCH]},
                "embedding": {"$exists": True},
            },
            {"embed_hash": 1, "embedding": 1, "_id": 0},
        )
        for doc in cursor:
            found.setdefault(doc["embed_hash"], doc["embedding"])
    return found


def embed_repository(repo_id: str, reporter: JobReporter) -> dict[str, int]:
    provider = get_embedding_provider()
    chunks = list(
        collection(CHUNKS).find(
            {"repo_id": ObjectId(repo_id)}, {"_id": 1, "path": 1, "symbol": 1, "content": 1}
        )
    )
    texts = [embedding_text(chunk) for chunk in chunks]
    hashes = [embed_hash(provider.model_name, text) for text in texts]
    cached = _cached_vectors(hashes)
    todo = [i for i, h in enumerate(hashes) if h not in cached]
    reporter.log(
        "embed",
        f"{len(chunks)} chunks; {len(chunks) - len(todo)} reused from earlier snapshots; "
        f"embedding {len(todo)} with {provider.model_name}",
    )

    def on_batch(done: int, total: int) -> None:
        reporter.progress("embed", done / max(total, 1), f"{done}/{total} chunks")

    fresh = embed_in_batches(provider, [texts[i] for i in todo], on_batch=on_batch)
    vectors = dict(cached)
    for index, vector in zip(todo, fresh, strict=True):
        vectors[hashes[index]] = vector

    ops = [
        UpdateOne(
            {"_id": chunk["_id"]},
            {
                "$set": {
                    "embedding": vectors[hashes[i]],
                    "embed_hash": hashes[i],
                    "embedding_model": provider.model_name,
                }
            },
        )
        for i, chunk in enumerate(chunks)
    ]
    for start in range(0, len(ops), WRITE_BATCH):
        collection(CHUNKS).bulk_write(ops[start : start + WRITE_BATCH], ordered=False)
    return {"embedded": len(todo), "reused": len(chunks) - len(todo), "total": len(chunks)}


def run_embedding_stage(job_id: str, repo_id: str) -> dict[str, int]:
    reporter = JobReporter(job_id)
    with reporter.step("embed"):
        try:
            result = embed_repository(repo_id, reporter)
        except EmbeddingError:
            raise
        except Exception as exc:
            logger.exception("embedding_crashed", repo_id=repo_id)
            raise EmbeddingError("Could not generate embeddings.") from exc
        reporter.complete("embed", f"{result['total']} chunks embedded")
    return result
