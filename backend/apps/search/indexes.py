"""Atlas Vector Search + Atlas Search index definitions for ``code_chunks``.

Both live next to the data in MongoDB (``mongodb-atlas-local`` runs mongot locally). Indexes
build asynchronously, so ``ensure_search_indexes`` can optionally wait until they are
queryable; search falls back gracefully while they are not.
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from apps.common.logging import get_logger
from apps.ingestion.index_store import CHUNKS, collection

logger = get_logger(__name__)


def vector_index_definition(dimensions: int) -> dict[str, Any]:
    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": dimensions,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "repo_id"},
        ]
    }


def text_index_definition() -> dict[str, Any]:
    # "code" analyzer: split on non-word characters, then split identifiers on case changes
    # and digits (getUserById -> get, user, by, id) while keeping the original token.
    return {
        "analyzer": "code",
        "searchAnalyzer": "code",
        "analyzers": [
            {
                "name": "code",
                "tokenizer": {"type": "regexSplit", "pattern": "[^A-Za-z0-9_]+"},
                "tokenFilters": [
                    {
                        "type": "wordDelimiterGraph",
                        "delimiterOptions": {
                            "generateWordParts": True,
                            "generateNumberParts": True,
                            "splitOnCaseChange": True,
                            "splitOnNumerics": True,
                            "preserveOriginal": True,
                        },
                    },
                    {"type": "lowercase"},
                ],
            }
        ],
        "mappings": {
            "dynamic": False,
            "fields": {
                "content": {"type": "string"},
                "symbol": {"type": "string"},
                "path": {"type": "string"},
                "repo_id": {"type": "objectId"},
            },
        },
    }


def desired_indexes() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        settings.SEARCH_VECTOR_INDEX: (
            "vectorSearch",
            vector_index_definition(settings.EMBEDDING_DIMENSIONS),
        ),
        settings.SEARCH_TEXT_INDEX: ("search", text_index_definition()),
    }


def matches(desired: Any, actual: Any) -> bool:
    """True when every value we asked for is present in what Atlas stored (Atlas adds
    defaults such as ``indexOptions`` and ``norms``, so plain equality never holds)."""
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(
            key in actual and matches(value, actual[key]) for key, value in desired.items()
        )
    if isinstance(desired, list):
        return (
            isinstance(actual, list)
            and len(desired) == len(actual)
            and all(matches(d, a) for d, a in zip(desired, actual, strict=True))
        )
    return desired == actual


def _existing() -> dict[str, dict[str, Any]]:
    try:
        return {index["name"]: index for index in collection(CHUNKS).list_search_indexes()}
    except OperationFailure as exc:
        if "not found" in str(exc).lower() or exc.code == 26:  # namespace does not exist yet
            return {}
        raise


def ensure_search_indexes(*, wait: bool = False, timeout: float = 180.0) -> dict[str, str]:
    """Create or update the search indexes. Returns ``{name: action}``."""
    chunks = collection(CHUNKS)
    if CHUNKS not in chunks.database.list_collection_names():
        chunks.database.create_collection(CHUNKS)

    existing = _existing()
    actions: dict[str, str] = {}
    for name, (kind, definition) in desired_indexes().items():
        current = existing.get(name)
        if current is None:
            chunks.create_search_index(
                SearchIndexModel(definition=definition, name=name, type=kind)
            )
            actions[name] = "created"
        elif not matches(definition, current.get("latestDefinition")):
            chunks.update_search_index(name, definition)
            actions[name] = "updated"
        else:
            actions[name] = "unchanged"
    logger.info("search_indexes_ensured", **actions)
    if wait:
        wait_until_queryable(timeout=timeout)
    return actions


def index_status() -> dict[str, bool]:
    existing = _existing()
    return {name: bool(existing.get(name, {}).get("queryable")) for name in desired_indexes()}


def wait_until_queryable(timeout: float = 180.0, interval: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        status = index_status()
        if all(status.values()):
            return
        if time.monotonic() > deadline:
            raise TimeoutError(f"Search indexes not queryable after {timeout:.0f}s: {status}")
        time.sleep(interval)
