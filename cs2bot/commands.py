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

STRATEGY, QUIET, TALK, PERSONA = "strategy", "quiet", "talk", "persona"

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
# "!persona coach", "bot be the coach", "act like a silver" - all the same order.
_PERSONA_WORDS = ("persona", "personas", "personality", "personalities")
# Said without the word "persona", so a name has to follow for it to be an order at all.
_PERSONA_LEADS = (("act", "like"), ("pretend", "to", "be"), ("switch", "to"), ("become",), ("be",))
# Said *to* the bot about what it is from now on - these carry a free-form instruction, so the
# words after them are kept whole instead of being matched against persona names only.
_INSTRUCTION_LEADS = (
    "you are now",
    "you're now",
    "from now on",
    "from now on you are",
    "your new personality is",
    "new persona:",
    "new personality:",
    "talk like",
    "speak like",
    "sound like",
)
_PERSONA_FILLER = {
    "a",
    "an",
    "the",
    "bot",
    "more",
    "please",
    "now",
    "mode",
    "to",
    "act",
    "like",
    "pretend",
    "switch",
    "become",
    "be",
    "go",
    "use",
    "your",
}
# "!persona", "!persona list", "what personas do you have" all mean the same thing.
_LIST_WORDS = {
    "list",
    "options",
    "what",
    "which",
    "who",
    "do",
    "you",
    "have",
    "got",
    "is",
    "are",
    "there",
    "available",
    "can",
    "say",
}


@dataclass(frozen=True)
class Command:
    kind: str
    site: str = ""
    persona: str = ""  # "" on a persona command means "tell me the ones you have"
    explicit: bool = False  # written as `!command`, so a name it cannot place is worth saying
    instruction: str = ""  # the whole order, for when it is not the name of a known persona


def _strip_prefix(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    for prefix in _PREFIXES:
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip(), True
    return stripped, False


def _mentions(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    return any(phrase.strip() and phrase.strip().casefold() in text for phrase in phrases)


def _names_in(words: list[str]) -> list[str]:
    """What is left of a persona order once the words everybody says are dropped."""
    return [w for w in words if w not in _PERSONA_FILLER and w not in _LIST_WORDS]


def _persona_wanted(words: list[str]) -> str | None:
    """The persona asked for, `""` for "which have you got", `None` if this is not the order."""
    for index, word in enumerate(words):
        if word in _PERSONA_WORDS:
            named = _names_in(words[index + 1 :])
            # People put the name on either side of the word: "persona coach", "coach persona".
            return " ".join(named or _names_in(words[:index]))
    for lead in _PERSONA_LEADS:
        for index in range(len(words) - len(lead) + 1):
            if tuple(words[index : index + len(lead)]) != lead:
                continue
            rest = _names_in(words[index + len(lead) :])
            if rest:
                return " ".join(rest)
    return None


def _instruction_in(body: str) -> str:
    """The order after "you are now" / "from now on" / "talk like", in the player's own words."""
    lowered = body.casefold().strip()
    for lead in sorted(_INSTRUCTION_LEADS, key=len, reverse=True):
        for prefix in (
            lead,
            "persona " + lead,
            "personality " + lead,
            "bot " + lead,
            "bot, " + lead,
            "ok bot " + lead,
            "hey bot " + lead,
        ):
            if lowered.startswith(prefix):
                rest = body.strip()[len(prefix) :].strip(" ,:-")
                if lead in ("talk like", "speak like", "sound like"):
                    rest = f"talk like {rest}"
                return rest if len(rest.split()) >= 1 else ""
    return ""


def parse(text: str, settings: StrategySettings) -> Command | None:
    """The order in a chat line, if there is one."""
    body, explicit = _strip_prefix(text)
    lowered = body.casefold().rstrip("?!. ")
    if not lowered:
        return None
    words = lowered.replace(",", " ").split()

    if settings.obey_commands and settings.obey_persona_commands:
        instruction = _instruction_in(body)
        if instruction:
            return Command(PERSONA, persona=instruction, explicit=True, instruction=instruction)

    # A long sentence that happens to contain "strat" is somebody talking, not somebody calling.
    if not explicit and len(words) > _MAX_COMMAND_WORDS:
        return None

    if settings.obey_commands:
        # "unmute" contains "mute", so being let off the leash is checked first.
        if _mentions(lowered, _TALK_WORDS):
            return Command(TALK)
        if _mentions(lowered, _QUIET_WORDS):
            return Command(QUIET)
        if settings.obey_persona_commands:
            wanted = _persona_wanted(words)
            if wanted is not None:
                return Command(PERSONA, persona=wanted, explicit=explicit)

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
