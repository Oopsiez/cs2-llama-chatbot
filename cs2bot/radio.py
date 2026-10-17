"""Telling radio commands apart from people talking.

CS2's radio wheel plays a canned voice line through the speakers (so the voice listener hears
it word for word) and prints it in the console log tagged `(RADIO)`. Neither is a teammate
talking to the bot, so both are recognised and left unanswered.
"""

from __future__ import annotations

import re

# Every line the CS2 radio and ping wheels can say, as the game voices/prints them.
RADIO_LINES: frozenset[str] = frozenset(
    phrase.casefold()
    for phrase in (
        # Standard radio
        "Go go go",
        "Go",
        "Fall back",
        "Team fall back",
        "Stick together",
        "Stick together team",
        "Hold this position",
        "Hold position",
        "Get in position",
        "Get in position and wait for my go",
        "Storm the front",
        "Report in",
        "Report in team",
        "Follow me",
        "Cover me",
        "You take the point",
        "Take the point",
        "Regroup",
        "Regroup team",
        "Taking fire, need assistance",
        "Taking fire",
        "Need assistance",
        # Report radio
        "Affirmative",
        "Roger that",
        "Roger",
        "Negative",
        "Enemy spotted",
        "Need backup",
        "Sector clear",
        "I'm in position",
        "In position",
        "Reporting in",
        "She's gonna blow",
        "Get out of there, it's gonna blow",
        "Enemy down",
        "Bomb has been planted",
        "Bomb planted",
        "Defusing",
        "Defusing the bomb",
        "Cover me, I'm defusing",
        # CS2 ping / quick wheel
        "Cheer",
        "Nice",
        "Nice shot",
        "Well played",
        "Compliment",
        "Thanks",
        "Thank you",
        "Sorry",
        "My bad",
        "Need a drop",
        "Can someone drop me a weapon",
        "Drop me a weapon",
        "I need a drop",
        "Need drop",
        "Rush",
        "Rush B",
        "Rush A",
        "Enemy here",
        "Danger",
        "Watch out",
        "Spotted an enemy",
        "Going A",
        "Going B",
        "Going mid",
        "Defending A",
        "Defending B",
        "Bomb here",
        "Bomb is here",
        "Dropping weapon",
        "Grenades here",
        "I need help",
        "Help",
    )
)

_TAG = re.compile(r"[\(\[]\s*radio\s*[\)\]]", re.IGNORECASE)
_LOCATION = re.compile(r"\s*[\(\[][^)\]]{1,30}[\)\]]\s*$")  # "Enemy spotted (Catwalk)"


def _normalise(text: str) -> str:
    text = _LOCATION.sub("", text)
    text = re.sub(r"[^a-z' ]+", " ", text.casefold())
    return " ".join(text.split())


def is_radio_tagged(line: str) -> bool:
    """Whether a console line is marked as a radio command rather than typed chat."""
    return bool(_TAG.search(line))


def is_radio(text: str) -> bool:
    """Whether a chat/voice text is one of the game's canned radio lines, not a person talking."""
    said = _normalise(text)
    if not said:
        return False
    if said in RADIO_LINES:
        return True
    # Transcripts come back as "Affirmative." or "Enemy spotted, sector clear" when two fire
    # close together: every chunk being a radio line still makes it radio.
    parts = [p for p in re.split(r"[,.!?;]+", text) if p.strip()]
    return len(parts) > 1 and all(_normalise(p) in RADIO_LINES for p in parts)
