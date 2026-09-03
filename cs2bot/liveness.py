"""Track who is dead this round.

CS2 tags a dead player's chat with `[DEAD]` (or `*DEAD*`, depending on the server), so the
first thing a corpse says gives their state away. Living players are not tagged at all, which
means an untagged line from someone we have not seen yet tells us nothing on its own - but once
somebody has been seen dead, everything they say until the round resets is also from the grave.
That memory is what lets the bot answer a dead player differently from a living one even when
the individual line carries no marker.
"""

from __future__ import annotations

from .models import ChatChannel, ChatMessage, LifeState

# Round phases that mean a fresh round: everyone is breathing again.
_RESET_PHASES = {"freezetime", "warmup"}


class DeathBoard:
    """Per-round memory of each player's life state, learned from chat markers."""

    def __init__(self) -> None:
        self._states: dict[str, LifeState] = {}
        self._phase = ""

    def note_phase(self, phase: str) -> None:
        """Feed the GSI round phase in; a new round wipes the board."""
        phase = phase.strip().casefold()
        if phase == self._phase:
            return
        self._phase = phase
        if phase in _RESET_PHASES:
            self.reset()

    def reset(self) -> None:
        self._states.clear()

    def state_of(self, sender: str) -> LifeState:
        return self._states.get(sender.casefold(), LifeState.UNKNOWN)

    @property
    def dead_players(self) -> list[str]:
        return sorted(name for name, state in self._states.items() if state is LifeState.DEAD)

    def observe(self, message: ChatMessage) -> ChatMessage:
        """Record what the line says about the sender, and fill in what it does not."""
        key = message.sender.casefold()
        if not key:
            return message

        if message.channel is ChatChannel.SPEC:
            # Spectators are not playing; do not let that leak into the dead roster.
            return message

        if message.sender_state is not LifeState.UNKNOWN:
            self._states[key] = message.sender_state
            return message

        remembered = self._states.get(key, LifeState.UNKNOWN)
        if remembered is LifeState.UNKNOWN:
            return message
        return message.model_copy(update={"sender_state": remembered})
