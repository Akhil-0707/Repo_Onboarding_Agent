from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.repos.models import IngestionJob, Repository


class JobSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = IngestionJob
        fields = (
            "id",
            "status",
            "progress",
            "error",
            "steps",
            "created_at",
            "started_at",
            "finished_at",
        )
        read_only_fields = fields


class JobSummarySerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = IngestionJob
        fields = ("id", "status", "progress", "error", "created_at", "finished_at")
        read_only_fields = fields


class RepositorySerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    latest_job = serializers.SerializerMethodField()
    analysis_status = serializers.SerializerMethodField()

    class Meta:
        model = Repository
        fields = (
            "id",
            "owner",
            "name",
            "full_name",
            "url",
            "description",
            "default_branch",
            "commit_sha",
            "private",
            "status",
            "error",
            "stats",
            "languages",
            "frameworks",
            "detection",
            "created_at",
            "ingested_at",
            "latest_job",
            "analysis_status",
        )
        read_only_fields = fields

    def get_analysis_status(self, repository: Repository) -> str:
        from apps.analysis.models import Analysis

        analysis = Analysis.objects.filter(repository=repository).only("status").first()
        return analysis.status if analysis else "pending"

    def get_latest_job(self, repository: Repository) -> dict[str, Any] | None:
        job = repository.jobs.order_by("-created_at").first()
        return JobSummarySerializer(job).data if job else None


class CreateRepositorySerializer(serializers.Serializer):
    url = serializers.CharField(max_length=500)


class AnalysisStartSerializer(serializers.Serializer):
    repository = RepositorySerializer()
    job = JobSerializer(allow_null=True)
    created = serializers.BooleanField()
    cached = serializers.BooleanField()


class FileEntrySerializer(serializers.Serializer):
    path = serializers.CharField()
    language = serializers.CharField()
    size = serializers.IntegerField()
    lines = serializers.IntegerField()


class TreeSerializer(serializers.Serializer):
    files = FileEntrySerializer(many=True)
    commit_sha = serializers.CharField()


class FileContentSerializer(serializers.Serializer):
    path = serializers.CharField()
    language = serializers.CharField()
    size = serializers.IntegerField()
    lines = serializers.IntegerField()
    start_line = serializers.IntegerField()
    end_line = serializers.IntegerField()
    content = serializers.CharField(allow_blank=True)
    symbols = serializers.ListField(child=serializers.DictField())
    github_url = serializers.URLField()
