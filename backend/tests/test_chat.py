"""Q&A chat: threads API and the streaming answer endpoint (needs MongoDB)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.chat import stream
from apps.chat.agent import answer_question
from apps.chat.models import Message, Thread
from apps.common.events import InMemoryEventBus, set_event_bus
from apps.ingestion import index_store, pipeline
from apps.ingestion.progress import initial_steps
from apps.ingestion.tasks import start_pipeline
from apps.llm.client import set_llm_client
from apps.llm.errors import ModelOfflineError
from apps.repos.models import IngestionJob, Repository, UserRepository
from tests.conftest_fixtures import FIXTURES
from tests.fakes.llm import FakeAnalysisLLM, ScriptedLLM, call, reply

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
    monkeypatch.setattr(stream, "check_llm_health", lambda: SimpleNamespace(online=True))
    yield
    set_event_bus(None)


@pytest.fixture
def repo() -> Repository:
    """An ingested + analysed fixture repository on ada's dashboard."""
    set_llm_client(FakeAnalysisLLM())
    user = User.objects.create(username="ada", github_id=1)
    repository = Repository.objects.create(
        url="https://github.com/acme/py_app", url_key="github.com/acme/py_app#" + "c" * 40,
        owner="acme", name="py_app", default_branch="main", commit_sha="c" * 40,
    )  # fmt: skip
    UserRepository.objects.create(user=user, repository=repository)
    job = IngestionJob.objects.create(repository=repository, user=user, steps=initial_steps())
    start_pipeline(str(job.pk))
    repository.refresh_from_db()
    assert repository.status == "ready"
    return repository


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user).access}")
    return client


def owner_client(repo: Repository) -> APIClient:
    return client_for(UserRepository.objects.get(repository=repo).user)


def new_thread(client: APIClient, repo: Repository) -> str:
    response = client.post(f"/api/repos/{repo.pk}/threads", {}, format="json")
    assert response.status_code == 201
    return response.json()["id"]


def ask(client: APIClient, repo: Repository, thread_id: str, content: str) -> Any:
    return client.post(
        f"/api/repos/{repo.pk}/threads/{thread_id}/messages/stream",
        json.dumps({"content": content}),
        content_type="application/json",
    )


def events_of(response: Any) -> list[tuple[str, dict[str, Any]]]:
    async def collect() -> bytes:
        return b"".join([chunk async for chunk in response.streaming_content])

    events = []
    for block in asyncio.run(collect()).decode().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


ANSWER = (
    "Users are stored in memory by UserService [app/services.py:10-20], and the route in "
    "[app/routes.py:4-12] calls it. Caching lives in [app/cache.py:1-9]."
)


# --- threads API -----------------------------------------------------------------------------


def test_thread_crud_and_ownership(repo: Repository) -> None:
    client = owner_client(repo)
    first, second = new_thread(client, repo), new_thread(client, repo)

    listing = client.get(f"/api/repos/{repo.pk}/threads").json()
    assert {t["id"] for t in listing["results"]} == {first, second}

    patched = client.patch(
        f"/api/repos/{repo.pk}/threads/{first}", {"title": "Storage"}, format="json"
    )
    assert patched.status_code == 200 and patched.json()["title"] == "Storage"
    detail = client.get(f"/api/repos/{repo.pk}/threads/{first}").json()
    assert detail["title"] == "Storage" and detail["messages"] == []

    stranger = client_for(User.objects.create(username="eve", github_id=2))
    assert stranger.get(f"/api/repos/{repo.pk}/threads/{first}").status_code == 404
    assert stranger.get(f"/api/repos/{repo.pk}/threads").status_code == 404
    assert client.get(f"/api/repos/{repo.pk}/threads/not-an-id").status_code == 404
    assert ask(stranger, repo, first, "hi").status_code == 404

    assert client.delete(f"/api/repos/{repo.pk}/threads/{first}").status_code == 204
    assert not Thread.objects.filter(pk=first).exists()
    assert client.get(f"/api/repos/{repo.pk}/threads").json()["count"] == 1


# --- streaming answers -----------------------------------------------------------------------


def test_answer_streams_tool_steps_tokens_and_validated_citations(repo: Repository) -> None:
    llm = ScriptedLLM(
        reply(tool_calls=[call("read_file", {"path": "app/services.py"})]), reply(ANSWER)
    )
    set_llm_client(llm)
    client = owner_client(repo)
    thread_id = new_thread(client, repo)

    response = ask(client, repo, thread_id, "  Where are users stored?  ")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    events = events_of(response)
    kinds = [kind for kind, _ in events]

    assert kinds[0] == "start" and kinds[-1] == "done"
    assert events[0][1]["message"]["content"] == "Where are users stored?"
    assert kinds.index("tool_start") < kinds.index("tool_end") < kinds.index("token")
    tool_end = dict(events)["tool_end"]
    assert tool_end["name"] == "read_file" and tool_end["ok"] and tool_end["id"] == 1
    assert dict(events)["tool_start"]["summary"] == "Reading 'app/services.py'"
    streamed = "".join(data["text"] for kind, data in events if kind == "token")
    assert "UserService" in streamed  # live preview of the answer

    citations = [data for kind, data in events if kind == "citation"]
    assert citations == [
        {"path": "app/services.py", "start_line": 10, "end_line": 20},
        {"path": "app/routes.py", "start_line": 4, "end_line": 12},
    ]
    final = events[-1][1]["message"]
    assert "app/cache.py" not in final["content"]  # invented file removed
    assert final["content"].endswith("calls it. Caching lives in.")
    assert final["citations"] == citations
    assert final["tool_steps"][0]["summary"] == "Reading 'app/services.py'"

    thread = Thread.objects.get(pk=thread_id)
    assert thread.title == "Where are users stored?"
    stored = list(thread.messages.order_by("created_at").values_list("role", "status"))
    assert stored == [("user", "complete"), ("assistant", "complete")]
    system = llm.requests[0]["messages"][0]["content"]
    assert "acme/py_app" in system and "untrusted DATA" in system
    assert "small web service" in system  # generated overview summary is context
    logs = index_store.collection("agent_logs").find({"repo_id": repo.pk, "scope": "chat"})
    assert {log["kind"] for log in logs} == {"llm", "tool"}


def test_history_keeps_recent_turns_and_summarises_older_ones(
    repo: Repository, settings: Any
) -> None:
    settings.CHAT_HISTORY_TURNS = 1
    llm = ScriptedLLM(reply("First answer."), reply("Second answer."), reply("Third answer."))
    set_llm_client(llm)
    client = owner_client(repo)
    thread_id = new_thread(client, repo)
    for question in ("Question one?", "Question two?", "Question three?"):
        assert events_of(ask(client, repo, thread_id, question))[-1][0] == "done"

    messages = llm.requests[2]["messages"]
    assert "Earlier in this conversation (summary):\n- Q: Question one?\n- A: First answer." in (
        messages[0]["content"]
    )
    assert messages[1:] == [
        {"role": "user", "content": "Question two?"},
        {"role": "assistant", "content": "Second answer."},
        {"role": "user", "content": "Question three?"},
    ]
    assert Thread.objects.get(pk=thread_id).title == "Question one?"


def test_model_dying_mid_answer_sends_an_error_event(repo: Repository) -> None:
    set_llm_client(ScriptedLLM(ModelOfflineError("tunnel closed")))
    client = owner_client(repo)
    thread_id = new_thread(client, repo)

    events = events_of(ask(client, repo, thread_id, "Where are users stored?"))
    assert [kind for kind, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "model_offline"
    failed = Message.objects.get(pk=events[1][1]["message_id"])
    assert failed.status == "error" and failed.role == "assistant"

    # Failed answers are not replayed to the model as history.
    llm = ScriptedLLM(reply("Now it works."))
    set_llm_client(llm)
    assert events_of(ask(client, repo, thread_id, "Again?"))[-1][0] == "done"
    roles = [m["role"] for m in llm.requests[0]["messages"]]
    assert roles == ["system", "user", "user"]


def test_offline_model_and_bad_requests_fail_before_streaming(
    repo: Repository, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    client = owner_client(repo)
    thread_id = new_thread(client, repo)
    url = f"/api/repos/{repo.pk}/threads/{thread_id}/messages/stream"

    monkeypatch.setattr(stream, "check_llm_health", lambda: SimpleNamespace(online=False))
    offline = ask(client, repo, thread_id, "Hello?")
    assert offline.status_code == 503
    assert offline.json()["error"]["code"] == "model_offline"
    assert not Message.objects.filter(thread_id=thread_id).exists()

    monkeypatch.setattr(stream, "check_llm_health", lambda: SimpleNamespace(online=True))
    assert ask(client, repo, thread_id, "   ").status_code == 400
    settings.CHAT_MAX_QUESTION_CHARS = 10
    too_long = ask(client, repo, thread_id, "x" * 11)
    assert too_long.status_code == 400
    assert "limited to 10" in json.dumps(too_long.json()["error"]["details"])
    bad_json = client.post(url, "{nope", content_type="application/json")
    assert bad_json.status_code == 400 and bad_json.json()["error"]["code"] == "parse_error"
    assert client.get(url).status_code == 405
    assert APIClient().post(url, {"content": "hi"}, format="json").status_code == 401

    Repository.objects.filter(pk=repo.pk).update(status="processing")
    not_ready = ask(client, repo, thread_id, "Hello?")
    assert not_ready.status_code == 409 and not_ready.json()["error"]["code"] == "repo_not_ready"


def test_cancelled_answer_stops_quietly(repo: Repository) -> None:
    set_llm_client(ScriptedLLM(reply("Never shown.")))
    user = UserRepository.objects.get(repository=repo).user
    thread = Thread.objects.create(user=user, repository=repo)
    question = Message.objects.create(thread=thread, role="user", content="Hi?")
    emitted: list[str] = []

    message = answer_question(
        str(thread.pk), str(question.pk), lambda kind, data: emitted.append(kind), lambda: True
    )
    assert message.status == "error" and "interrupted" in message.error
    assert emitted == []  # nobody is listening any more
