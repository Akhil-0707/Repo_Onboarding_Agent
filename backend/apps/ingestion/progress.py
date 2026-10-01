"""Persist job progress to MongoDB and push it live through the event bus.

Writes use atomic PyMongo updates on the ``ingestion_jobs`` collection (array filters on
step keys, capped log arrays) so concurrent writers never clobber each other.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from apps.common.events import get_event_bus
from apps.common.logging import get_logger, scrub
from apps.common.mongo import get_db

logger = get_logger(__name__)

JOBS = "ingestion_jobs"
MAX_LOGS_PER_STEP = 200

# (key, label, weight) -- weights drive the overall progress percentage.
PIPELINE_STEPS: list[tuple[str, str, int]] = [
    ("resolve", "Resolve repository", 2),
    ("clone", "Clone repository", 15),
    ("filter", "Filter files", 5),
    ("detect", "Detect languages & frameworks", 3),
    ("parse", "Parse code", 25),
    ("chunk", "Chunk code", 15),
    ("store", "Save code index", 10),
    ("embed", "Generate embeddings", 25),
]


def channel(job_id: str) -> str:
    return f"ingest:job:{job_id}"


def now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    """Step timestamps live inside a JSONField, which must stay JSON-serialisable."""
    return now().isoformat()


def initial_steps() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "weight": weight,
            "status": "pending",
            "progress": 0,
            "message": "",
            "started_at": None,
            "finished_at": None,
            "logs": [],
        }
        for key, label, weight in PIPELINE_STEPS
    ]


class JobReporter:
    def __init__(self, job_id: str) -> None:
        self.job_id = str(job_id)
        self._oid = ObjectId(self.job_id)
        self._weights = {key: weight for key, _, weight in PIPELINE_STEPS}
        # Stages run in separate tasks: resume overall progress from what is stored.
        doc = get_db()[JOBS].find_one({"_id": self._oid}, {"steps.key": 1, "steps.status": 1})
        self._done: dict[str, float] = {
            step["key"]: 1.0
            for step in (doc or {}).get("steps", [])
            if step.get("status") in {"done", "skipped"}
        }

    # -- low level ----------------------------------------------------------------------------
    def _jobs(self) -> Any:
        return get_db()[JOBS]

    def _publish(self, event: dict[str, Any]) -> None:
        get_event_bus().publish(channel(self.job_id), event)

    def _overall(self) -> int:
        total = sum(self._weights.values()) or 1
        return min(100, int(sum(self._weights[k] * f for k, f in self._done.items()) * 100 / total))

    def _set_step(self, key: str, fields: dict[str, Any]) -> None:
        self._jobs().update_one(
            {"_id": self._oid},
            {
                "$set": {f"steps.$[s].{k}": v for k, v in fields.items()}
                | {"progress": self._overall()}
            },
            array_filters=[{"s.key": key}],
        )
        self._publish({"type": "step", "key": key, **fields, "job_progress": self._overall()})

    # -- API ----------------------------------------------------------------------------------
    def job_started(self) -> None:
        self._jobs().update_one(
            {"_id": self._oid}, {"$set": {"status": "running", "started_at": now(), "error": ""}}
        )
        self._publish({"type": "job", "status": "running"})

    def log(self, key: str, message: str, level: str = "info") -> None:
        entry = {"ts": iso_now(), "level": level, "message": scrub(message)}
        self._jobs().update_one(
            {"_id": self._oid},
            {"$push": {"steps.$[s].logs": {"$each": [entry], "$slice": -MAX_LOGS_PER_STEP}}},
            array_filters=[{"s.key": key}],
        )
        self._publish({"type": "log", "key": key, **entry})

    def progress(self, key: str, fraction: float, message: str = "") -> None:
        fraction = max(0.0, min(1.0, fraction))
        self._done[key] = fraction
        fields: dict[str, Any] = {"progress": int(fraction * 100)}
        if message:
            fields["message"] = message
        self._set_step(key, fields)

    def skip(self, key: str, message: str) -> None:
        self._done[key] = 1.0
        self._set_step(key, {"status": "skipped", "progress": 100, "message": message})

    def complete(self, key: str, message: str = "") -> None:
        self._done[key] = 1.0
        self._set_step(
            key, {"status": "done", "progress": 100, "message": message, "finished_at": iso_now()}
        )

    @contextmanager
    def step(self, key: str) -> Iterator[JobReporter]:
        self._set_step(key, {"status": "running", "started_at": iso_now()})
        try:
            yield self
        except Exception as exc:
            self._set_step(key, {"status": "failed", "finished_at": iso_now()})
            self.log(key, str(exc) or type(exc).__name__, level="error")
            raise
        if self._done.get(key) != 1.0:
            self.complete(key)

    def finish(self, status: str, error: str = "") -> None:
        self._jobs().update_one(
            {"_id": self._oid},
            {
                "$set": {
                    "status": status,
                    "error": scrub(error),
                    "finished_at": now(),
                    **({"progress": 100} if status == "done" else {}),
                }
            },
        )
        self._publish({"type": "job", "status": status, "error": scrub(error)})
