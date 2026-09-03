"""Keeping the bot from saying the same thing over and over.

Small models fall into grooves fast ("ez", "nice shot", "ez", ...), which is the fastest way for
a chat bot to read as a bot. Replies are compared against the last few things the bot said, both
as whole strings and as word sets, so "nice shot dude" and "dude nice shot" count as the same
line even though no substring matches.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

_WORD = re.compile(r"[a-z0-9']+")
# Words that are shared by almost any two chat lines and should not make them look alike.
_FILLER = frozenset({"a", "an", "the", "is", "was", "to", "of", "and", "i", "you", "u", "it"})


def _key(text: str) -> str:
    return " ".join(_WORD.findall(text.casefold()))


def _content_words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if word not in _FILLER}


def similarity(left: str, right: str) -> float:
    """0..1 overlap between two replies: the higher of string ratio and word overlap."""
    a, b = _key(left), _key(right)
    if not a or not b:
        return 1.0 if a == b else 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    left_words, right_words = _content_words(a), _content_words(b)
    if left_words and right_words:
        shared = len(left_words & right_words) / min(len(left_words), len(right_words))
        ratio = max(ratio, shared)
    return ratio


def is_repetitive(text: str, recent: Iterable[str], threshold: float) -> str | None:
    """The earlier reply `text` echoes, or None if it is fresh enough."""
    if not text.strip():
        return None
    for previous in recent:
        if similarity(text, previous) >= threshold:
            return previous
    return None


def avoid_note(recent: Iterable[str]) -> str | None:
    """Prompt line listing what the bot already said, so it can steer away from it."""
    lines = [line.strip() for line in recent if line.strip()]
    if not lines:
        return None
    quoted = "; ".join(f'"{line}"' for line in lines)
    return (
        f"You already said: {quoted}. Say something clearly different this time - new wording, "
        "new angle, do not restate those."
    )
