"""Rate limits, re-analysis, private-repo access, usage reporting, the stale-job sweeper and
API error envelopes (needs MongoDB)."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.analysis.models import Analysis
from apps.chat.models import Message, Thread
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.github import set_code_host
from apps.ingestion.progress import initial_steps
from apps.ingestion.sweeper import sweep_stale_jobs
from apps.repos.models import IngestionJob, Repository, UserRepository
from tests.conftest_fixtures import FIXTURES
from tests.fakes.github import FakeCodeHost

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> Any:
    index_store.ensure_indexes()
    for name in (index_store.FILES, index_store.CHUNKS, index_store.EDGES):
        index_store.collection(name).delete_many({})
    fake = FakeCodeHost()
    set_code_host(fake)
    set_event_bus(InMemoryEventBus())

    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / url.rsplit("/", 1)[-1], destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)
    yield fake
    set_code_host(None)
    set_event_bus(None)


def client_for(username: str) -> tuple[APIClient, User]:
    user = User.objects.create(username=username, github_id=abs(hash(username)) % 10**9)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user).access}")
    return client, user


def analyze(client: APIClient, name: str = "py_app") -> Any:
    return client.post("/api/repos", {"url": f"https://github.com/acme/{name}"}, format="json")


@pytest.fixture
def limit_two(settings: Any) -> None:
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"new_analysis": "2/hour"},
    }


# --- rate limit ------------------------------------------------------------------------------


def test_new_analyses_are_limited_but_cache_hits_are_free(host: Any, limit_two: None) -> None:
    ada, _ = client_for("ada")
    bob, _ = client_for("bob")
    assert analyze(bob, "js_app").status_code == 201  # bob's work, cached for everyone

    assert analyze(ada, "py_app").status_code == 201
    assert analyze(ada, "go_app").status_code == 201
    limited = analyze(ada, "java_app")
    assert limited.status_code == 429
    error = limited.json()["error"]
    assert error["code"] == "rate_limited"
    assert "2 new analyses per hour" in error["message"]
    assert 0 < error["details"]["retry_after_seconds"] <= 3600
    assert not Repository.objects.filter(name="java_app").exists()  # nothing half-created

    cached = analyze(ada, "js_app")  # already analysed by bob: free
    assert cached.status_code == 200 and cached.json()["cached"] is True
    again = analyze(ada, "py_app")  # her own snapshot: free too
    assert again.status_code == 200

    quota = ada.get("/api/usage").json()["rate_limit"]["new_analyses"]
    assert quota["limit"] == 2 and quota["used"] == 2 and quota["remaining"] == 0
    assert 0 < quota["reset_in_seconds"] <= 3600
    assert bob.get("/api/usage").json()["rate_limit"]["new_analyses"]["remaining"] == 1


# --- re-analysis -----------------------------------------------------------------------------


def test_reanalyze_same_commit_is_a_no_op_when_complete(host: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    jobs = IngestionJob.objects.count()

    response = client.post(f"/api/repos/{repo_id}/reanalyze")
    assert response.status_code == 200
    assert response.json()["cached"] is True and response.json()["created"] is False
    assert IngestionJob.objects.count() == jobs


def test_reanalyze_retries_only_unfinished_sections(host: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    analysis = Analysis.objects.get(repository_id=repo_id)
    sections = dict(analysis.sections)
    glossary_before = sections["glossary"]
    sections["tour"] = {"status": "failed", "error": "model gave up"}
    overview_updated = sections["overview"]["updated_at"]
    Analysis.objects.filter(pk=analysis.pk).update(sections=sections, status="partial")

    response = client.post(f"/api/repos/{repo_id}/reanalyze")
    assert response.status_code == 201
    job = IngestionJob.objects.get(pk=response.json()["job"]["id"])
    assert job.status == "done"
    assert {s["key"]: s["status"] for s in job.steps}["clone"] == "done"  # no re-ingestion

    analysis.refresh_from_db()
    assert analysis.status == "done"
    assert analysis.sections["tour"]["status"] == "done"
    assert analysis.sections["overview"]["updated_at"] == overview_updated  # not redone
    assert analysis.sections["glossary"] == glossary_before


def test_reanalyze_new_commit_replaces_the_snapshot_on_the_dashboard(host: Any) -> None:
    client, _ = client_for("ada")
    other, _ = client_for("bob")
    old_id = analyze(client).json()["repository"]["id"]
    assert analyze(other).status_code == 200  # bob shares the old snapshot

    host.sha = "b" * 40
    response = client.post(f"/api/repos/{old_id}/reanalyze")
    assert response.status_code == 201
    new_id = response.json()["repository"]["id"]
    assert new_id != old_id
    assert Repository.objects.get(pk=new_id).commit_sha == "b" * 40
    dashboard = [r["id"] for r in client.get("/api/repos").json()["results"]]
    assert dashboard == [new_id]
    assert other.get(f"/api/repos/{old_id}").status_code == 200  # bob keeps his snapshot


def test_reanalyze_conflicts_and_limits(host: Any, limit_two: None) -> None:
    client, user = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    running = IngestionJob.objects.create(
        repository_id=repo_id, user=user, status="running", steps=initial_steps()
    )
    busy = client.post(f"/api/repos/{repo_id}/reanalyze")
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "analysis_in_progress"
    running.delete()

    analyze(client, "go_app")  # second new analysis: quota used up
    host.sha = "c" * 40
    limited = client.post(f"/api/repos/{repo_id}/reanalyze")
    assert limited.status_code == 429
    assert not Repository.objects.filter(commit_sha="c" * 40).exists()


# --- private repositories --------------------------------------------------------------------


def test_private_access_is_rechecked_and_revoked(host: Any, settings: Any) -> None:
    host.private = True
    client, user = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    link = UserRepository.objects.get(user=user, repository_id=repo_id)
    assert link.access_checked_at is not None  # verified by the analysis request itself

    calls = host.calls
    assert client.get(f"/api/repos/{repo_id}").status_code == 200
    assert host.calls == calls  # recently verified: no GitHub round trip

    stale = timezone.now() - timedelta(hours=settings.PRIVATE_ACCESS_RECHECK_HOURS + 1)
    UserRepository.objects.filter(pk=link.pk).update(access_checked_at=stale)
    host.down = True  # GitHub outage: a recent confirmation is still good enough
    assert client.get(f"/api/repos/{repo_id}").status_code == 200

    UserRepository.objects.filter(pk=link.pk).update(access_checked_at=None)
    outage = client.get(f"/api/repos/{repo_id}")
    assert outage.status_code == 502 and outage.json()["error"]["code"] == "github_error"

    host.down = False
    host.denied.add(None)  # ada has no GitHub token; the repo is no longer visible to her
    assert client.get(f"/api/repos/{repo_id}/analysis").status_code == 404
    assert not UserRepository.objects.filter(pk=link.pk).exists()


def test_public_repos_never_call_github_for_reads(host: Any) -> None:
    client, _ = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    calls = host.calls
    client.get(f"/api/repos/{repo_id}")
    client.get(f"/api/repos/{repo_id}/tree")
    assert host.calls == calls


# --- usage -----------------------------------------------------------------------------------


def test_usage_attributes_analyses_to_who_started_them(host: Any) -> None:
    ada, _ = client_for("ada")
    bob, bob_user = client_for("bob")
    repo_id = analyze(ada).json()["repository"]["id"]
    analyze(bob)  # cache hit
    analysis = Analysis.objects.get(repository_id=repo_id)
    thread = Thread.objects.create(user=bob_user, repository_id=repo_id)
    Message.objects.create(thread=thread, role="user", content="Q?")
    Message.objects.create(
        thread=thread, role="assistant", content="A.",
        usage={"calls": 2, "prompt_tokens": 300, "completion_tokens": 40, "latency_ms": 900},
    )  # fmt: skip

    mine = ada.get("/api/usage").json()
    assert mine["totals"]["analysis"]["prompt_tokens"] == analysis.usage["prompt_tokens"] > 0
    assert mine["totals"]["chat"]["questions"] == 0
    row = mine["repositories"][0]
    assert row["id"] == repo_id and row["started_by_you"] and row["on_dashboard"]
    assert mine["pricing"]["self_hosted"] is True and mine["totals"]["all"]["est_cost"] == 0

    his = bob.get("/api/usage").json()
    assert his["totals"]["analysis"]["total_tokens"] == 0  # cache hits are free
    assert his["totals"]["chat"]["questions"] == 1
    assert his["totals"]["chat"]["total_tokens"] == 340
    assert his["repositories"][0]["started_by_you"] is False
    assert his["repositories"][0]["analysis"] is None

    repo_usage = bob.get(f"/api/repos/{repo_id}/usage").json()
    assert repo_usage["analysis"]["calls"] == analysis.usage["calls"]
    assert repo_usage["chat"]["calls"] == 2 and repo_usage["chat"]["questions"] == 1
    assert ada.get(f"/api/repos/{repo_id}/usage").json()["chat"]["calls"] == 0


def test_estimated_cost_uses_configured_prices(host: Any, settings: Any) -> None:
    settings.LLM_COST_PER_1K_INPUT = 0.5
    settings.LLM_COST_PER_1K_OUTPUT = 2.0
    client, user = client_for("ada")
    repo_id = analyze(client).json()["repository"]["id"]
    thread = Thread.objects.create(user=user, repository_id=repo_id)
    Message.objects.create(
        thread=thread, role="assistant",
        usage={"calls": 1, "prompt_tokens": 2000, "completion_tokens": 500, "latency_ms": 1},
    )  # fmt: skip
    body = client.get(f"/api/repos/{repo_id}/usage").json()
    assert body["chat"]["est_cost"] == 2.0  # 2k x 0.5 + 0.5k x 2.0
    assert body["pricing"]["self_hosted"] is False


# --- stale jobs ------------------------------------------------------------------------------


def make_job(user: User, repository: Repository, status: str, minutes_ago: int) -> IngestionJob:
    job = IngestionJob.objects.create(
        repository=repository, user=user, status=status, steps=initial_steps()
    )
    then = timezone.now() - timedelta(minutes=minutes_ago)
    IngestionJob.objects.filter(pk=job.pk).update(heartbeat_at=then, created_at=then)
    return job


def test_sweeper_fails_silent_jobs_only(host: Any) -> None:
    client, user = client_for("ada")
    ready = Repository.objects.get(pk=analyze(client).json()["repository"]["id"])
    broken = Repository.objects.create(
        url="https://github.com/acme/x", url_key="github.com/acme/x", owner="acme", name="x",
        default_branch="main", commit_sha="d" * 40, status="ingesting",
    )  # fmt: skip

    dead_ingest = make_job(user, broken, "running", minutes_ago=45)
    alive = make_job(user, broken, "running", minutes_ago=5)
    young_queue = make_job(user, broken, "queued", minutes_ago=120)
    waiting = make_job(user, broken, "waiting_for_model", minutes_ago=600)
    sections = dict(Analysis.objects.get(repository=ready).sections)
    sections["tour"] = {"status": "running"}
    Analysis.objects.filter(repository=ready).update(sections=sections, status="running")
    dead_analysis = make_job(user, ready, "running", minutes_ago=45)

    assert sweep_stale_jobs() == 2
    assert sweep_stale_jobs() == 0  # idempotent

    dead_ingest.refresh_from_db()
    broken.refresh_from_db()
    assert dead_ingest.status == "failed" and "stopped responding" in dead_ingest.error
    assert broken.status == "failed"
    for job in (alive, young_queue, waiting):
        before = job.status
        job.refresh_from_db()
        assert job.status == before

    dead_analysis.refresh_from_db()
    ready.refresh_from_db()
    analysis = Analysis.objects.get(repository=ready)
    assert dead_analysis.status == "done"
    assert {s["key"]: s["status"] for s in dead_analysis.steps}["analyze"] == "failed"
    assert ready.status == "ready"  # the code stays browsable
    assert analysis.status == "partial"
    assert analysis.sections["tour"]["status"] == "failed"
    assert analysis.sections["overview"]["status"] == "done"


# --- error envelope --------------------------------------------------------------------------


def test_unknown_api_urls_use_the_error_envelope(host: Any) -> None:
    client, _ = client_for("ada")
    response = client.get("/api/definitely/not/here")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No such API endpoint.", "details": None}
    }
