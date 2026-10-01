from __future__ import annotations

from typing import Any

from celery import shared_task

from apps.llm.health import check_llm_health


@shared_task(ignore_result=True)
def probe_llm_health() -> dict[str, Any]:
    """Periodic probe (celery beat) that keeps the cached health fresh."""
    return check_llm_health(force=True).as_dict()
