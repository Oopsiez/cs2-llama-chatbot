"""Backend-agnostic interface for the Llama 3 runtime."""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field

_TOKEN_NAMES = (
    r"im_end|im_start|eot_id|eom_id|end_of_turn|start_of_turn|endoftext|end_of_text|begin_of_text"
    r"|start_header_id|end_header_id|eos|bos|end|assistant|user|system"
)
# Chat-template markers some GGUFs leak into the reply, whole or mangled:
# "<|im_end|>", "</|im_end|", "<|eot_id|", "|im_end|>", "<|im_end" ...
_SPECIAL_TOKEN = re.compile(
    r"<\s*/?\s*\|[^|<>\s]{1,32}\|\s*>?"  # <|anything|>, </|im_end|
    rf"|<\s*/?\s*\|?\s*(?:{_TOKEN_NAMES})\b\s*\|?\s*>?"  # <|im_end, </im_end|>
    rf"|/?\|(?:{_TOKEN_NAMES})(?:\|\s*>?|>)"  # |im_end|>, |eot_id|
    r"|<\s*/?\s*\|?[a-z_]{0,16}$",  # cut off at the end: "<|im", "</"
    re.IGNORECASE,
)


def strip_special_tokens(text: str) -> str:
    """`text` without leaked chat-template markers, so nobody types or says "im_end"."""
    return re.sub(r"[ \t]{2,}", " ", _SPECIAL_TOKEN.sub(" ", text)).strip()


@dataclass
class SamplingParams:
    temperature: float = 0.8
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.15
    max_tokens: int = 80
    stop: list[str] = field(
        default_factory=lambda: [
            "\n\n",
            "<|eot_id|>",
            "<|im_end|>",
            "<|end|>",
            "<|endoftext|>",
            "|im_end|",
            "|eot_id|",
            "<|im_start|>",
        ]
    )


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

    async def warm(self) -> str:
        """Get the model into memory now, so the first reply does not have to."""
        return await self.health()

    async def aclose(self) -> None:
        return None
