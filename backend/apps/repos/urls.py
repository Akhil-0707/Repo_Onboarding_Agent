from django.urls import path

from apps.analysis import views as analysis_views
from apps.repos import stream, views

urlpatterns = [
    path("repos", views.RepositoryListCreateView.as_view(), name="repo-list"),
    path("repos/<str:repo_id>", views.RepositoryDetailView.as_view(), name="repo-detail"),
    path("repos/<str:repo_id>/reanalyze", views.ReanalyzeView.as_view(), name="repo-reanalyze"),
    path("repos/<str:repo_id>/job", views.JobView.as_view(), name="repo-job"),
    path("repos/<str:repo_id>/job/stream", stream.job_stream_view, name="repo-job-stream"),
    path("repos/<str:repo_id>/tree", views.TreeView.as_view(), name="repo-tree"),
    path("repos/<str:repo_id>/files", views.FileContentView.as_view(), name="repo-file"),
    path("repos/<str:repo_id>/analysis", analysis_views.AnalysisView.as_view(), name="analysis"),
    path(
        "repos/<str:repo_id>/analysis/<str:section>",
        analysis_views.AnalysisSectionView.as_view(),
        name="analysis-section",
    ),
]
