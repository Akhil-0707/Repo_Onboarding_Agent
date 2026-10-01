from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.llm.health import check_llm_health


class LLMHealthSerializer(serializers.Serializer):
    online = serializers.BooleanField()
    model = serializers.CharField()
    latency_ms = serializers.IntegerField(allow_null=True)
    checked_at = serializers.CharField()
    error = serializers.CharField(allow_null=True)


class LLMHealthView(APIView):
    """Whether the self-hosted model server is reachable. Public so the landing page can show
    the offline banner; it never reveals the server URL or key."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(responses=LLMHealthSerializer)
    def get(self, request: Request) -> Response:
        status = check_llm_health(force=request.query_params.get("refresh") == "1")
        return Response(LLMHealthSerializer(status.as_dict()).data)
