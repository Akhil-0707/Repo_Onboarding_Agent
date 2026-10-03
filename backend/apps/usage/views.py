from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.repos.services import get_user_repository
from apps.usage.services import repository_usage, user_usage


class UserUsageView(APIView):
    def get(self, request: Request) -> Response:
        """Tokens, latency and estimated cost across your analyses and chats, plus rate limits."""
        return Response(user_usage(request.user))


class RepositoryUsageView(APIView):
    def get(self, request: Request, repo_id: str) -> Response:
        """The snapshot's analysis usage and your chat usage on it."""
        repository = get_user_repository(request.user, repo_id)
        return Response(repository_usage(request.user, repository))
