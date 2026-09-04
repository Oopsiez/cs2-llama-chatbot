"""Work out what the user is called in game, and whether a message is aimed at them.

Two separate problems:

* **Who am I?** The name matters for filtering out the bot's own chat and for telling the model
  who it is. It comes from three places, in order of trust: what the user typed in the panel,
  the Game State Integration payload, and finally the console log itself (CS2 echoes the `name`
  cvar and prints name changes).
* **Is someone talking to me?** Players rarely type the full name: they shorten it, drop the
  clan tag, mangle the case, or just prefix `name:`. `addressed_to` does a tolerant match over
  the name plus any aliases, and also treats "you"-style replies to something the bot just said
  as directed at the user.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# `MM/DD HH:MM:SS  ` and `MM/DD/YYYY - HH:MM:SS: ` timestamp prefixes (`con_timestamp 1`).
TIMESTAMP = re.compile(r"^\d{2}/\d{2}(?:/\d{2,4})?\s*(?:-\s*)?\d{2}:\d{2}:\d{2}\s*:?\s+")

# What the console prints when the `name` cvar is echoed. Source wrote
# `"name" = "Oopsiez" ( def. "unnamed" )`; CS2 also prints it bare, and the console echoes the
# command back with a `] ` prompt.
_CVAR_ECHO = re.compile(
    r'^\]?\s*"?name"?\s*=\s*(?:"(?P<quoted>.*?)"|(?P<bare>[^"(]+?))'
    r'\s*(?:\(\s*def\.|$)',
    re.IGNORECASE,
)
# `setinfo name "Oopsiez"` / `name "Oopsiez"` typed into the console.
_NAME_COMMAND = re.compile(r'^(?:setinfo\s+)?name\s+"(?P<name>.+?)"\s*$', re.IGNORECASE)
# `Oopsiez changed name to skelly` (source-style rename notice).
_RENAME = re.compile(r"^(?:Player\s+)?(?P<old>.+?) changed (?:their )?name to (?P<new>.+?)\.?$")

_SECOND_PERSON = re.compile(r"\b(you|u|ur|your|youre|yours|yourself)\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"})

# Clan tags and decoration players wrap around their nickname: `[EZ] xX_name_Xx | twitch.tv/x`.
_DECORATION = re.compile(r"[\[\](){}<>|/\\*_~^`'\"?!.,:;+=-]+")
_CLAN_TAG = re.compile(r"^\s*[\[({<][^\])}>]{1,12}[\])}>]\s*|\s*[\[({<][^\])}>]{1,12}[\])}>]\s*$")

MIN_HANDLE = 3


@dataclass(frozen=True)
class Mention:
    """Why a message counts as being aimed at the user (or not)."""

    addressed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.addressed


def normalize_handle(name: str) -> str:
    """Reduce a nickname to comparable letters: no accents, no leet, no decoration."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    folded = folded.casefold().translate(_LEET)
    folded = _DECORATION.sub(" ", folded)
    return "".join(_WORD.findall(folded))


def handle_variants(name: str, aliases: Iterable[str] = ()) -> set[str]:
    """Every spelling of the user's name we are willing to recognise.

    Covers the whole nickname, each word inside it (so `[EZ] noodle king` answers to `noodle`),
    and the alias list from the panel. Fragments shorter than `MIN_HANDLE` are dropped so a
    two-letter name does not match half the words in chat.
    """
    variants: set[str] = set()
    for candidate in (name, *aliases):
        if not candidate or not candidate.strip():
            continue
        whole = normalize_handle(candidate)
        if len(whole) >= MIN_HANDLE:
            variants.add(whole)
        for word in _WORD.findall(_DECORATION.sub(" ", candidate.casefold().translate(_LEET))):
            if len(word) >= MIN_HANDLE:
                variants.add(word)
    return variants


def is_same_player(sender: str, name: str, aliases: Iterable[str] = ()) -> bool:
    """True when `sender` is the user, allowing for decoration around the nickname."""
    if not name and not list(aliases):
        return False
    sender_handle = normalize_handle(_CLAN_TAG.sub("", sender))
    if not sender_handle:
        return False
    for candidate in (name, *aliases):
        if candidate and normalize_handle(_CLAN_TAG.sub("", candidate)) == sender_handle:
            return True
    return False


def detect_name_from_line(line: str, known: str = "") -> str | None:
    """Pull the user's name out of a console line, or None if the line says nothing about it."""
    body = TIMESTAMP.sub("", line.strip()).strip()
    if not body:
        return None
    echo = _CVAR_ECHO.match(body)
    if echo:
        name = (echo.group("quoted") or echo.group("bare") or "").strip()
        return name or None
    command = _NAME_COMMAND.match(body)
    if command:
        return command.group("name").strip() or None
    rename = _RENAME.match(body)
    if rename and known and normalize_handle(rename.group("old")) == normalize_handle(known):
        return rename.group("new").strip() or None
    return None


def _is_drawn_out(word: str, variant: str) -> bool:
    """`noodleee` is still `noodle`; `noodles` is a different word."""
    if len(word) <= len(variant) or not word.startswith(variant):
        return False
    return set(word[len(variant) :]) == {variant[-1]}


def addressed_to(
    text: str,
    name: str,
    aliases: Iterable[str] = (),
    replying_to_bot: bool = False,
) -> Mention:
    """Decide whether `text` is talking to the user.

    `replying_to_bot` should be set when the bot spoke a moment ago, which is what makes a bare
    "you" or "??" count as directed at it.
    """
    stripped = text.strip()
    if not stripped:
        return Mention(False)

    variants = handle_variants(name, aliases)
    if variants:
        # `name: text`, `name, text`, `@name ...` - an explicit address, strongest signal.
        lead = re.match(r"^\s*@?\s*(?P<head>[^,:]{1,32})\s*[,:]\s*\S", stripped)
        if lead and normalize_handle(lead.group("head")) in variants:
            return Mention(True, "addressed by name")
        if stripped.startswith("@"):
            first = normalize_handle(stripped[1:].split()[0] if stripped[1:].split() else "")
            if first in variants:
                return Mention(True, "@mention")

        # Whole words only: `hey-noodle!` counts, `i love noodles` does not.
        words = _WORD.findall(_DECORATION.sub(" ", stripped.casefold().translate(_LEET)))
        for word in words:
            if word in variants or any(_is_drawn_out(word, variant) for variant in variants):
                return Mention(True, "name mentioned")

    if replying_to_bot and _SECOND_PERSON.search(stripped):
        return Mention(True, "replying to what you just said")

    return Mention(False)
