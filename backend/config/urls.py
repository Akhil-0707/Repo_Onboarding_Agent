from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.errors import not_found_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/health", include("apps.common.urls")),
    path("api/llm/", include("apps.llm.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.repos.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.usage.urls")),
    # Last: unknown API URLs get the JSON error envelope (also with DEBUG on).
    re_path(r"^api/", not_found_view),
]

handler404 = "apps.common.errors.not_found_view"
handler500 = "apps.common.errors.server_error_view"
