"""PyMongo repository layer for the high-volume code index collections.

Collections: ``files`` (metadata + symbols), ``blobs`` (content, keyed by git blob SHA so it
dedupes across commits and repos), ``code_chunks`` and ``dependency_edges``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, InsertOne, UpdateOne
from pymongo.collection import Collection

from apps.common.mongo import get_db

FILES = "files"
BLOBS = "blobs"
CHUNKS = "code_chunks"
EDGES = "dependency_edges"
AGENT_LOGS = "agent_logs"

BATCH = 500


def git_blob_sha(data: bytes) -> str:
    """Same identifier git uses for blob objects."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _oid(repo_id: str | ObjectId) -> ObjectId:
    return repo_id if isinstance(repo_id, ObjectId) else ObjectId(str(repo_id))


def _batched(items: Iterable[Any], size: int = BATCH) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def collection(name: str) -> Collection:
    return get_db()[name]


def ensure_indexes() -> list[str]:
    """Create regular (non-search) indexes. Idempotent."""
    created: list[str] = []
    specs: dict[str, list[IndexModel]] = {
        FILES: [
            IndexModel(
                [("repo_id", ASCENDING), ("path", ASCENDING)], unique=True, name="repo_path"
            ),
            IndexModel([("repo_id", ASCENDING), ("symbols.name", ASCENDING)], name="repo_symbol"),
        ],
        CHUNKS: [
            IndexModel(
                [("repo_id", ASCENDING), ("path", ASCENDING), ("start_line", ASCENDING)],
                name="repo_path_line",
            ),
            IndexModel([("repo_id", ASCENDING), ("symbol", ASCENDING)], name="repo_symbol"),
        ],
        EDGES: [
            IndexModel([("repo_id", ASCENDING), ("src", ASCENDING)], name="repo_src"),
            IndexModel([("repo_id", ASCENDING), ("dst", ASCENDING)], name="repo_dst"),
            IndexModel([("repo_id", ASCENDING), ("src_dir", ASCENDING)], name="repo_src_dir"),
        ],
        AGENT_LOGS: [
            IndexModel([("repo_id", ASCENDING), ("ts", DESCENDING)], name="repo_ts"),
            IndexModel([("ts", ASCENDING)], expireAfterSeconds=30 * 24 * 3600, name="ttl_30d"),
        ],
    }
    db = get_db()
    for name, models in specs.items():
        created += db[name].create_indexes(models)
    return created


def clear_repo_index(repo_id: str | ObjectId) -> None:
    oid = _oid(repo_id)
    for name in (FILES, CHUNKS, EDGES):
        collection(name).delete_many({"repo_id": oid})


def save_blobs(blobs: dict[str, str]) -> None:
    ops = [
        UpdateOne({"_id": sha}, {"$setOnInsert": {"content": content}}, upsert=True)
        for sha, content in blobs.items()
    ]
    for batch in _batched(ops):
        collection(BLOBS).bulk_write(batch, ordered=False)


def _insert(name: str, repo_id: ObjectId, documents: Iterable[dict[str, Any]]) -> int:
    count = 0
    for batch in _batched(InsertOne({**doc, "repo_id": repo_id}) for doc in documents):
        collection(name).bulk_write(batch, ordered=False)
        count += len(batch)
    return count


def save_files(repo_id: str | ObjectId, files: Iterable[dict[str, Any]]) -> int:
    return _insert(FILES, _oid(repo_id), files)


def save_chunks(repo_id: str | ObjectId, chunks: Iterable[dict[str, Any]]) -> int:
    return _insert(CHUNKS, _oid(repo_id), chunks)


def save_edges(repo_id: str | ObjectId, edges: Iterable[dict[str, Any]]) -> int:
    return _insert(EDGES, _oid(repo_id), edges)


# --- reads ------------------------------------------------------------------------------


def list_files(repo_id: str | ObjectId) -> list[dict[str, Any]]:
    cursor = collection(FILES).find(
        {"repo_id": _oid(repo_id)},
        {"_id": 0, "path": 1, "language": 1, "size": 1, "lines": 1},
    )
    return sorted(cursor, key=lambda f: f["path"])


def get_file(repo_id: str | ObjectId, path: str) -> dict[str, Any] | None:
    return collection(FILES).find_one({"repo_id": _oid(repo_id), "path": path}, {"_id": 0})


def get_blob(sha: str) -> str | None:
    doc = collection(BLOBS).find_one({"_id": sha})
    return doc["content"] if doc else None


def count_chunks(repo_id: str | ObjectId) -> int:
    return collection(CHUNKS).count_documents({"repo_id": _oid(repo_id)})
