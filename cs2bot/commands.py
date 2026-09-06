"""Orders given to the bot in chat.

Teammates type at the bot the way they type at a human - "strat?", "!strat b", "bot shut up" -
so the parser accepts both the `!command` form and the bare phrases people actually use. A
command is only recognised when the line is short: "so what do we do about the eco next round"
is conversation, not a call for a strat, and the bot should answer it as chat.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import StrategySettings
from .models import ChatChannel

STRATEGY, QUIET, TALK = "strategy", "quiet", "talk"

_PREFIXES = ("!", ".", "/")
_MAX_COMMAND_WORDS = 6

_SITE_WORDS = {
    "a": "a",
    "asite": "a",
    "a-site": "a",
    "long": "a",
    "b": "b",
    "bsite": "b",
    "b-site": "b",
    "mid": "mid",
    "middle": "mid",
}
_QUIET_WORDS = ("quiet", "mute", "shut up", "stfu", "shush")
_TALK_WORDS = ("talk", "unmute", "speak", "wake up")


@dataclass(frozen=True)
class Command:
    kind: str
    site: str = ""


def _strip_prefix(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    for prefix in _PREFIXES:
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip(), True
    return stripped, False


def _mentions(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    return any(phrase.strip() and phrase.strip().casefold() in text for phrase in phrases)


def parse(text: str, settings: StrategySettings) -> Command | None:
    """The order in a chat line, if there is one."""
    body, explicit = _strip_prefix(text)
    lowered = body.casefold().rstrip("?!. ")
    if not lowered:
        return None
    words = lowered.replace(",", " ").split()
    # A long sentence that happens to contain "strat" is somebody talking, not somebody calling.
    if not explicit and len(words) > _MAX_COMMAND_WORDS:
        return None

    if settings.obey_commands:
        # "unmute" contains "mute", so being let off the leash is checked first.
        if _mentions(lowered, _TALK_WORDS):
            return Command(TALK)
        if _mentions(lowered, _QUIET_WORDS):
            return Command(QUIET)

    if not settings.answer_when_asked:
        return None
    if not _mentions(lowered, settings.request_phrases):
        return None
    site = ""
    for word in words:
        if word in _SITE_WORDS:
            site = _SITE_WORDS[word]
            break
    return Command(STRATEGY, site)


def listens_to(settings: StrategySettings, channel: ChatChannel) -> bool:
    """Whether an order arriving in this channel counts."""
    if settings.listen_channel == "both":
        return channel in (ChatChannel.ALL, ChatChannel.TEAM)
    if settings.listen_channel == "team":
        return channel is ChatChannel.TEAM
    return channel is ChatChannel.ALL


def answer_in_team_chat(settings: StrategySettings, asked_in: ChatChannel) -> bool:
    """Whether the answer goes to team chat - a strat is usually not for the enemy to read."""
    if settings.reply_channel == "same":
        return asked_in is ChatChannel.TEAM
    return settings.reply_channel == "team"
