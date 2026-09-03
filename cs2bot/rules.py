"""Decide whether the bot should answer a given chat message.

Dead/alive is normally just context for the reply, not a filter: on a server where everyone sees
everything, the bot answers a corpse and a living player alike and only changes *how* it writes.

The optional `enforce_visibility` mode is for servers that split the audience, where a dead
player's chat reaches only other dead players and spectators. There, answering a `[DEAD]` line
while alive looks like cheating, and typing while dead is shouting into the void.
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
    if not config.dead_alive.enforce_visibility or dead_chat_is_global(config, player):
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

    # Being spoken to directly outranks the trigger-word filter.
    if message.addressed_to_me and config.behavior.always_reply_when_addressed:
        reason = visibility_reason(config, message, local_state, player)
        return (False, reason) if reason else (True, message.mention_reason or "addressed to you")

    if config.behavior.only_reply_when_addressed and not message.addressed_to_me:
        return False, "nobody is talking to you"

    triggers = [t for t in config.behavior.trigger_words if t.strip()]
    if triggers:
        lowered = message.text.casefold()
        if not any(trigger.casefold() in lowered for trigger in triggers):
            return False, "no trigger word matched"

    reason = visibility_reason(config, message, local_state, player)
    if reason:
        return False, reason

    return True, "ok"
