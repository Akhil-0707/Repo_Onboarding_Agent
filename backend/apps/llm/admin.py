from django.contrib import admin
from django.http import HttpRequest

from apps.llm.config import invalidate_cache
from apps.llm.models import RuntimeSetting


@admin.register(RuntimeSetting)
class RuntimeSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_at")
    search_fields = ("key",)

    def save_model(
        self, request: HttpRequest, obj: RuntimeSetting, form: object, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        invalidate_cache()
