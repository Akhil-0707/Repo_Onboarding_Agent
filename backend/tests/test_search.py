"""Embeddings, RRF fusion and hybrid search (no database needed)."""

from __future__ import annotations

import math

import pytest

from apps.search.backends import Hit, InMemorySearchBackend, SearchBackend, code_tokens
from apps.search.embeddings import EmbeddingError, EmbeddingProvider, embed_in_batches
from apps.search.embeddings.openai_compat import OpenAICompatibleEmbeddingProvider
from apps.search.hybrid import hybrid_search, reciprocal_rank_fusion
from apps.search.indexes import matches, text_index_definition, vector_index_definition
from tests.fakes.embeddings import HashingEmbeddingProvider
from tests.fakes.openai_server import FakeOpenAIServer


def hit(chunk_id: str, path: str = "a.py", line: int = 1) -> Hit:
    return Hit(chunk_id=chunk_id, path=path, start_line=line, end_line=line + 1, content="x")


# --- RRF -----------------------------------------------------------------------------------


def test_rrf_rewards_agreement_between_retrievers() -> None:
    vector = [hit("a"), hit("b"), hit("c")]
    text = [hit("c"), hit("d"), hit("a")]
    merged = reciprocal_rank_fusion({"vector": vector, "text": text}, k=60, limit=10)

    order = [h.chunk_id for h in merged]
    assert order[:2] == ["a", "c"]  # found by both
    a = merged[0]
    assert math.isclose(a.score, 1 / 61 + 1 / 63)
    assert a.sources == {"vector": 1, "text": 3}
    assert set(order) == {"a", "b", "c", "d"}


def test_rrf_limit_and_empty_input() -> None:
    assert reciprocal_rank_fusion({}, k=60) == []
    hits = [hit(str(i)) for i in range(20)]
    assert len(reciprocal_rank_fusion({"text": hits}, k=60, limit=5)) == 5


class _Backend(SearchBackend):
    def __init__(self, vector: list[Hit] | Exception, text: list[Hit] | Exception) -> None:
        self.vector, self.text = vector, text

    def vector_search(self, repo_id: str, vector: list[float], limit: int) -> list[Hit]:
        if isinstance(self.vector, Exception):
            raise self.vector
        return self.vector

    def text_search(self, repo_id: str, query: str, limit: int) -> list[Hit]:
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def test_hybrid_degrades_when_vector_index_is_unavailable() -> None:
    backend = _Backend(RuntimeError("index building"), [hit("t1"), hit("t2")])
    results = hybrid_search("r", "query", backend=backend, embedder=HashingEmbeddingProvider())
    assert [h.chunk_id for h in results] == ["t1", "t2"]
    assert all(h.sources == {"text": i + 1} for i, h in enumerate(results))


def test_hybrid_degrades_when_embedding_fails() -> None:
    class Broken(HashingEmbeddingProvider):
        def embed_query(self, text: str) -> list[float]:
            raise EmbeddingError("model missing")

    results = hybrid_search("r", "q", backend=_Backend([hit("v")], [hit("t")]), embedder=Broken())
    assert [h.chunk_id for h in results] == ["t"]


def test_in_memory_backend_matches_identifier_parts() -> None:
    docs = [
        {"_id": "1", "repo_id": "r", "path": "users.py", "start_line": 1, "end_line": 5,
         "content": "def getUserById(id): ...", "symbol": "getUserById"},
        {"_id": "2", "repo_id": "r", "path": "orders.py", "start_line": 1, "end_line": 5,
         "content": "def list_orders(): ...", "symbol": "list_orders"},
        {"_id": "3", "repo_id": "other", "path": "users.py", "start_line": 1, "end_line": 2,
         "content": "user", "symbol": None},
    ]  # fmt: skip
    hits = InMemorySearchBackend(docs).text_search("r", "user by id", 10)
    assert [h.chunk_id for h in hits] == ["1"]
    assert {"get", "user", "by", "id", "getuserbyid"} <= code_tokens("getUserById")


# --- embedding batching ---------------------------------------------------------------------


class Flaky(EmbeddingProvider):
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.batches: list[int] = []

    model_name = "flaky"  # type: ignore[assignment]
    dimensions = 2  # type: ignore[assignment]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.failures:
            self.failures -= 1
            raise ConnectionError("blip")
        self.batches.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


def test_batches_retry_with_backoff_and_report_progress() -> None:
    provider = Flaky(failures=2)
    progress: list[tuple[int, int]] = []
    sleeps: list[float] = []
    vectors = embed_in_batches(
        provider,
        [f"t{i}" for i in range(5)],
        batch_size=2,
        max_retries=3,
        on_batch=lambda done, total: progress.append((done, total)),
        sleep=sleeps.append,
    )
    assert len(vectors) == 5
    assert provider.batches == [2, 2, 1]
    assert progress == [(2, 5), (4, 5), (5, 5)]
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 0.5


def test_batches_give_up_after_retries() -> None:
    with pytest.raises(EmbeddingError, match="after 2 attempts"):
        embed_in_batches(
            Flaky(failures=5), ["a"], batch_size=1, max_retries=1, sleep=lambda _: None
        )


def test_wrong_vector_count_is_an_error() -> None:
    class Short(Flaky):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0]]

    with pytest.raises(EmbeddingError, match="wrong number"):
        embed_in_batches(Short(0), ["a", "b"], batch_size=2, sleep=lambda _: None)


def test_openai_compatible_embeddings(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.embedding_dimensions = 4
    fake_llm.embedding_failures = 1
    provider = OpenAICompatibleEmbeddingProvider(
        base_url=fake_llm.url, api_key="test-key", model_name="emb", dimensions=4
    )
    vectors = embed_in_batches(provider, ["a", "bbb"], batch_size=8, sleep=lambda _: None)

    assert len(vectors) == 2
    assert all(math.isclose(sum(v * v for v in vec), 1.0) for vec in vectors)  # normalised
    body = fake_llm.requests[-1]
    assert body["model"] == "emb" and body["input"] == ["a", "bbb"]


def test_openai_compatible_dimension_mismatch(fake_llm: FakeOpenAIServer) -> None:
    fake_llm.embedding_dimensions = 8
    provider = OpenAICompatibleEmbeddingProvider(
        base_url=fake_llm.url, api_key="k", model_name="emb", dimensions=4
    )
    with pytest.raises(EmbeddingError, match="8-d"):
        provider.embed_documents(["a"])


# --- index definitions ------------------------------------------------------------------------


def test_index_definition_matching_tolerates_atlas_defaults() -> None:
    desired = text_index_definition()
    stored = {
        **desired,
        "mappings": {
            "dynamic": False,
            "fields": {
                name: {**spec, "indexOptions": "offsets", "norms": "include"}
                for name, spec in desired["mappings"]["fields"].items()
            },
        },
    }
    assert matches(desired, stored)
    assert not matches(vector_index_definition(384), vector_index_definition(768))


def test_embedding_warmup_runs_in_the_background(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.search import warmup

    queries: list[str] = []

    class Recorder:
        def embed_query(self, text: str) -> list[float]:
            queries.append(text)
            raise RuntimeError("no model here")  # failures are logged, never raised

    monkeypatch.setattr(warmup, "get_embedding_provider", Recorder)
    warmup.warm_up_embeddings().join(timeout=5)
    assert queries == ["warm up"]
