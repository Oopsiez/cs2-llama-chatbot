"""Domain types shared by the parser, game state, responder and web layers."""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field

from .callouts import Position


class ChatChannel(str, Enum):
    ALL = "all"
    TEAM = "team"
    SPEC = "spec"
    UNKNOWN = "unknown"


class MessageSource(str, Enum):
    """Where a message reached the bot.

    Voice is not a third chat channel - it is a different way of hearing one. It matters because
    voice comms are team-only and a transcript is a guess, so replies to it are written and
    routed differently from replies to something somebody typed.
    """

    CHAT = "chat"
    VOICE = "voice"


class Team(str, Enum):
    T = "T"
    CT = "CT"
    SPECTATOR = "SPEC"
    UNKNOWN = "UNKNOWN"


class LifeState(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    UNKNOWN = "unknown"


class ChatMessage(BaseModel):
    """Something said to the bot: a chat line from the console log, or transcribed speech."""

    raw: str
    sender: str
    text: str
    channel: ChatChannel = ChatChannel.UNKNOWN
    source: MessageSource = MessageSource.CHAT
    sender_state: LifeState = LifeState.UNKNOWN
    sender_team: Team = Team.UNKNOWN
    is_self: bool = False
    addressed_to_me: bool = False
    mention_reason: str = ""
    timestamp: float = Field(default_factory=time.time)

    @property
    def is_voice(self) -> bool:
        return self.source is MessageSource.VOICE


class LocalPlayer(BaseModel):
    """What we know about the player running the bot, sourced from Game State Integration."""

    name: str = ""
    steam_id: str = ""
    team: Team = Team.UNKNOWN
    state: LifeState = LifeState.UNKNOWN
    health: int | None = None
    round_phase: str = ""
    map_phase: str = ""
    map_name: str = ""
    mode: str = ""
    position: Position | None = None
    active_weapon: str = ""
    bomb: str = ""  # planted | carried | dropped | defused | exploded
    round_number: int = 0
    updated_at: float = 0.0

    @property
    def is_warmup(self) -> bool:
        return self.map_phase == "warmup"

    @property
    def is_stale(self) -> bool:
        """GSI stops posting when CS2 is closed; treat old data as unknown."""
        return self.updated_at == 0.0 or (time.time() - self.updated_at) > 30.0


class BotReply(BaseModel):
    """A reply the bot produced, along with what happened to it."""

    in_reply_to: ChatMessage
    text: str
    delivered: bool
    reason: str = ""
    latency_ms: int = 0
    timestamp: float = Field(default_factory=time.time)


class SkippedMessage(BaseModel):
    message: ChatMessage
    reason: str
    timestamp: float = Field(default_factory=time.time)
