from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

log = logging.getLogger("wague.realtime")


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def _keys(self, user_id: UUID | None, *, admin: bool) -> list[str]:
        keys = ["broadcast"]
        if user_id is not None:
            keys.append(f"user:{user_id}")
        if admin:
            keys.append("admin")
        return keys

    async def subscribe(self, user_id: UUID, *, admin: bool) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            for key in self._keys(user_id, admin=admin):
                self._subs[key].add(queue)
        return queue

    async def unsubscribe(self, user_id: UUID, queue: asyncio.Queue, *, admin: bool) -> None:
        async with self._lock:
            for key in self._keys(user_id, admin=admin):
                self._subs[key].discard(queue)

    def publish(self, event: dict, *, user_id: UUID | None = None, admin: bool = False) -> None:
        targets: set[asyncio.Queue] = set()
        for key in self._keys(user_id, admin=admin):
            targets.update(self._subs.get(key, set()))
        for queue in targets:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("dropping realtime event; subscriber queue is full")


hub = Hub()
