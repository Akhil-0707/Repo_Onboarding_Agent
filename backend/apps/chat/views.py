from __future__ import annotations

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from django.db.models import QuerySet
from rest_framework import generics
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.chat.models import Message, Thread
from apps.chat.serializers import MessageSerializer, ThreadDetailSerializer, ThreadSerializer
from apps.common.errors import NotFoundError
from apps.repos.quota import ensure_chat_question_left
from apps.repos.services import get_user_repository


def get_user_thread(user: User, repo_id: str, thread_id: str) -> Thread:
    """The thread if it belongs to ``user`` and to a repository on their dashboard; else 404."""
    repository = get_user_repository(user, repo_id)
    try:
        oid = ObjectId(thread_id)
    except (InvalidId, TypeError) as exc:
        raise NotFoundError("Thread not found.") from exc
    thread = (
        Thread.objects.select_related("repository")
        .filter(pk=oid, user=user, repository=repository)
        .first()
    )
    if thread is None:
        raise NotFoundError("Thread not found.")
    return thread


class ThreadListCreateView(generics.ListCreateAPIView):
    serializer_class = ThreadSerializer

    def get_queryset(self) -> QuerySet[Thread]:
        repository = get_user_repository(self.request.user, self.kwargs["repo_id"])
        return Thread.objects.filter(user=self.request.user, repository=repository).order_by(
            "-updated_at"
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        repository = get_user_repository(self.request.user, self.kwargs["repo_id"])
        # A conversation exists to ask a question: none left this hour -> don't create one.
        ensure_chat_question_left(self.request.user)
        serializer.save(user=self.request.user, repository=repository)


class ThreadDetailView(generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        return ThreadDetailSerializer if self.request.method == "GET" else ThreadSerializer

    def get_object(self) -> Thread:
        return get_user_thread(self.request.user, self.kwargs["repo_id"], self.kwargs["thread_id"])


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer

    def get_queryset(self) -> QuerySet[Message]:
        thread = get_user_thread(
            self.request.user, self.kwargs["repo_id"], self.kwargs["thread_id"]
        )
        return thread.messages.order_by("created_at")
