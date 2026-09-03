"""Tiny pub/sub used to push live activity to every connected web client."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any


class EventBus:
    def __init__(self, history: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def publish(self, kind: str, payload: Any) -> None:
        event = {"kind": kind, "at": time.time(), "data": payload}
        self._history.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stalled client must not block the game loop; drop its oldest event.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
