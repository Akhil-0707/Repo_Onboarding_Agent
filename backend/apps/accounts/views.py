"""GitHub OAuth sign-in and JWT session endpoints.

Flow:
1. ``GET /api/auth/github/login``: sets a signed state cookie, then redirects to GitHub.
2. ``GET /api/auth/github/callback``: verifies state, exchanges the code, upserts the user,
   then redirects to the SPA with a one-time code (never a token in the URL).
3. ``POST /api/auth/exchange``: the SPA trades the code for an access token (JSON body) plus
   a refresh token in an httpOnly cookie.
4. ``POST /api/auth/refresh`` rotates the refresh cookie. ``POST /api/auth/logout`` revokes
   every session.
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core.signing import BadSignature
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.github_oauth import GitHubOAuthError, get_oauth_client
from apps.accounts.serializers import AccessTokenSerializer, ExchangeSerializer, UserSerializer
from apps.accounts.services import (
    InvalidSession,
    create_exchange_code,
    issue_tokens,
    redeem_exchange_code,
    revoke_all_sessions,
    rotate_refresh_token,
    upsert_github_user,
)
from apps.common.errors import ApiError
from apps.common.logging import get_logger

logger = get_logger(__name__)

STATE_SALT = "repoguide.oauth-state"
STATE_MAX_AGE = 600
DEFAULT_NEXT = "/dashboard"


class InvalidExchangeCode(ApiError):
    default_code = "invalid_code"
    default_detail = "This sign-in link has expired. Please sign in again."


class SessionExpired(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "session_expired"
    default_detail = "Your session has expired. Please sign in again."


class MissingClientHeader(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "csrf_failed"
    default_detail = "Missing client header."


def safe_next(value: str | None) -> str:
    """Only allow same-site relative paths (prevents open redirects)."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return DEFAULT_NEXT
    return value


def frontend_redirect(**params: str) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/auth/callback?{urlencode(params)}")


def set_refresh_cookie(response: HttpResponse, refresh: str) -> None:
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="Lax",
        path=settings.AUTH_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: HttpResponse) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE, path=settings.AUTH_REFRESH_COOKIE_PATH, samesite="Lax"
    )


def require_client_header(request: HttpRequest) -> None:
    if request.headers.get(settings.AUTH_CLIENT_HEADER) != "web":
        raise MissingClientHeader()


class GitHubLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[
            OpenApiParameter("private", bool, description="Also request private repo access"),
            OpenApiParameter("next", str, description="Relative path to return to"),
        ],
        responses={302: None},
    )
    def get(self, request: Request) -> HttpResponse:
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            return frontend_redirect(error="GitHub sign-in is not configured on this server.")
        private = request.query_params.get("private") in {"1", "true"}
        state = secrets.token_urlsafe(24)
        response = HttpResponseRedirect(get_oauth_client().authorize_url(state, private=private))
        response.set_signed_cookie(
            settings.AUTH_OAUTH_STATE_COOKIE,
            json.dumps({"state": state, "next": safe_next(request.query_params.get("next"))}),
            salt=STATE_SALT,
            max_age=STATE_MAX_AGE,
            httponly=True,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite="Lax",
        )
        return response


class GitHubCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(responses={302: None})
    def get(self, request: Request) -> HttpResponse:
        try:
            stored = json.loads(
                request.get_signed_cookie(
                    settings.AUTH_OAUTH_STATE_COOKIE, salt=STATE_SALT, max_age=STATE_MAX_AGE
                )
            )
        except (KeyError, BadSignature, ValueError):
            stored = {}

        def fail(message: str) -> HttpResponse:
            response = frontend_redirect(error=message)
            response.delete_cookie(settings.AUTH_OAUTH_STATE_COOKIE)
            return response

        if request.query_params.get("error"):
            return fail("GitHub sign-in was cancelled.")
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        if not stored.get("state") or not secrets.compare_digest(stored["state"], state):
            logger.warning("oauth_state_mismatch")
            return fail("Sign-in expired or was tampered with. Please try again.")
        if not code:
            return fail("GitHub did not return an authorization code.")

        client = get_oauth_client()
        try:
            token = client.exchange_code(code)
            profile = client.fetch_profile(token)
        except GitHubOAuthError as exc:
            logger.warning("oauth_exchange_failed", error=str(exc))
            return fail(str(exc))

        user = upsert_github_user(profile, token)
        response = frontend_redirect(
            code=create_exchange_code(user), next=safe_next(stored.get("next"))
        )
        response.delete_cookie(settings.AUTH_OAUTH_STATE_COOKIE)
        return response


class ExchangeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=ExchangeSerializer, responses=AccessTokenSerializer)
    def post(self, request: Request) -> Response:
        serializer = ExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = redeem_exchange_code(serializer.validated_data["code"])
        if user is None:
            raise InvalidExchangeCode()
        tokens = issue_tokens(user)
        response = Response({"access": tokens.access, "user": UserSerializer(user).data})
        set_refresh_cookie(response, tokens.refresh)
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=None, responses=AccessTokenSerializer)
    def post(self, request: Request) -> Response:
        require_client_header(request)
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if not raw:
            raise SessionExpired()
        try:
            user, tokens = rotate_refresh_token(raw)
        except InvalidSession as exc:
            response = Response(
                {"error": {"code": "session_expired", "message": str(exc), "details": None}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response
        response = Response({"access": tokens.access, "user": UserSerializer(user).data})
        set_refresh_cookie(response, tokens.refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        require_client_header(request)
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if raw:
            try:
                user, _ = rotate_refresh_token(raw)
                revoke_all_sessions(user)
            except InvalidSession:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
