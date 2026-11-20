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
    score_ct: int = 0
    score_t: int = 0
    updated_at: float = 0.0

    @property
    def is_warmup(self) -> bool:
        return self.map_phase == "warmup"

    @property
    def rounds_to_win(self) -> int:
        """First to this many rounds takes the map: MR12 competitive/premier, MR8 wingman,
        casual's 15-round format. CS2 does not send it, so it follows the mode."""
        mode = self.mode.casefold()
        if mode in ("wingman", "scrimcomp2v2"):
            return 9
        if mode in ("casual", "deathmatch"):
            return 8
        return 13

    @property
    def match_situation(self) -> str:
        """Where the match stands, in words the model can use: just started, close, match point,
        or over. Empty without a scoreboard."""
        if not self.map_phase or self.is_warmup:
            return ""
        if self.map_phase == "gameover":
            return "the match is over"
        ours, theirs = (
            (self.score_ct, self.score_t) if self.team is Team.CT else (self.score_t, self.score_ct)
        )
        total = ours + theirs
        need = self.rounds_to_win
        on_a_side = self.team in (Team.CT, Team.T)
        score = f"{ours}-{theirs}" if on_a_side else f"CT {self.score_ct} - T {self.score_t}"
        if max(ours, theirs) == need - 1:
            who = "you are" if ours > theirs else "they are" if theirs > ours else "both teams are"
            return f"score {score}, match point - {who} one round from winning"
        if total <= 2:
            return f"score {score}, the match has just started"
        if max(ours, theirs) >= need - 3:
            return f"score {score}, the match is nearly over"
        if abs(ours - theirs) <= 2:
            return f"score {score}, it is close"
        return f"score {score}, {'you are ahead' if ours > theirs else 'you are behind'}"

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
