from __future__ import annotations

from urllib.parse import quote

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import ApiError, NotFoundError
from apps.ingestion import index_store
from apps.repos.models import Repository, UserRepository
from apps.repos.serializers import (
    AnalysisStartSerializer,
    CreateRepositorySerializer,
    FileContentSerializer,
    JobSerializer,
    RepositorySerializer,
    TreeSerializer,
)
from apps.repos.services import get_user_repository, latest_job, start_analysis


class NotIndexedYet(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "not_ready"
    default_detail = "This repository has not finished ingesting yet."


class RepositoryListCreateView(ListAPIView):
    serializer_class = RepositorySerializer

    def get_queryset(self):  # noqa: ANN201 - DRF signature
        repo_ids = (
            UserRepository.objects.filter(user=self.request.user)
            .order_by("-created_at")
            .values_list("repository_id", flat=True)
        )
        ids = list(repo_ids)
        by_id = {r.pk: r for r in Repository.objects.filter(pk__in=ids)}
        return [by_id[i] for i in ids if i in by_id]

    @extend_schema(request=CreateRepositorySerializer, responses={201: AnalysisStartSerializer})
    def post(self, request: Request) -> Response:
        payload = CreateRepositorySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = start_analysis(request.user, payload.validated_data["url"])
        body = AnalysisStartSerializer(
            {
                "repository": result.repository,
                "job": result.job,
                "created": result.created,
                "cached": result.cached,
            }
        ).data
        return Response(
            body, status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        )


class RepositoryDetailView(APIView):
    @extend_schema(responses=RepositorySerializer)
    def get(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        UserRepository.objects.filter(user=request.user, repository=repository).update(
            last_opened_at=timezone.now()
        )
        return Response(RepositorySerializer(repository).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        UserRepository.objects.filter(user=request.user, repository=repository).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobView(APIView):
    @extend_schema(responses=JobSerializer)
    def get(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        job = latest_job(repository)
        if job is None:
            raise NotFoundError("No ingestion job for this repository.")
        return Response(JobSerializer(job).data)


class TreeView(APIView):
    @extend_schema(responses=TreeSerializer)
    def get(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        files = [
            {k: f[k] for k in ("path", "language", "size", "lines")}
            for f in index_store.list_files(repository.pk)
        ]
        if not files and repository.status != "ready":
            raise NotIndexedYet()
        return Response({"files": files, "commit_sha": repository.commit_sha})


def _int_param(request: Request, name: str) -> int | None:
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise ApiError(f"'{name}' must be an integer.") from exc
    if number < 1:
        raise ApiError(f"'{name}' must be at least 1.")
    return number


class FileContentView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("path", str, required=True),
            OpenApiParameter("start", int),
            OpenApiParameter("end", int),
        ],
        responses=FileContentSerializer,
    )
    def get(self, request: Request, repo_id: str) -> Response:
        repository = get_user_repository(request.user, repo_id)
        path = request.query_params.get("path", "").strip().lstrip("/")
        if not path:
            raise ApiError("'path' is required.")
        file = index_store.get_file(repository.pk, path)
        if file is None:
            raise NotFoundError(f"File not found: {path}")
        content = index_store.get_blob(file["blob_sha"]) or ""
        lines = content.splitlines()
        total = max(1, len(lines))
        start = _int_param(request, "start") or 1
        end = _int_param(request, "end") or total
        if start > total:
            raise ApiError(f"start ({start}) is beyond the end of the file ({total} lines).")
        end = min(max(end, start), total)
        sliced = "\n".join(lines[start - 1 : end]) if (start, end) != (1, total) else content
        anchor = f"#L{start}" if start == end else f"#L{start}-L{end}"
        github_url = (
            f"{repository.url}/blob/{repository.commit_sha}/{quote(path)}"
            f"{anchor if (start, end) != (1, total) else ''}"
        )
        return Response(
            FileContentSerializer(
                {
                    "path": path,
                    "language": file["language"],
                    "size": file["size"],
                    "lines": total,
                    "start_line": start,
                    "end_line": end,
                    "content": sliced,
                    "symbols": file.get("symbols", []),
                    "github_url": github_url,
                }
            ).data
        )
