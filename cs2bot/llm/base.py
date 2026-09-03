"""Backend-agnostic interface for the Llama 3 runtime."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class SamplingParams:
    temperature: float = 0.8
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.15
    max_tokens: int = 80
    stop: list[str] = field(default_factory=lambda: ["\n\n", "<|eot_id|>"])


@dataclass
class ChatTurn:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(RuntimeError):
    pass


class LLMBackend(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def generate(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        """Return the assistant reply for `turns`."""

    async def health(self) -> str:
        """Human-readable readiness string; raises LLMError when unusable."""
        return "ok"

    async def aclose(self) -> None:
        return None
