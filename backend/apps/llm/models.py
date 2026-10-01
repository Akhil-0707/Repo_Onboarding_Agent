from __future__ import annotations

from django.db import models


class RuntimeSetting(models.Model):
    """Key/value settings that can change while containers keep running.

    Used for the model server URL, which changes every time a Kaggle session restarts.
    """

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "runtime_settings"

    def __str__(self) -> str:
        return self.key
