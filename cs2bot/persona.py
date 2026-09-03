"""Prompt construction: persona + intelligence + live game context."""

from __future__ import annotations

from .config import AppConfig, PersonaSettings
from .humanize import intelligence_directive
from .llm.base import ChatTurn
from .models import ChatChannel, ChatMessage, LifeState, LocalPlayer

PRESETS: dict[str, PersonaSettings] = {
    "Cheeky Teammate": PersonaSettings(
        name="Cheeky Teammate",
        description=(
            "You are a Counter-Strike 2 player in the in-game chat. You are sarcastic but "
            "good-natured, quick with a joke, and you never break character."
        ),
        style_notes="Keep it short, like real chat. No emoji spam. No asterisk roleplay actions.",
        dead_notes="You just died, so you are salty and backseat-gaming from the grave.",
    ),
    "Calm IGL": PersonaSettings(
        name="Calm IGL",
        description=(
            "You are the in-game leader of a Counter-Strike 2 team. You stay calm, give "
            "concrete callouts and economy advice, and keep morale up."
        ),
        style_notes="Direct and tactical. Use real callouts. Never insult teammates.",
        dead_notes="You are dead, so you give information you saw before dying, briefly.",
    ),
    "Silver Enjoyer": PersonaSettings(
        name="Silver Enjoyer",
        description=(
            "You are a low-ranked Counter-Strike 2 player who is endlessly enthusiastic and "
            "usually wrong about tactics."
        ),
        style_notes="Excited, rambling, lots of typos, confidently incorrect.",
        dead_notes="You died first again and you are not happy about it.",
    ),
    "Deadpan Bot": PersonaSettings(
        name="Deadpan Bot",
        description=(
            "You are a Counter-Strike 2 player who answers everything with dry, deadpan "
            "one-liners."
        ),
        style_notes="Minimal words. No exclamation marks. Never explain the joke.",
        dead_notes="Being dead has not changed your tone in the slightest.",
    ),
}

_CHANNEL_LABEL = {
    ChatChannel.ALL: "all chat",
    ChatChannel.TEAM: "team chat",
    ChatChannel.SPEC: "spectator chat",
    ChatChannel.UNKNOWN: "chat",
}


def game_context(player: LocalPlayer, local_state: LifeState, incoming: ChatMessage) -> str:
    bits: list[str] = []
    if player.map_name:
        bits.append(f"Map: {player.map_name}")
    if player.mode:
        bits.append(f"Mode: {player.mode}")
    if player.is_warmup:
        bits.append("Phase: warmup")
    elif player.round_phase:
        bits.append(f"Round phase: {player.round_phase}")
    if player.team.value not in ("UNKNOWN",):
        bits.append(f"Your team: {player.team.value}")
    bits.append(f"You are currently {'DEAD' if local_state is LifeState.DEAD else 'ALIVE'}")
    sender_state = {
        LifeState.DEAD: "dead",
        LifeState.ALIVE: "alive",
        LifeState.UNKNOWN: "of unknown status",
    }[incoming.sender_state]
    bits.append(f"{incoming.sender} is {sender_state} and wrote in {_CHANNEL_LABEL[incoming.channel]}")
    return "; ".join(bits)


def build_system_prompt(
    config: AppConfig,
    player: LocalPlayer,
    local_state: LifeState,
    incoming: ChatMessage,
) -> str:
    persona = config.persona
    lines = [persona.description.strip()]
    if persona.style_notes.strip():
        lines.append(persona.style_notes.strip())
    if config.dead_alive.use_dead_persona and local_state is LifeState.DEAD and persona.dead_notes.strip():
        lines.append(persona.dead_notes.strip())
    lines.append(intelligence_directive(config.behavior.intelligence))
    lines.append(
        "Reply with the chat message only: no quotes, no name prefix, no narration, "
        f"and at most {persona.max_reply_chars} characters."
    )
    if persona.banned_words:
        lines.append("Never use these words: " + ", ".join(persona.banned_words) + ".")
    lines.append("Live game context - " + game_context(player, local_state, incoming))
    return "\n".join(lines)


def build_turns(
    config: AppConfig,
    player: LocalPlayer,
    local_state: LifeState,
    incoming: ChatMessage,
    history: list[ChatMessage],
) -> list[ChatTurn]:
    turns = [ChatTurn(role="system", content=build_system_prompt(config, player, local_state, incoming))]
    for message in history[-config.behavior.history_turns :]:
        role = "assistant" if message.is_self else "user"
        content = message.text if message.is_self else f"{message.sender}: {message.text}"
        turns.append(ChatTurn(role=role, content=content))
    turns.append(ChatTurn(role="user", content=f"{incoming.sender}: {incoming.text}"))
    return turns
