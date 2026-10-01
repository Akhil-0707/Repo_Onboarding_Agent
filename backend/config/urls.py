from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/health", include("apps.common.urls")),
    path("api/llm/", include("apps.llm.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.repos.urls")),
]
