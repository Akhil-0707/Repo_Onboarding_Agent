"""Analysis agent end to end on an ingested fixture repository (needs MongoDB)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.analysis import runner, tasks
from apps.analysis.models import Analysis
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.progress import initial_steps
from apps.ingestion.tasks import start_pipeline
from apps.llm.client import OpenAICompatibleLLMClient, set_llm_client
from apps.llm.health import check_llm_health
from apps.repos.models import IngestionJob, Repository, UserRepository
from tests.conftest_fixtures import FIXTURES
from tests.fakes.llm import FakeAnalysisLLM, section_answer
from tests.fakes.openai_server import FakeOpenAIServer, completion

pytestmark = [pytest.mark.mongo, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Any:
    index_store.ensure_indexes()
    for name in (index_store.FILES, index_store.CHUNKS, index_store.EDGES, "agent_logs"):
        index_store.collection(name).delete_many({})
    set_event_bus(InMemoryEventBus())

    def fake_clone(url: str, sha: str, destination: Path, **kwargs: Any) -> Path:
        shutil.copytree(FIXTURES / "py_app", destination)
        return destination

    monkeypatch.setattr(pipeline, "clone_repository", fake_clone)
    yield
    set_event_bus(None)


def start(user: User | None = None, sha: str = "f" * 40) -> tuple[Repository, IngestionJob]:
    user = user or User.objects.create(username=f"u{sha[:4]}", github_id=int(sha[:6], 16))
    repo = Repository.objects.create(
        url="https://github.com/acme/py_app", url_key=f"github.com/acme/py_app#{sha}",
        owner="acme", name="py_app", default_branch="main", commit_sha=sha,
    )  # fmt: skip
    UserRepository.objects.create(user=user, repository=repo)
    job = IngestionJob.objects.create(repository=repo, user=user, steps=initial_steps())
    start_pipeline(str(job.pk))
    repo.refresh_from_db()
    job.refresh_from_db()
    return repo, job


def test_full_analysis_produces_validated_sections() -> None:
    llm = FakeAnalysisLLM()
    set_llm_client(llm)
    repo, job = start()

    assert repo.status == "ready"
    assert job.status == "done"
    analyze_step = next(s for s in job.steps if s["key"] == "analyze")
    assert analyze_step["status"] == "done"
    analysis = Analysis.objects.get(repository=repo)
    assert analysis.status == "done"
    assert analysis.model == "fake-llm"
    assert analysis.checkpoint is None
    assert set(analysis.sections) == {"overview", "architecture", "start_here", "tour", "glossary"}

    overview = analysis.sections["overview"]["data"]
    assert {s["path"] for s in overview["structure"]} == {"app/", "tests/"}  # imaginary/ dropped
    assert overview["entry_points"][0]["path"] == "app/main.py"
    assert len(overview["starter_questions"]) == 4
    assert analysis.sections["overview"]["references"]["dropped"] == 1

    start_here = analysis.sections["start_here"]["data"]["files"]
    paths = [f["path"] for f in start_here]
    assert "does/not/exist.py" not in paths and len(paths) == len(set(paths))

    arch = analysis.sections["architecture"]["data"]
    modules = {m["id"]: m for m in arch["modules"]}
    assert set(modules) == {"app", "core", "tests", "db"}  # phantom/ has no real files
    assert modules["app"]["kind"] == "entry"  # "Entry" coerced
    assert modules["core"]["paths"] == ["app/"]  # app/ghost.py dropped
    edges = {(e["source"], e["target"]): e for e in arch["edges"]}
    assert set(edges) == {("app", "core"), ("core", "db"), ("tests", "core")}
    assert edges["app", "core"]["imports"] == 2 and not edges["app", "core"]["derived"]
    assert edges["tests", "core"]["derived"]  # proven by the dependency graph
    assert arch["mermaid"].startswith("flowchart")
    assert 'm_app(["Application"])' in arch["mermaid"]
    assert "m_tests -.->" in arch["mermaid"]

    tour = analysis.sections["tour"]["data"]["steps"]
    assert [s["title"] for s in tour] == ["Start-up", "Routing", "Service"]  # ghost dropped
    assert [s["kind"] for s in tour] == ["entry_point", "flow_trace", "flow_trace"]
    assert (tour[2]["start_line"], tour[2]["end_line"]) == (10, 20)  # symbol beats line 99

    terms = {t["term"]: t for t in analysis.sections["glossary"]["data"]["terms"]}
    assert terms["UserService"]["path"] == "app/services.py"  # linked via symbol index
    assert terms["UserService"]["start_line"] == 10
    assert terms["Ghost"]["path"] is None  # hallucinated location removed

    assert analysis.usage["calls"] == llm.calls
    assert analysis.usage["prompt_tokens"] == 100 * llm.calls
    logs = list(index_store.collection("agent_logs").find({"repo_id": repo.pk}))
    assert {log["kind"] for log in logs} == {"llm", "tool"}
    assert any(log.get("tool") == "get_repo_metadata" for log in logs)
    assert all(log.get("prompt_tokens", 0) >= 0 for log in logs)


def test_analysis_api() -> None:
    set_llm_client(FakeAnalysisLLM())
    repo, _ = start()
    user = UserRepository.objects.get(repository=repo).user
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user).access}")

    body = client.get(f"/api/repos/{repo.pk}/analysis").json()
    assert body["status"] == "done"
    assert set(body["sections"]) == {"overview", "architecture", "start_here", "tour", "glossary"}
    assert body["sections"]["overview"]["data"]["summary"]
    assert body["usage"]["calls"] > 0

    section = client.get(f"/api/repos/{repo.pk}/analysis/glossary").json()
    assert section["status"] == "done" and section["data"]["terms"]
    assert client.get(f"/api/repos/{repo.pk}/analysis/bogus").status_code == 404

    detail = client.get(f"/api/repos/{repo.pk}").json()
    assert detail["analysis_status"] == "done"

    stranger = APIClient()
    other = User.objects.create(username="eve", github_id=4)
    stranger.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(other).access}")
    assert stranger.get(f"/api/repos/{repo.pk}/analysis").status_code == 404


def test_offline_model_waits_then_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeAnalysisLLM()
    set_llm_client(llm)
    monkeypatch.setattr(runner, "model_available", lambda: False)
    monkeypatch.setattr(tasks, "model_available", lambda: False)
    repo, job = start()

    assert repo.status == "ready"  # code is browsable while the analysis waits
    assert job.status == "waiting_for_model"
    assert next(s for s in job.steps if s["key"] == "analyze")["status"] == "waiting"
    analysis = Analysis.objects.get(repository=repo)
    assert analysis.status == "waiting_for_model" and analysis.waiting_since is not None
    assert llm.calls == 0
    assert tasks.resume_waiting_analyses() == 0  # still offline: nothing happens

    monkeypatch.setattr(runner, "model_available", lambda: True)
    monkeypatch.setattr(tasks, "model_available", lambda: True)
    assert tasks.resume_waiting_analyses() == 1
    job.refresh_from_db()
    analysis.refresh_from_db()
    assert job.status == "done" and analysis.status == "done"
    assert analysis.waiting_since is None


def test_model_dies_mid_analysis_and_resumes_from_checkpoint() -> None:
    # 3 calls: overview research (tool call + notes) + overview JSON. Then the model dies
    # inside the architecture research.
    dying = FakeAnalysisLLM(offline_after=4)
    set_llm_client(dying)
    repo, job = start()

    analysis = Analysis.objects.get(repository=repo)
    assert job.status == "waiting_for_model"
    assert analysis.section_status("overview") == "done"
    assert analysis.section_status("architecture") == "running"
    assert analysis.checkpoint["section"] == "architecture"
    assert analysis.checkpoint["phase"] == "research"
    assert analysis.checkpoint["messages"][-1]["role"] == "tool"

    healthy = FakeAnalysisLLM()
    set_llm_client(healthy)
    tasks.resume_waiting_analyses()
    analysis.refresh_from_db()
    job.refresh_from_db()
    assert job.status == "done" and analysis.status == "done"
    assert "overview" not in healthy.sections_answered  # finished sections are never redone
    assert healthy.sections_answered == ["architecture", "start_here", "tour", "glossary"]
    # Architecture research resumed from the checkpoint: no new metadata tool call needed.
    assert healthy.calls == 1 + 1 + 3 * 3  # notes + JSON, then 3 sections x (tool, notes, JSON)


def test_waiting_too_long_gives_up(monkeypatch: pytest.MonkeyPatch, settings: Any) -> None:
    from datetime import timedelta

    from django.utils import timezone

    monkeypatch.setattr(runner, "model_available", lambda: False)
    monkeypatch.setattr(tasks, "model_available", lambda: False)
    repo, job = start()
    Analysis.objects.filter(repository=repo).update(
        waiting_since=timezone.now() - timedelta(hours=settings.ANALYSIS_MAX_WAIT_HOURS + 1)
    )
    tasks.resume_waiting_analyses()
    job.refresh_from_db()
    assert job.status == "done"
    assert Analysis.objects.get(repository=repo).status == "failed"


# --- real HTTP client against the fake OpenAI-compatible server ------------------------------


def http_responder(server: FakeOpenAIServer, state: dict[str, Any]):
    """Speaks the OpenAI wire format; first tool call of the run is malformed on purpose."""

    def respond(body: dict[str, Any]) -> Any:
        state["chat_requests"] += 1
        if state["die_after"] and state["chat_requests"] >= state["die_after"]:
            server.offline = True
        messages = body["messages"]
        prompt = "\n".join(str(m.get("content") or "") for m in messages if m["role"] == "user")
        if body.get("tools"):
            if not any(m["role"] == "tool" for m in messages):
                if not state["sent_malformed"]:
                    state["sent_malformed"] = True
                    return completion(tool_calls=[{"name": "read_file", "arguments": '{"path": '}])
                return completion(tool_calls=[{"name": "get_repo_metadata", "arguments": "{}"}])
            last_tool = [m for m in messages if m["role"] == "tool"][-1]["content"]
            if "must be a JSON object" in last_tool:  # the repair message reached the model
                state["saw_repair_message"] = True
                return completion(
                    tool_calls=[{"name": "read_file", "arguments": '{"path": "app/main.py"}'}]
                )
            return completion("Notes: verified with tools.")
        section = re.search(r"^Section: (\w+)", prompt, flags=re.MULTILINE)
        if section:
            state["sections"].append(section.group(1))
            return completion(json.dumps(section_answer(section.group(1), prompt)))
        return completion("Notes.")

    return respond


def test_end_to_end_over_http_with_repair_outage_and_resume(
    fake_llm: FakeOpenAIServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "model_available", lambda: check_llm_health(force=True).online)
    monkeypatch.setattr(tasks, "model_available", lambda: check_llm_health(force=True).online)
    state = {"chat_requests": 0, "sent_malformed": False, "saw_repair_message": False,
             "sections": [], "die_after": 5}  # fmt: skip
    fake_llm.responder = http_responder(fake_llm, state)
    set_llm_client(OpenAICompatibleLLMClient(max_retries=1, backoff_base=0.01, backoff_max=0.02))

    repo, job = start()

    assert state["saw_repair_message"]
    assert job.status == "waiting_for_model"  # the tunnel went down mid-analysis
    analysis = Analysis.objects.get(repository=repo)
    assert analysis.section_status("overview") == "done"
    assert analysis.checkpoint is not None

    assert tasks.resume_waiting_analyses() == 0  # health check sees the outage
    fake_llm.offline = False
    state["die_after"] = 0
    assert tasks.resume_waiting_analyses() == 1

    job.refresh_from_db()
    analysis.refresh_from_db()
    assert job.status == "done" and analysis.status == "done"
    assert state["sections"].count("overview") == 1
    assert analysis.usage["prompt_tokens"] > 0
