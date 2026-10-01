from django.urls import path

from apps.llm.views import LLMHealthView

urlpatterns = [
    path("health", LLMHealthView.as_view(), name="llm-health"),
]
