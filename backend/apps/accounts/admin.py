from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "github_id", "is_staff", "date_joined")
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("GitHub", {"fields": ("github_id", "avatar_url", "github_scopes")}),
    )
