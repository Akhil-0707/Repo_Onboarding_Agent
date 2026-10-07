"""Real Atlas Vector Search + Atlas Search on mongodb-atlas-local (mongot).

Validates the index definitions (including the camelCase-splitting code analyzer) and the
aggregation pipelines end to end.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from apps.accounts.models import User
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.progress import initial_steps
from apps.ingestion.tasks import start_pipeline
from apps.repos.models import IngestionJob, Repository
from apps.search.backends import AtlasSearchBackend, Hit, set_search_backend
from apps.search.hybrid import hybrid_search
from apps.search.indexes import ensure_search_indexes
from tests.conftest_fixtures import FIXTURES
from tests.fakes.embeddings import HashingEmbeddingProvider

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]


def eventually(fetch: Callable[[], list[Hit]], timeout: float = 60.0) -> list[Hit]:
    """mongot syncs from the oplog asynchronously; poll until results appear."""
    deadline = time.monotonic() + timeout
    while True:
        hits = fetch()
        if hits or time.monotonic() > deadline:
            return hits
        time.sleep(1.0)


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> Any:
    ensure_search_indexes(wait=True, timeout=180)
    index_store.ensure_indexes()
    set_event_bus(InMemoryEventBus())

    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / "js_app", destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)
    user = User.objects.create(username="atlas", github_id=5)
    repository = Repository.objects.create(
        url="https://github.com/acme/js_app", url_key="github.com/acme/js_app", owner="acme",
        name="js_app", default_branch="main", commit_sha="e" * 40,
    )  # fmt: skip
    job = IngestionJob.objects.create(repository=repository, user=user, steps=initial_steps())
    start_pipeline(str(job.pk))
    repository.refresh_from_db()
    assert repository.status == "ready"
    yield repository
    index_store.clear_repo_index(repository.pk)
    set_event_bus(None)


def test_text_search_splits_camel_case_identifiers(repo: Repository) -> None:
    backend = AtlasSearchBackend()
    hits = eventually(lambda: backend.text_search(str(repo.pk), "user store", 10))
    assert hits, "Atlas Search returned nothing"
    assert hits[0].path == "src/services/users.ts"  # matches `UserStore` via case split


def test_text_search_is_scoped_to_the_repository(repo: Repository) -> None:
    from bson import ObjectId

    backend = AtlasSearchBackend()
    eventually(lambda: backend.text_search(str(repo.pk), "router", 5))
    assert backend.text_search(str(ObjectId()), "router", 5) == []


def test_vector_and_hybrid_search(repo: Repository) -> None:
    backend = AtlasSearchBackend()
    embedder = HashingEmbeddingProvider()
    vector = embedder.embed_query("createServer express app listen")
    vector_hits = eventually(lambda: backend.vector_search(str(repo.pk), vector, 5))
    assert vector_hits and {h.path for h in vector_hits} & {"src/server.ts", "src/index.ts"}

    # The text index syncs independently of the vector index (slower under parallel test load).
    assert eventually(lambda: backend.text_search(str(repo.pk), "getUser route handler", 5))
    set_search_backend(backend)
    hybrid = hybrid_search(str(repo.pk), "getUser route handler", limit=5, embedder=embedder)
    assert hybrid and any(h.sources.keys() == {"vector", "text"} for h in hybrid)
    assert {"src/routes/index.ts", "src/services/users.ts"} & {h.path for h in hybrid}
