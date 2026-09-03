"""Decide whether the bot should answer a given chat message.

The dead/alive part exists because CS2 splits the chat audience: a dead player's messages are
only rendered for other dead players and spectators. Two consequences drive the rules below.

1. While the bot is alive, a `*DEAD*` message is one it should not be able to read, so replying
   to it looks like cheating.
2. While the bot is dead, anything it types is invisible to living players, so answering them is
   shouting into the void.

Warmup, deathmatch and servers running `sv_deadtalk` merge the audiences again, which is what
`treat_warmup_as_global` / `dead_chat_is_global` are for.
"""

from __future__ import annotations

from .config import AppConfig
from .models import ChatMessage, LifeState, LocalPlayer


def dead_chat_is_global(config: AppConfig, player: LocalPlayer) -> bool:
    if config.dead_alive.dead_chat_is_global:
        return True
    return config.dead_alive.treat_warmup_as_global and player.is_warmup


def visibility_reason(
    config: AppConfig,
    message: ChatMessage,
    local_state: LifeState,
    player: LocalPlayer,
) -> str | None:
    """Return why the reply would not be seen, or None when it would be."""
    if not config.dead_alive.enabled or dead_chat_is_global(config, player):
        return None

    if local_state is LifeState.DEAD:
        if not config.dead_alive.reply_when_dead:
            return "bot is dead and replying while dead is disabled"
        if (
            message.sender_state is LifeState.ALIVE
            and not config.dead_alive.reply_to_alive_when_dead
        ):
            return f"{message.sender} is alive and cannot see dead chat"
        return None

    if (
        message.sender_state is LifeState.DEAD
        and not config.dead_alive.reply_to_dead_when_alive
    ):
        return f"{message.sender} is dead; a living bot should not see that message"
    return None


def should_reply(
    config: AppConfig,
    message: ChatMessage,
    local_state: LifeState,
    player: LocalPlayer,
) -> tuple[bool, str]:
    """`(allowed, reason)` - `reason` explains a refusal, or the trigger when allowed."""
    if message.is_self:
        return False, "own message"

    lowered_sender = message.sender.casefold()
    if any(lowered_sender == ignored.casefold() for ignored in config.behavior.ignore_players):
        return False, f"{message.sender} is on the ignore list"

    if message.channel not in config.behavior.reply_channels:
        return False, f"{message.channel.value} chat is disabled"

    triggers = [t for t in config.behavior.trigger_words if t.strip()]
    if triggers:
        lowered = message.text.casefold()
        if not any(trigger.casefold() in lowered for trigger in triggers):
            return False, "no trigger word matched"

    reason = visibility_reason(config, message, local_state, player)
    if reason:
        return False, reason

    return True, "ok"
