from django.urls import path

from apps.usage import views

urlpatterns = [
    path("usage", views.UserUsageView.as_view(), name="usage"),
    path("repos/<str:repo_id>/usage", views.RepositoryUsageView.as_view(), name="repo-usage"),
]
