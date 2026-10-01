"""Tiny pub/sub abstraction used to push live progress from Celery workers to SSE clients."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from django.conf import settings

from apps.common.logging import get_logger

logger = get_logger(__name__)


class EventBus(ABC):
    @abstractmethod
    def publish(self, channel: str, event: dict[str, Any]) -> None: ...

    @abstractmethod
    def subscribe(self, channel: str, tick: float = 15.0) -> AsyncIterator[dict[str, Any] | None]:
        """Yield ``None`` once subscribed (so callers can snapshot state without missing
        events), then events, plus ``None`` every ``tick`` seconds without one."""


class RedisEventBus(EventBus):
    def __init__(self, url: str) -> None:
        import redis

        self.url = url
        self._sync = redis.Redis.from_url(url)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        try:
            self._sync.publish(channel, json.dumps(event, default=str))
        except Exception as exc:  # progress is best effort; Mongo holds the truth
            logger.warning("event_publish_failed", channel=channel, error=str(exc))

    async def subscribe(
        self, channel: str, tick: float = 15.0
    ) -> AsyncIterator[dict[str, Any] | None]:
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(self.url)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield None
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=tick)
                if message is None:
                    yield None
                    continue
                try:
                    yield json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()


class InMemoryEventBus(EventBus):
    """For tests: same-process delivery through asyncio queues."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        self.published.append((channel, event))
        for queue in self._queues[channel]:
            queue.put_nowait(event)

    async def subscribe(
        self, channel: str, tick: float = 15.0
    ) -> AsyncIterator[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[channel].append(queue)
        try:
            yield None
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=tick)
                except TimeoutError:
                    yield None
        finally:
            self._queues[channel].remove(queue)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus(settings.REDIS_URL)
    return _bus


def set_event_bus(bus: EventBus | None) -> None:
    global _bus
    _bus = bus
