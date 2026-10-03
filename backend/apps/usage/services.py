"""Token usage per repository and per user.

Analyses are a shared cache: a snapshot's analysis usage is attributed to the users who started
work on it ("analyses you started"); opening a snapshot someone else analysed costs nothing.
Chat usage is always personal.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.conf import settings

from apps.accounts.models import User
from apps.analysis.models import Analysis
from apps.chat.models import Message, MessageRole, Thread
from apps.llm.cost import sum_usage
from apps.repos.models import IngestionJob, Repository, UserRepository
from apps.repos.quota import CHAT_QUESTION, NEW_ANALYSIS, quota_status


def _chat_by_repo(user: User, repository: Repository | None = None) -> dict[Any, dict[str, Any]]:
    threads = Thread.objects.filter(user=user)
    if repository is not None:
        threads = threads.filter(repository=repository)
    repo_of = dict(threads.values_list("pk", "repository_id"))
    usages: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    questions: dict[Any, int] = defaultdict(int)
    rows = Message.objects.filter(thread_id__in=list(repo_of)).values_list(
        "thread_id", "role", "usage"
    )
    for thread_id, role, usage in rows:
        repo_id = repo_of[thread_id]
        if role == MessageRole.USER:
            questions[repo_id] += 1
        else:
            usages[repo_id].append(usage)
    return {
        repo_id: {**sum_usage(usages[repo_id]), "questions": questions[repo_id]}
        for repo_id in set(repo_of.values())
    }


def _analysis_usage(repository_ids: list[Any]) -> dict[Any, dict[str, Any]]:
    return {
        repo_id: sum_usage([usage])
        for repo_id, usage in Analysis.objects.filter(repository_id__in=repository_ids).values_list(
            "repository_id", "usage"
        )
    }


def pricing() -> dict[str, Any]:
    return {
        "input_per_1k": settings.LLM_COST_PER_1K_INPUT,
        "output_per_1k": settings.LLM_COST_PER_1K_OUTPUT,
        "self_hosted": not (settings.LLM_COST_PER_1K_INPUT or settings.LLM_COST_PER_1K_OUTPUT),
    }


def repository_usage(user: User, repository: Repository) -> dict[str, Any]:
    chat = _chat_by_repo(user, repository).get(repository.pk) or {**sum_usage([]), "questions": 0}
    analysis = _analysis_usage([repository.pk]).get(repository.pk) or sum_usage([])
    return {"analysis": analysis, "chat": chat, "pricing": pricing()}


def user_usage(user: User) -> dict[str, Any]:
    chat = _chat_by_repo(user)
    started = set(IngestionJob.objects.filter(user=user).values_list("repository_id", flat=True))
    dashboard = list(
        UserRepository.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("repository_id", flat=True)
    )
    repo_ids = list(dict.fromkeys([*dashboard, *started, *chat]))
    repos = Repository.objects.in_bulk(repo_ids)
    analysis = _analysis_usage([r for r in repo_ids if r in started])

    rows = []
    for repo_id in repo_ids:
        repository = repos.get(repo_id)
        if repository is None:
            continue
        rows.append(
            {
                "id": str(repo_id),
                "full_name": repository.full_name,
                "commit_sha": repository.commit_sha,
                "on_dashboard": repo_id in dashboard,
                "started_by_you": repo_id in started,
                "analysis": analysis.get(repo_id),
                "chat": chat.get(repo_id),
            }
        )
    analysis_total = sum_usage(analysis.values())
    chat_total = sum_usage(chat.values())
    return {
        "totals": {
            "analysis": analysis_total,
            "chat": {**chat_total, "questions": sum(c["questions"] for c in chat.values())},
            "all": sum_usage([analysis_total, chat_total]),
        },
        "repositories": rows,
        "rate_limit": {
            "new_analyses": quota_status(user, NEW_ANALYSIS),
            "chat_questions": quota_status(user, CHAT_QUESTION),
        },
        "pricing": pricing(),
    }
