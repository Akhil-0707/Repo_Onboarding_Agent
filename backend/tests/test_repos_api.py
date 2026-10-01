"""Repository API + ingestion pipeline end to end (needs MongoDB)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest
from bson import ObjectId
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.errors import LimitExceededError, RepositoryNotFoundError
from apps.ingestion.github import CodeHost, RepoInfo, RepoRef, set_code_host
from apps.ingestion.progress import channel
from apps.repos.models import IngestionJob, Repository, UserRepository
from apps.repos.stream import job_events
from tests.conftest_fixtures import FIXTURES, add_noise

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]

SHA = "a" * 40


class FakeCodeHost(CodeHost):
    def __init__(self) -> None:
        self.size_kb = 50
        self.sha = SHA
        self.calls: list[tuple[RepoRef, str | None]] = []

    def resolve(self, ref: RepoRef, token: str | None) -> RepoInfo:
        self.calls.append((ref, token))
        if ref.name == "missing":
            raise RepositoryNotFoundError("Repository not found.")
        return RepoInfo(
            owner="Acme",
            name=ref.name,
            description="Fixture repo",
            default_branch="main",
            head_sha=self.sha,
            private=False,
            size_kb=self.size_kb,
            html_url=f"https://github.com/Acme/{ref.name}",
        )


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> Any:
    index_store.ensure_indexes()
    for name in (index_store.FILES, index_store.CHUNKS, index_store.EDGES):
        index_store.collection(name).delete_many({})
    host = FakeCodeHost()
    bus = InMemoryEventBus()
    set_code_host(host)
    set_event_bus(bus)

    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / url.rsplit("/", 1)[-1], destination)
        add_noise(destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)
    yield host, bus
    set_code_host(None)
    set_event_bus(None)


def client_for(username: str) -> tuple[APIClient, User]:
    user = User.objects.create(username=username, github_id=abs(hash(username)) % 10**9)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user).access}")
    return client, user


def analyze(client: APIClient, url: str = "https://github.com/acme/py_app") -> Any:
    return client.post("/api/repos", {"url": url}, format="json")


def test_create_runs_pipeline_and_indexes_repo(_setup: Any) -> None:
    _host, bus = _setup
    client, _ = client_for("ada")

    response = analyze(client)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["created"] is True and body["cached"] is False
    repo = Repository.objects.get(pk=body["repository"]["id"])
    assert repo.status == "ready", repo.error
    assert repo.full_name == "Acme/py_app"
    assert repo.stats["files"] >= 7
    assert repo.stats["chunks"] > repo.stats["files"] - 3
    assert repo.stats["dependency_edges"] >= 3
    assert repo.stats["skipped"]["ignored_dir"] >= 2
    assert "Flask" in repo.frameworks
    assert repo.languages.get("python") == 100.0

    job = IngestionJob.objects.get(pk=body["job"]["id"])
    assert job.status == "done" and job.progress == 100
    assert {s["key"]: s["status"] for s in job.steps} == {
        "resolve": "done",
        "clone": "done",
        "filter": "done",
        "detect": "done",
        "parse": "done",
        "chunk": "done",
        "store": "done",
    }
    filter_logs = next(s for s in job.steps if s["key"] == "filter")["logs"]
    assert any("over 500 KB" in log["message"] for log in filter_logs)

    events = [e for c, e in bus.published if c == channel(str(job.pk))]
    assert events[0] == {"type": "job", "status": "running"}
    assert events[-1]["type"] == "job" and events[-1]["status"] == "done"

    files = {f["path"] for f in index_store.list_files(repo.pk)}
    assert "app/main.py" in files and "node_modules/left-pad/index.js" not in files
    services = index_store.get_file(repo.pk, "app/services.py")
    assert services is not None
    assert {s["name"] for s in services["symbols"]} >= {"UserService", "get_user"}


def test_dashboard_list_detail_and_job(_setup: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]

    listing = client.get("/api/repos")
    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()["results"]] == [repo_id]
    assert listing.json()["results"][0]["latest_job"]["status"] == "done"

    detail = client.get(f"/api/repos/{repo_id}")
    assert detail.json()["commit_sha"] == SHA

    job = client.get(f"/api/repos/{repo_id}/job")
    assert job.json()["status"] == "done"
    assert len(job.json()["steps"]) == 7


def test_same_commit_is_served_from_cache(_setup: Any) -> None:
    first, _ = client_for("ada")
    second, bob = client_for("bob")
    repo_id = analyze(first).json()["repository"]["id"]

    response = analyze(second, "acme/py_app")

    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["created"] is False
    assert response.json()["repository"]["id"] == repo_id
    assert IngestionJob.objects.count() == 1
    assert UserRepository.objects.filter(user=bob).count() == 1


def test_new_commit_creates_new_snapshot(_setup: Any) -> None:
    host, _ = _setup
    client, _ = client_for("ada")
    first = analyze(client).json()["repository"]["id"]
    host.sha = "b" * 40
    second = analyze(client).json()["repository"]["id"]
    assert first != second
    assert Repository.objects.count() == 2


def test_other_users_cannot_see_a_repo(_setup: Any) -> None:
    owner, _ = client_for("ada")
    stranger, _ = client_for("eve")
    repo_id = analyze(owner).json()["repository"]["id"]

    for path in ["", "/job", "/tree", "/files?path=app/main.py"]:
        response = stranger.get(f"/api/repos/{repo_id}{path}")
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("url", "status", "code"),
    [
        ("https://gitlab.com/a/b", 400, "invalid_url"),
        ("not a url", 400, "invalid_url"),
        ("https://github.com/acme/missing", 404, "not_found"),
    ],
)
def test_create_errors(_setup: Any, url: str, status: int, code: str) -> None:
    client, _ = client_for("ada")
    response = analyze(client, url)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_repo_too_large_is_rejected_before_cloning(_setup: Any) -> None:
    host, _ = _setup
    host.size_kb = 900 * 1024
    client, _ = client_for("ada")
    response = analyze(client)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "limit_exceeded"
    assert Repository.objects.count() == 0


def test_pipeline_failure_is_recorded(_setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def too_big(*_args: Any, **_kwargs: Any) -> Path:
        raise LimitExceededError("The repository is 300 MB, above RepoGuide's 200 MB limit.")

    monkeypatch.setattr(pipeline, "clone_repository", too_big)
    client, _ = client_for("ada")
    body = analyze(client).json()

    repo = Repository.objects.get(pk=body["repository"]["id"])
    job = IngestionJob.objects.get(pk=body["job"]["id"])
    assert repo.status == "failed"
    assert "300 MB" in repo.error
    assert job.status == "failed"
    clone_step = next(s for s in job.steps if s["key"] == "clone")
    assert clone_step["status"] == "failed"
    assert later_steps_pending(job)

    # Retrying a failed snapshot re-runs ingestion on the same record.
    monkeypatch.undo()
    _setup_clone(monkeypatch)
    retry = analyze(client)
    assert retry.status_code == 201
    repo.refresh_from_db()
    assert repo.status == "ready"


def later_steps_pending(job: IngestionJob) -> bool:
    return all(s["status"] == "pending" for s in job.steps if s["key"] in {"parse", "store"})


def _setup_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / "py_app", destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)


def test_tree_and_file_content_with_ranges(_setup: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]

    tree = client.get(f"/api/repos/{repo_id}/tree").json()
    paths = [f["path"] for f in tree["files"]]
    assert paths == sorted(paths) and "app/routes.py" in paths

    full = client.get(f"/api/repos/{repo_id}/files", {"path": "app/main.py"}).json()
    expected = (FIXTURES / "py_app/app/main.py").read_text(encoding="utf-8")
    assert full["content"] == expected
    assert full["start_line"] == 1 and full["end_line"] == full["lines"]
    assert full["github_url"] == f"https://github.com/Acme/py_app/blob/{SHA}/app/main.py"

    part = client.get(f"/api/repos/{repo_id}/files", {"path": "app/main.py", "start": 8, "end": 11})
    assert part.json()["content"] == "\n".join(expected.splitlines()[7:11])
    assert part.json()["github_url"].endswith("#L8-L11")

    clamped = client.get(
        f"/api/repos/{repo_id}/files", {"path": "app/main.py", "start": 3, "end": 999}
    )
    assert clamped.json()["end_line"] == full["lines"]

    beyond = client.get(f"/api/repos/{repo_id}/files", {"path": "app/main.py", "start": 999})
    assert beyond.status_code == 400
    missing = client.get(f"/api/repos/{repo_id}/files", {"path": "nope.py"})
    assert missing.status_code == 404


def test_delete_unlinks_from_dashboard(_setup: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    assert client.delete(f"/api/repos/{repo_id}").status_code == 204
    assert client.get(f"/api/repos/{repo_id}").status_code == 404
    assert Repository.objects.filter(pk=ObjectId(repo_id)).exists()  # shared cache kept


def test_invalid_repo_id_is_404(_setup: Any) -> None:
    client, _ = client_for("ada")
    assert client.get("/api/repos/not-an-object-id").status_code == 404


# --- SSE -----------------------------------------------------------------------------------


def test_stream_requires_auth(_setup: Any) -> None:
    owner, _ = client_for("ada")
    repo_id = analyze(owner).json()["repository"]["id"]
    response = APIClient().get(f"/api/repos/{repo_id}/job/stream")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_stream_of_finished_job_sends_snapshot_and_end(_setup: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    response = client.get(f"/api/repos/{repo_id}/job/stream")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"

    async def collect() -> bytes:
        return b"".join([chunk async for chunk in response.streaming_content])  # type: ignore[attr-defined]

    body = asyncio.run(collect()).decode()
    assert body.startswith("event: snapshot\n")
    assert '"status": "done"' in body
    assert body.rstrip().endswith('data: {"status": "done"}')


def test_stream_forwards_live_events(_setup: Any) -> None:
    _host, bus = _setup
    user = User.objects.create(username="ada", github_id=1)
    repo = Repository.objects.create(
        url="https://github.com/a/b", url_key="github.com/a/b", owner="a", name="b",
        default_branch="main", commit_sha=SHA,
    )  # fmt: skip
    job = IngestionJob.objects.create(repository=repo, user=user, status="running")
    job_id = str(job.pk)

    async def scenario() -> list[str]:
        received: list[str] = []
        stream = job_events(job_id, tick=5)
        received.append(await anext(stream))  # snapshot
        bus.publish(channel(job_id), {"type": "step", "key": "clone", "status": "running"})
        received.append(await anext(stream))
        bus.publish(channel(job_id), {"type": "job", "status": "done"})
        received.append(await anext(stream))
        received.append(await anext(stream))
        await stream.aclose()
        return received

    events = asyncio.run(scenario())
    assert [e.split("\n", 1)[0] for e in events] == [
        "event: snapshot",
        "event: step",
        "event: job",
        "event: end",
    ]
