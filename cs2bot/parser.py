"""Turn raw CS2 `console.log` lines into `ChatMessage` objects.

CS2 writes chat to `console.log` when the game runs with `-condebug`. The exact shape varies
with `con_timestamp`, the server's chat plugins and the game mode, so instead of one strict
regex we try a small ladder of patterns and normalise the result. Anything that does not carry
a recognised chat marker (a `[ALL]`/`[CT]`/`[T]`/`[DEAD]`/`[SPEC]` tag, a `*DEAD*`/`*SPEC*`
prefix, a team tag, or the `"Name<..>" say "..."` server format) is ignored, which keeps ordinary
console spam out of the bot.
"""

from __future__ import annotations

import re
import unicodedata

from .models import ChatChannel, ChatMessage, LifeState, Team

# `MM/DD HH:MM:SS  ` and `MM/DD/YYYY - HH:MM:SS: ` timestamp prefixes.
_TIMESTAMP = re.compile(
    r"^\d{2}/\d{2}(?:/\d{2,4})?\s*(?:-\s*)?\d{2}:\d{2}:\d{2}\s*:?\s+"
)

_SRCDS = re.compile(
    r'^"(?P<name>.*?)<\d+><(?P<sid>[^>]*)><(?P<team>[^>]*)>"\s+(?P<cmd>say|say_team)\s+"(?P<text>.*)"\s*$'
)

_CHANNEL_TAG = re.compile(r"^\[(?P<tag>ALL|CT|T|DEAD|SPEC|SPECTATOR)\]\s*", re.IGNORECASE)
_DEAD_PREFIX = re.compile(r"^\*DEAD\*\s*")
_SPEC_PREFIX = re.compile(r"^\*SPEC\*\s*")
_TEAM_TAG = re.compile(r"^\((?P<team>Counter-Terrorist|Terrorist|Spectator|CT|T|SPEC)\)\s*", re.IGNORECASE)
_NAME_TEXT = re.compile(r"^(?P<name>.+?)\s*:\s(?P<text>.*)$")

_TEAM_BY_NAME = {
    "ct": Team.CT,
    "counter-terrorist": Team.CT,
    "t": Team.T,
    "terrorist": Team.T,
    "spec": Team.SPECTATOR,
    "spectator": Team.SPECTATOR,
    "unassigned": Team.UNKNOWN,
}


def _clean(text: str) -> str:
    """Drop the bidi marks and control characters CS2 sprinkles into names."""
    out = []
    for ch in text:
        if ch in "\u200b\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069\ufeff":
            continue
        if unicodedata.category(ch) == "Cc" and ch not in "\t":
            continue
        out.append(ch)
    return "".join(out).strip()


def _team(value: str | None) -> Team:
    if not value:
        return Team.UNKNOWN
    return _TEAM_BY_NAME.get(value.strip().lower(), Team.UNKNOWN)


def _same_player(sender: str, own_name: str) -> bool:
    if not own_name:
        return False
    return sender.strip().casefold() == own_name.strip().casefold()


def parse_chat_line(line: str, own_name: str = "") -> ChatMessage | None:
    """Parse a single console line. Returns None when the line is not player chat."""
    raw = line.rstrip("\r\n")
    body = _clean(_TIMESTAMP.sub("", _clean(raw)))
    if not body:
        return None

    srcds = _SRCDS.match(body)
    if srcds:
        sender = _clean(srcds.group("name"))
        return ChatMessage(
            raw=raw,
            sender=sender,
            text=_clean(srcds.group("text")),
            channel=ChatChannel.TEAM if srcds.group("cmd") == "say_team" else ChatChannel.ALL,
            sender_team=_team(srcds.group("team")),
            is_self=_same_player(sender, own_name),
        )

    channel = ChatChannel.UNKNOWN
    state = LifeState.UNKNOWN
    team = Team.UNKNOWN
    saw_marker = False

    tag = _CHANNEL_TAG.match(body)
    if tag:
        saw_marker = True
        body = body[tag.end() :]
        name = tag.group("tag").upper()
        if name == "ALL":
            channel = ChatChannel.ALL
        elif name in ("CT", "T"):
            channel = ChatChannel.TEAM
            team = _team(name)
        elif name == "DEAD":
            channel = ChatChannel.ALL
            state = LifeState.DEAD
        else:
            channel = ChatChannel.SPEC
            team = Team.SPECTATOR

    # `*DEAD*` / `*SPEC*` may sit on either side of the channel tag depending on the server.
    for _ in range(2):
        if _DEAD_PREFIX.match(body):
            saw_marker = True
            state = LifeState.DEAD
            body = _DEAD_PREFIX.sub("", body, count=1)
            continue
        if _SPEC_PREFIX.match(body):
            saw_marker = True
            channel = ChatChannel.SPEC
            team = Team.SPECTATOR
            body = _SPEC_PREFIX.sub("", body, count=1)
            continue
        break

    team_tag = _TEAM_TAG.match(body)
    if team_tag:
        saw_marker = True
        team = _team(team_tag.group("team"))
        if channel is ChatChannel.UNKNOWN:
            channel = ChatChannel.SPEC if team is Team.SPECTATOR else ChatChannel.TEAM
        body = body[team_tag.end() :]

    if not saw_marker:
        return None

    # A channel tag can also follow the `*DEAD*` prefix, e.g. `*DEAD* [ALL] name: text`.
    tag = _CHANNEL_TAG.match(body)
    if tag:
        body = body[tag.end() :]
        name = tag.group("tag").upper()
        if name == "ALL":
            channel = ChatChannel.ALL
        elif name in ("CT", "T"):
            channel = ChatChannel.TEAM
            team = _team(name)

    match = _NAME_TEXT.match(body)
    if not match:
        return None

    sender = _clean(match.group("name"))
    text = _clean(match.group("text"))
    if not sender or not text:
        return None

    if state is LifeState.UNKNOWN and channel is not ChatChannel.SPEC:
        state = LifeState.ALIVE

    return ChatMessage(
        raw=raw,
        sender=sender,
        text=text,
        channel=channel,
        sender_state=state,
        sender_team=team,
        is_self=_same_player(sender, own_name),
    )
