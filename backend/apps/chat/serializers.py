from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from apps.chat.models import Message, Thread


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "status",
            "error",
            "citations",
            "tool_steps",
            "created_at",
        )
        read_only_fields = fields


class ThreadSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)

    class Meta:
        model = Thread
        fields = ("id", "title", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ThreadDetailSerializer(ThreadSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(ThreadSerializer.Meta):
        fields = (*ThreadSerializer.Meta.fields, "messages")

    def get_messages(self, thread: Thread) -> list[dict]:
        return MessageSerializer(thread.messages.order_by("created_at"), many=True).data


class AskSerializer(serializers.Serializer):
    content = serializers.CharField(trim_whitespace=True)

    def validate_content(self, value: str) -> str:
        limit = settings.CHAT_MAX_QUESTION_CHARS
        if len(value) > limit:
            raise serializers.ValidationError(f"Questions are limited to {limit} characters.")
        return value
