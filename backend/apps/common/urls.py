from django.urls import path

from apps.common.views import ServiceHealthView

urlpatterns = [
    path("", ServiceHealthView.as_view(), name="service-health"),
]
