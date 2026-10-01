from django.urls import path

from apps.chat import stream, views

urlpatterns = [
    path("repos/<str:repo_id>/threads", views.ThreadListCreateView.as_view(), name="thread-list"),
    path(
        "repos/<str:repo_id>/threads/<str:thread_id>",
        views.ThreadDetailView.as_view(),
        name="thread-detail",
    ),
    path(
        "repos/<str:repo_id>/threads/<str:thread_id>/messages",
        views.MessageListView.as_view(),
        name="thread-messages",
    ),
    path(
        "repos/<str:repo_id>/threads/<str:thread_id>/messages/stream",
        stream.message_stream_view,
        name="thread-message-stream",
    ),
]
