from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.repos.models import Repository


class Thread(models.Model):
    """One Q&A conversation about one repository, owned by one user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_threads"
        indexes = [
            models.Index(fields=["user", "repository", "-updated_at"], name="thread_recent_idx")
        ]

    def __str__(self) -> str:
        return self.title or f"Thread {self.pk}"


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class MessageStatus(models.TextChoices):
    COMPLETE = "complete", "Complete"
    ERROR = "error", "Error"


class Message(models.Model):
    """``citations``: validated ``{path, start_line, end_line}`` references in ``content``.
    ``tool_steps``: what the agent did (tool, summary, ok, duration) for the collapsible UI."""

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=MessageStatus.choices, default=MessageStatus.COMPLETE
    )
    error = models.TextField(blank=True, default="")
    citations = models.JSONField(default=list, blank=True)
    tool_steps = models.JSONField(default=list, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        indexes = [models.Index(fields=["thread", "created_at"], name="message_thread_idx")]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"
