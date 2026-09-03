"""Recognise the bot's own chat lines coming back out of the console log.

Everything the bot types goes through CS2 and is written straight back to `console.log`, where it
looks exactly like anybody else's message. The only thing marking it as ours is the name on it -
so until the user's name is resolved (no GSI yet, nothing said in the log yet) the bot reads its
own line, answers it, reads *that* back, and holds a conversation with itself until the round
ends. Team chat makes it worse: both sides of the loop are in the same channel, so nothing else
breaks it up.

Matching on the *text* we just sent closes the loop whatever name it arrives under. Replies are
chunked to fit CS2's chat limit, so a line coming back may be a piece of a longer reply; a
containment check either way catches those too.
"""

from __future__ import annotations

import re
import time

_NOISE = re.compile(r"[^0-9a-z]+")

MEMORY_SECONDS = 90.0
# Short enough that "gg" or "yes" cannot silence a real player who happens to agree with us.
MIN_FRAGMENT = 8


def echo_key(text: str) -> str:
    """Strip everything a chat round-trip might change: case, punctuation, spacing."""
    return _NOISE.sub(" ", text.casefold()).strip()


class EchoGuard:
    """Remembers what the bot recently said so the same text is never treated as input."""

    def __init__(self, window: float = MEMORY_SECONDS) -> None:
        self.window = window
        self._sent: list[tuple[float, str]] = []

    def remember(self, text: str, now: float | None = None) -> None:
        key = echo_key(text)
        if not key:
            return
        now = time.time() if now is None else now
        self._sent.append((now, key))
        self._expire(now)

    def is_echo(self, text: str, now: float | None = None) -> bool:
        key = echo_key(text)
        if not key:
            return False
        now = time.time() if now is None else now
        self._expire(now)
        for _, sent in self._sent:
            if key == sent:
                return True
            # The *overlap* has to be substantial: a remembered "gg" sits inside plenty of
            # innocent sentences, and silencing those would be worse than the loop.
            if min(len(key), len(sent)) >= MIN_FRAGMENT and (key in sent or sent in key):
                return True
        return False

    def forget(self) -> None:
        self._sent.clear()

    def _expire(self, now: float) -> None:
        self._sent = [entry for entry in self._sent if now - entry[0] <= self.window]
