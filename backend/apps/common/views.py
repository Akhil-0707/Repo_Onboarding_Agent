from __future__ import annotations

from django.core.cache import cache
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.mongo import get_db


class ServiceHealthView(APIView):
    """Liveness/readiness of the backend's own dependencies (MongoDB and Redis)."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        responses=inline_serializer(
            "ServiceHealth",
            {
                "status": serializers.CharField(),
                "mongo": serializers.BooleanField(),
                "cache": serializers.BooleanField(),
            },
        )
    )
    def get(self, request: Request) -> Response:
        mongo_ok = cache_ok = False
        try:
            get_db().command("ping")
            mongo_ok = True
        except Exception:  # noqa: S110 - health checks report, they do not raise
            pass
        try:
            cache.set("health:ping", "1", timeout=5)
            cache_ok = cache.get("health:ping") == "1"
        except Exception:  # noqa: S110
            pass
        healthy = mongo_ok and cache_ok
        return Response(
            {"status": "ok" if healthy else "degraded", "mongo": mongo_ok, "cache": cache_ok},
            status=200 if healthy else 503,
        )
