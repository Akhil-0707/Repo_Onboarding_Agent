from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import Analysis
from apps.analysis.sections import SECTIONS, get_section
from apps.common.errors import NotFoundError
from apps.repos.services import get_user_repository


class SectionSerializer(serializers.Serializer):
    status = serializers.CharField()
    error = serializers.CharField(allow_blank=True)
    updated_at = serializers.CharField(allow_null=True)
    data = serializers.JSONField(allow_null=True)


class AnalysisSerializer(serializers.Serializer):
    status = serializers.CharField()
    model = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True)
    sections = serializers.DictField(child=SectionSerializer())
    usage = serializers.DictField()
    est_cost = serializers.FloatField()
    waiting_since = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


def section_payload(analysis: Analysis | None, key: str) -> dict[str, Any]:
    state = ((analysis.sections if analysis else {}) or {}).get(key) or {}
    return {
        "status": state.get("status", "pending"),
        "error": state.get("error", ""),
        "updated_at": state.get("updated_at"),
        "data": state.get("data"),
    }


def analysis_payload(analysis: Analysis | None) -> dict[str, Any]:
    return {
        "status": analysis.status if analysis else "pending",
        "model": analysis.model if analysis else "",
        "error": analysis.error if analysis else "",
        "sections": {spec.key: section_payload(analysis, spec.key) for spec in SECTIONS},
        "usage": (analysis.usage if analysis else {}) or {},
        "est_cost": analysis.est_cost if analysis else 0.0,
        "waiting_since": analysis.waiting_since if analysis else None,
        "started_at": analysis.started_at if analysis else None,
        "finished_at": analysis.finished_at if analysis else None,
    }


class AnalysisView(APIView):
    @extend_schema(responses=AnalysisSerializer)
    def get(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        analysis = Analysis.objects.filter(repository=repository).first()
        return Response(AnalysisSerializer(analysis_payload(analysis)).data)


class AnalysisSectionView(APIView):
    @extend_schema(responses=SectionSerializer)
    def get(self, request: Request, repo_id: str, section: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        if get_section(section) is None:
            raise NotFoundError(f"Unknown section '{section}'.")
        analysis = Analysis.objects.filter(repository=repository).first()
        return Response(SectionSerializer(section_payload(analysis, section)).data)
