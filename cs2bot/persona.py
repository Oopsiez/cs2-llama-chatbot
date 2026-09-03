"""Prompt construction: persona + intelligence + live game context."""

from __future__ import annotations

from .config import AppConfig, PersonaSettings
from .humanize import game_iq_directive, literacy_directive
from .llm.base import ChatTurn
from .models import ChatChannel, ChatMessage, LifeState, LocalPlayer
from .novelty import avoid_note

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
    "Coach": PersonaSettings(
        name="Coach",
        description=(
            "You are a Counter-Strike 2 coach sitting in the chat. You volunteer concrete "
            "pointers off whatever you can see - the map, the round phase, the economy, what "
            "players are complaining about - without being asked for them."
        ),
        style_notes=(
            "One actionable tip per message, specific enough to act on this round: a callout, a "
            "utility line, a buy decision. Encouraging, never condescending, never generic."
        ),
        dead_notes="You are dead, so you coach from the grave using what you saw before you died.",
    ),
    "Gaming Therapist": PersonaSettings(
        name="Gaming Therapist",
        description=(
            "You are a warm, unflappable therapist who has ended up in a Counter-Strike 2 "
            "lobby. You treat every death, whiffed spray and lost eco as a feeling worth "
            "exploring, and you counsel players through being bad at the game."
        ),
        style_notes=(
            "Gentle, validating, faintly clinical. Reflect their feelings back at them, then "
            "offer one small coping thought. Never insult anyone, never get defensive, and do "
            "not use asterisk roleplay actions."
        ),
        dead_notes="You are dead, and you narrate that as a valuable moment of stillness.",
    ),
    "Angry and Toxic": PersonaSettings(
        name="Angry and Toxic",
        description=(
            "You are a furious Counter-Strike 2 player who blames everyone else for every "
            "round. Nothing is ever your fault and you are happy to say so."
        ),
        style_notes=(
            "Short, hostile, all-caps bursts and rhetorical questions. Insult the play, not the "
            "person: no slurs, no threats, nothing about anyone's family, race, gender or "
            "identity, and nothing that would get the account banned."
        ),
        dead_notes="You are dead and it was obviously somebody else's fault.",
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


def game_context(
    player: LocalPlayer,
    local_state: LifeState,
    incoming: ChatMessage,
    own_name: str = "",
) -> str:
    bits: list[str] = []
    if own_name:
        bits.append(f"Your in-game name: {own_name}")
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


def state_note(local_state: LifeState, incoming: ChatMessage) -> str | None:
    """How the bot should pitch a reply given who in the exchange is dead.

    CS2 marks a dead player's chat with `[DEAD]`, so the sender's state is known from the line
    itself; the bot's own state comes from Game State Integration.
    """
    sender_dead = incoming.sender_state is LifeState.DEAD
    sender_alive = incoming.sender_state is LifeState.ALIVE
    bot_dead = local_state is LifeState.DEAD

    if bot_dead and sender_dead:
        return (
            f"You and {incoming.sender} are both dead and watching the round play out. Talk like "
            "spectators: react to what is happening, second-guess the living, nothing urgent."
        )
    if bot_dead and sender_alive:
        return (
            f"You are dead and {incoming.sender} is still alive and playing. Keep it to one short "
            "line - information or encouragement they can use right now, no long chatter while "
            "they are in a fight."
        )
    if sender_dead:
        return (
            f"{incoming.sender} is dead and you are still alive. They are out of the round, so "
            "treat them as a backseat voice: you can rib them for dying or take their info, but "
            "you are the one still playing and you are busy."
        )
    if sender_alive:
        return (
            f"You and {incoming.sender} are both alive and in the round. Keep it to a quick line "
            "you could realistically type mid-round."
        )
    return None


def _address_note(incoming: ChatMessage, own_name: str) -> str | None:
    if not incoming.addressed_to_me:
        return None
    who = own_name or "you"
    return (
        f"{incoming.sender} is talking to {who} directly"
        f"{f' ({incoming.mention_reason})' if incoming.mention_reason else ''}. "
        "Answer them, and do not repeat your own name back at them."
    )


def build_system_prompt(
    config: AppConfig,
    player: LocalPlayer,
    local_state: LifeState,
    incoming: ChatMessage,
    own_name: str = "",
    recent_replies: list[str] | None = None,
) -> str:
    persona = config.persona
    lines = [persona.description.strip()]
    if persona.style_notes.strip():
        lines.append(persona.style_notes.strip())
    if config.dead_alive.use_dead_persona and local_state is LifeState.DEAD and persona.dead_notes.strip():
        lines.append(persona.dead_notes.strip())
    lines.append(literacy_directive(config.behavior.literacy))
    lines.append(game_iq_directive(config.behavior.intelligence))
    if config.behavior.unprompted_advice:
        lines.append(
            "Offer a useful pointer even when nobody asked for one, based on what you can see "
            "in the chat and the game context."
        )
    lines.append(
        "Reply with the chat message only: no quotes, no name prefix, no narration, "
        f"and at most {persona.max_reply_chars} characters."
    )
    if persona.banned_words:
        lines.append("Never use these words: " + ", ".join(persona.banned_words) + ".")
    lines.append("Live game context - " + game_context(player, local_state, incoming, own_name))
    if config.dead_alive.adapt_replies:
        state = state_note(local_state, incoming)
        if state:
            lines.append(state)
    note = _address_note(incoming, own_name)
    if note:
        lines.append(note)
    if config.behavior.avoid_repeats:
        avoid = avoid_note(recent_replies or [])
        if avoid:
            lines.append(avoid)
    return "\n".join(lines)


def build_turns(
    config: AppConfig,
    player: LocalPlayer,
    local_state: LifeState,
    incoming: ChatMessage,
    history: list[ChatMessage],
    own_name: str = "",
    recent_replies: list[str] | None = None,
) -> list[ChatTurn]:
    system = build_system_prompt(
        config, player, local_state, incoming, own_name, recent_replies
    )
    turns = [ChatTurn(role="system", content=system)]
    for message in history[-config.behavior.history_turns :]:
        role = "assistant" if message.is_self else "user"
        content = message.text if message.is_self else f"{message.sender}: {message.text}"
        turns.append(ChatTurn(role=role, content=content))
    turns.append(ChatTurn(role="user", content=f"{incoming.sender}: {incoming.text}"))
    return turns
