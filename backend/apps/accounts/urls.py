from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("auth/github/login", views.GitHubLoginView.as_view(), name="github-login"),
    path("auth/github/callback", views.GitHubCallbackView.as_view(), name="github-callback"),
    path("auth/exchange", views.ExchangeView.as_view(), name="auth-exchange"),
    path("auth/refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("me", views.MeView.as_view(), name="me"),
]
