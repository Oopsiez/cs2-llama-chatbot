"""Offline backend so the UI, parser and delivery rules can be exercised without a model."""

from __future__ import annotations

import asyncio
import random

from .base import ChatTurn, LLMBackend, SamplingParams

_CANNED = [
    "yeah that was my bad, rotating now",
    "nice shot, genuinely",
    "who queued for this map",
    "eco next round, trust me",
    "smoke is up, take it",
]


class MockBackend(LLMBackend):
    name = "mock"

    def __init__(self, delay: float = 0.05, seed: int | None = None) -> None:
        self._delay = delay
        self._random = random.Random(seed)

    async def generate(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        await asyncio.sleep(self._delay)
        last_user = next((t.content for t in reversed(turns) if t.role == "user"), "")
        reply = self._random.choice(_CANNED)
        if last_user:
            reply = f"{reply} ({last_user.strip()[:40]})"
        return reply[: max(16, params.max_tokens * 4)]

    async def health(self) -> str:
        return "mock backend (no model loaded)"
