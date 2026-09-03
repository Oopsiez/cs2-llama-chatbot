"""Snitch mode: the bot gives away where *you* are.

Everything here comes from CS2's own Game State Integration, which only ever describes the local
player while you are playing - your position, your health, your weapon, the bomb. So the bot can
only snitch on you, which is the joke: it answers "where are you?" honestly, or volunteers your
position to all chat on a timer.

Position arrives as raw world coordinates, so it is only turned into a callout when you have
recorded one nearby (see `callouts.py`). With nothing recorded the bot still has plenty to give
away - health, weapon, bomb state - and simply says it does not know the callout.
"""

from __future__ import annotations

from .callouts import CalloutBook
from .config import SnitchSettings
from .models import LifeState, LocalPlayer

_BOMB_PHRASES = {
    "planted": "the bomb is down",
    "carried": "carrying the bomb",
    "dropped": "the bomb is dropped",
    "defusing": "someone is defusing",
    "defused": "the bomb is defused",
    "exploded": "the bomb went off",
}


def is_request(text: str, phrases: list[str]) -> bool:
    """Whether a chat line is somebody asking where the player is."""
    lowered = text.casefold()
    return any(phrase.strip() and phrase.strip().casefold() in lowered for phrase in phrases)


def where(player: LocalPlayer, book: CalloutBook) -> str:
    """The recorded callout the player is standing in, if any."""
    return book.resolve(player.map_name, player.position)


def facts(
    settings: SnitchSettings, player: LocalPlayer, book: CalloutBook, first_person: bool = False
) -> list[str]:
    """The things the bot is willing to give away, phrased for the prompt or for chat."""
    subject, has = ("i am", "i have") if first_person else ("you are", "you have")
    out: list[str] = []
    if settings.reveal_position:
        callout = where(player, book)
        if callout:
            out.append(f"{subject} at {callout}")
        elif player.position is not None and not first_person:
            out.append(
                f"your position is {player.position.x:.0f}, {player.position.y:.0f}, "
                f"{player.position.z:.0f}, which matches no recorded callout"
            )
    if settings.reveal_health and player.health is not None:
        out.append(f"{has} {player.health} hp")
    if settings.reveal_weapon and player.active_weapon:
        out.append(f"{subject} holding a {player.active_weapon}")
    if settings.reveal_bomb and player.bomb in _BOMB_PHRASES:
        out.append(_BOMB_PHRASES[player.bomb])
    return out


def prompt_note(
    settings: SnitchSettings, player: LocalPlayer, book: CalloutBook, asked: bool = False
) -> str | None:
    """The instruction that lets the model snitch in its own voice when the subject comes up."""
    if not settings.enabled:
        return None
    known = facts(settings, player, book)
    if not known:
        return None
    note = (
        "Snitch mode is on: you give away your own position and situation whenever it comes up, "
        "in character, and you never lie about it. Right now " + "; ".join(known) + "."
    )
    if asked:
        note += " Somebody just asked where you are, so tell them."
    return note


def announcement(settings: SnitchSettings, player: LocalPlayer, book: CalloutBook) -> str:
    """A plain, model-free line for timed and on-death snitching."""
    if player.state is LifeState.DEAD:
        callout = where(player, book) if settings.reveal_position else ""
        return f"i died at {callout}" if callout else "im dead"
    known = facts(settings, player, book, first_person=True)
    return ", ".join(known)
