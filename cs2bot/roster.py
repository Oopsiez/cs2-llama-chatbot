"""Who is on our team, learned from chat.

A strat that says "one man holds apps" is not a call - somebody has to be told. Without GSI there
is no scoreboard to read, but team chat is proof of a teammate: only teammates appear in it. So
whoever has spoken in team chat this map is the roster, most recently heard first, and the
playbook hands them the jobs in that order.

All-chat says nothing about sides, so it is ignored here on purpose: putting an enemy's name on a
job is worse than saying "P3".
"""

from __future__ import annotations

from .models import ChatChannel, ChatMessage

MAX_TEAMMATES = 4  # the four other players; the fifth job is the bot's own


class Roster:
    """Teammates seen in team chat, newest first, minus ourselves."""

    def __init__(self, limit: int = MAX_TEAMMATES) -> None:
        self._limit = limit
        self._names: list[str] = []

    def clear(self) -> None:
        self._names.clear()

    def observe(self, message: ChatMessage) -> None:
        if message.channel is not ChatChannel.TEAM or message.is_self or not message.sender:
            return
        key = message.sender.casefold()
        self._names = [name for name in self._names if name.casefold() != key]
        self._names.insert(0, message.sender)
        del self._names[self._limit :]

    def names(self, exclude: str = "") -> list[str]:
        skip = exclude.casefold()
        return [name for name in self._names if name.casefold() != skip]
