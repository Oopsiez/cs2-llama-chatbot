"""The bot itself: tail the log, decide, generate, deliver."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import replace
from typing import Any

from .config import AppConfig, load_config, save_config
from .echo import EchoGuard
from .events import EventBus
from .gamestate import GameStateStore
from .humanize import humanize, sampling_for
from .identity import addressed_to, detect_name_from_line
from .liveness import DeathBoard
from .llm import LLMBackend, LLMError, SamplingParams, build_backend
from .logtail import LogTailer
from .models import BotReply, ChatChannel, ChatMessage, LifeState
from .novelty import is_repetitive
from .output import ChatSender, build_sender
from .parser import parse_chat_line
from .persona import build_reveal_turns, build_turns
from .rules import should_reply
from .snitch import announcement, is_request, where

POLL_INTERVAL = 0.25
# Reading the message and deciding what to say, before any typing time.
THINK_SECONDS = 0.8
# How long after the bot speaks a bare "you" still counts as a reply to it.
REPLY_WINDOW_SECONDS = 25.0


class Engine:
    def __init__(self, config: AppConfig | None = None, seed: int | None = None) -> None:
        self.config = config or load_config()
        self.bus = EventBus()
        self.game_state = GameStateStore()
        self.deaths = DeathBoard()
        self.echo = EchoGuard()
        self.history: list[ChatMessage] = []
        # Monotonic clocks start at boot, so a plain 0.0 would read as "just replied" on a
        # freshly started machine and hold the first reply back for a whole cooldown.
        self.last_reply_at = float("-inf")
        self.last_spoke_at = 0.0
        self.last_announce_at = time.monotonic()
        self._last_seen_state = LifeState.UNKNOWN
        self._revealed = False
        self.detected_name: str = ""
        self._detected_from: str = "console log"
        self.recent_replies: list[str] = []
        self.last_generation_repeated = False
        self.last_error: str = ""
        self.llm_status: str = "not checked"
        self._backend: LLMBackend | None = None
        self._sender: ChatSender | None = None
        self._tailer: LogTailer | None = None
        self._task: asyncio.Task[None] | None = None
        # Every roll the bot makes - reply probability, typos - comes from here, so passing a
        # seed makes a run reproducible.
        self._random = random.Random(seed)

    # ---- identity ---------------------------------------------------------------

    @property
    def own_name(self) -> str:
        """The user's in-game name: panel setting first, then GSI, then the console log."""
        configured = self.config.game.own_name.strip()
        if configured:
            return configured
        if not self.config.game.auto_detect_name:
            return ""
        return self.game_state.player.name or self.detected_name

    @property
    def name_source(self) -> str:
        if self.config.game.own_name.strip():
            return "set in panel"
        if not self.config.game.auto_detect_name:
            return "auto-detect off"
        if self.game_state.player.name:
            return "game state integration"
        if self.detected_name:
            return self._detected_from
        return "unknown"

    def _note_identity(self, line: str) -> None:
        """Watch non-chat console lines for the user's name."""
        if not self.config.game.auto_detect_name:
            return
        found = detect_name_from_line(line, self.own_name)
        if not found or found == self.detected_name:
            return
        self._learn_name(found, "console log")

    def _learn_name(self, name: str, source: str) -> None:
        if not name or name == self.detected_name:
            return
        self.detected_name = name
        self._detected_from = source
        self.bus.publish("identity", {"name": self.own_name, "source": self.name_source})

    def flag_own_echo(self, message: ChatMessage) -> ChatMessage:
        """Mark a line the bot itself just sent, which CS2 echoes back into the console log.

        Without this the bot answers itself - and then answers *that* - whenever its name has not
        been resolved, which is the usual case in team chat before GSI connects.
        """
        if message.is_self or not self.echo.is_echo(message.text):
            return message
        if not self.own_name and self.config.game.auto_detect_name:
            self._learn_name(message.sender, "your own reply in chat")
        return message.model_copy(
            update={"is_self": True, "addressed_to_me": False, "mention_reason": ""}
        )

    def annotate(self, message: ChatMessage) -> ChatMessage:
        """Mark whether the sender is the user, and whether they are talking to the user."""
        if message.is_self:
            return message
        mention = addressed_to(
            message.text,
            self.own_name,
            self.config.game.name_aliases,
            replying_to_bot=(time.time() - self.last_spoke_at) < REPLY_WINDOW_SECONDS,
        )
        return message.model_copy(
            update={"addressed_to_me": mention.addressed, "mention_reason": mention.reason}
        )

    # ---- wiring -----------------------------------------------------------------

    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = build_backend(self.config.llm)
        return self._backend

    @property
    def sender(self) -> ChatSender:
        if self._sender is None:
            self._sender = build_sender(self.config)
        return self._sender

    async def apply_config(self, config: AppConfig, persist: bool = True) -> None:
        """Swap in new settings, rebuilding anything whose inputs changed."""
        old = self.config
        self.config = config
        if config.llm != old.llm:
            if self._backend is not None:
                await self._backend.aclose()
            self._backend = None
            self.llm_status = "not checked"
        if config.game != old.game or config.behavior != old.behavior:
            self._sender = None
        if config.game.console_log_path != old.game.console_log_path:
            if self._tailer is not None:
                self._tailer.close()
            self._tailer = None
        if persist:
            save_config(config)
        self.bus.publish("config", config.model_dump(mode="json"))

    async def check_llm(self) -> str:
        try:
            self.llm_status = await self.backend.health()
        except LLMError as exc:
            self.llm_status = f"error: {exc}"
        self.bus.publish("status", self.status())
        return self.llm_status

    # ---- lifecycle --------------------------------------------------------------

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="cs2bot-loop")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._tailer is not None:
            self._tailer.close()
            self._tailer = None

    async def _run(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep the loop alive across transient failures
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.bus.publish("error", {"message": self.last_error})
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self) -> None:
        path = self.config.game.console_log_path
        if not path:
            return
        if self._tailer is None:
            self._tailer = LogTailer(path)
        for line in self._tailer.read_lines():
            message = parse_chat_line(line, self.own_name, self.config.game.name_aliases)
            if message is None:
                self._note_identity(line)
                continue
            await self.handle_message(message)
        await self.maybe_announce()
        await self.maybe_reveal()

    # ---- message handling -------------------------------------------------------

    async def handle_message(self, message: ChatMessage) -> BotReply | None:
        message = self.annotate(self.flag_own_echo(self.track_state(message)))
        self.history.append(message)
        del self.history[:-50]
        self.bus.publish("chat", message.model_dump(mode="json"))

        if not self.config.enabled:
            return None

        local_state = self.game_state.local_state(self.config.dead_alive.assume_alive_without_gsi)
        allowed, reason = should_reply(self.config, message, local_state, self.game_state.player)
        if not allowed:
            self.bus.publish("skipped", {"message": message.model_dump(mode="json"), "reason": reason})
            return None

        # Being spoken to directly - or asked where you are - gets an answer regardless of pacing.
        asked_where = (
            self.config.snitch.enabled
            and self.config.snitch.answer_when_asked
            and is_request(message.text, self.config.snitch.request_phrases)
        )
        urgent = asked_where or (
            message.addressed_to_me and self.config.behavior.always_reply_when_addressed
        )

        now = time.monotonic()
        if not urgent and now - self.last_reply_at < self.config.behavior.cooldown_seconds:
            self.bus.publish(
                "skipped",
                {"message": message.model_dump(mode="json"), "reason": "cooling down"},
            )
            return None
        if not urgent and self._random.random() > self.config.behavior.reply_probability:
            self.bus.publish(
                "skipped",
                {"message": message.model_dump(mode="json"), "reason": "reply probability roll failed"},
            )
            return None

        self.last_reply_at = now
        started = time.perf_counter()
        try:
            text = await self.generate_reply(message, local_state)
        except LLMError as exc:
            self.last_error = str(exc)
            self.bus.publish("error", {"message": str(exc)})
            return None

        if not text:
            reason = (
                "kept repeating itself"
                if self.last_generation_repeated
                else "model returned nothing"
            )
            self.bus.publish(
                "skipped", {"message": message.model_dump(mode="json"), "reason": reason}
            )
            return None

        self._remember_reply(text)
        # Remember it *before* it is sent: the log echo can arrive the instant CS2 prints it.
        self.echo.remember(text)
        await self._pause_before_sending(text, elapsed=time.perf_counter() - started)

        delivered, detail = await self.sender.send(text, team_only=message.channel is ChatChannel.TEAM)
        reply = BotReply(
            in_reply_to=message,
            text=text,
            delivered=delivered,
            reason=detail,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        self.last_spoke_at = time.time()
        own_message = message.model_copy(
            update={
                "sender": self.own_name or "me",
                "text": text,
                "is_self": True,
                "sender_state": local_state,
            }
        )
        self.history.append(own_message)
        self.bus.publish("reply", reply.model_dump(mode="json"))
        return reply

    # ---- snitching ---------------------------------------------------------------

    async def maybe_announce(self) -> None:
        """Drop the player's own position into chat on a timer, or when they die.

        Unlike a reply this is not triggered by anybody typing, so it runs off the poll loop.
        """
        settings = self.config.snitch
        state = self.game_state.local_state(self.config.dead_alive.assume_alive_without_gsi)
        just_died = state is LifeState.DEAD and self._last_seen_state is LifeState.ALIVE
        self._last_seen_state = state
        if not (self.config.enabled and settings.enabled):
            return

        now = time.monotonic()
        due = (
            settings.announce_interval > 0
            and now - self.last_announce_at >= settings.announce_interval
        )
        if not (due or (settings.announce_on_death and just_died)):
            return

        text = announcement(settings, self.game_state.player, self.config.callouts)
        if not text:
            return
        self.last_announce_at = now
        self._remember_reply(text)
        self.echo.remember(text)
        delivered, detail = await self.sender.send(text, team_only=settings.channel == "team")
        self.last_spoke_at = time.time()
        self.bus.publish(
            "snitch", {"text": text, "delivered": delivered, "reason": detail}
        )

    async def maybe_reveal(self) -> None:
        """Own up on the end-of-match scoreboard, once.

        `gameover` keeps arriving for as long as the scoreboard is up, and the next match resets
        the phase, which is what re-arms this.
        """
        settings = self.config.reveal
        phase = self.game_state.player.map_phase
        over = phase == "gameover"
        if not over:
            self._revealed = False
            return
        if self._revealed or not (self.config.enabled and settings.enabled):
            return

        text = await self._reveal_text()
        if not text:
            return
        self._revealed = True
        self._remember_reply(text)
        self.echo.remember(text)
        delivered, detail = await self.sender.send(text, team_only=settings.channel == "team")
        self.last_spoke_at = time.time()
        self.bus.publish("reveal", {"text": text, "delivered": delivered, "reason": detail})

    async def _reveal_text(self) -> str:
        """The confession itself, written in character unless a fixed line was configured."""
        settings = self.config.reveal
        written = settings.message.strip()
        if settings.mode == "character":
            try:
                generated = await self.backend.generate(
                    build_reveal_turns(self.config), self._sampling_params()
                )
            except LLMError as exc:
                # The match is over either way; the canned line is better than silence.
                self.last_error = str(exc)
                generated = ""
            written = humanize(
                generated,
                literacy=self.config.behavior.literacy,
                max_chars=max(40, self.config.persona.max_reply_chars - len(settings.link) - 1),
                seed=self._random.randrange(2**32),
            ) or written
        link = settings.link.strip()
        if link and link not in written:
            written = f"{written} {link}".strip()
        return written

    def track_state(self, message: ChatMessage) -> ChatMessage:
        """Learn the sender's life state from `[DEAD]`, and remember it for the round."""
        if not self.config.dead_alive.track_players:
            return message
        self.deaths.note_phase(self.game_state.player.round_phase)
        return self.deaths.observe(message)

    async def generate_reply(self, message: ChatMessage, local_state: LifeState) -> str:
        """Generate a reply, retrying while it echoes something the bot recently said."""
        behavior = self.config.behavior
        turns = build_turns(
            self.config,
            self.game_state.player,
            local_state,
            message,
            self.history[:-1],
            self.own_name,
            self.recent_replies,
        )
        attempts = 1 + (behavior.repeat_retries if behavior.avoid_repeats else 0)
        self.last_generation_repeated = False
        text = ""
        for attempt in range(attempts):
            params = self._sampling_params()
            if attempt:
                # Nudge it out of the groove it just fell into.
                params = replace(
                    params, temperature=min(1.6, params.temperature + 0.15 * attempt)
                )
            raw = await self.backend.generate(turns, params)
            text = humanize(
                raw,
                literacy=behavior.literacy,
                max_chars=self.config.persona.max_reply_chars,
                seed=self._random.randrange(2**32),
            )
            if not behavior.avoid_repeats or not text:
                return text
            echoed = is_repetitive(text, self.recent_replies, behavior.repeat_similarity)
            if echoed is None:
                return text
            self.bus.publish(
                "repeat",
                {"text": text, "echoed": echoed, "attempt": attempt + 1, "attempts": attempts},
            )
        self.last_generation_repeated = True
        return ""

    def reply_delay_for(self, text: str) -> float:
        """How long the bot should sit on a reply before it appears in chat."""
        behavior = self.config.behavior
        if behavior.humanized_typing:
            # Read the message, think, then type it out at the configured speed.
            return THINK_SECONDS + behavior.typing_delay_per_char * len(text)
        return max(0.0, behavior.reply_delay)

    async def _pause_before_sending(self, text: str, elapsed: float) -> None:
        remaining = self.reply_delay_for(text) - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    def _remember_reply(self, text: str) -> None:
        self.recent_replies.append(text)
        keep = max(0, self.config.behavior.repeat_memory)
        del self.recent_replies[: max(0, len(self.recent_replies) - keep)]

    def _sampling_params(self) -> SamplingParams:
        generation = self.config.generation
        if generation.auto_from_intelligence:
            auto = sampling_for(self.config.behavior.literacy, self.config.behavior.intelligence)
            return SamplingParams(
                temperature=float(auto["temperature"]),
                top_p=float(auto["top_p"]),
                top_k=int(auto["top_k"]),
                repeat_penalty=float(auto["repeat_penalty"]),
                max_tokens=int(auto["max_tokens"]),
            )
        return SamplingParams(
            temperature=generation.temperature,
            top_p=generation.top_p,
            top_k=generation.top_k,
            repeat_penalty=generation.repeat_penalty,
            max_tokens=generation.max_tokens,
        )

    # ---- introspection ----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        player = self.game_state.player
        return {
            "enabled": self.config.enabled,
            "running": self._task is not None and not self._task.done(),
            "llm_backend": self.config.llm.backend,
            "llm_status": self.llm_status,
            "sender": self.sender.describe(),
            "log_path": self.config.game.console_log_path,
            "log_attached": bool(self._tailer and self._tailer.is_open),
            "own_name": self.own_name,
            "name_source": self.name_source,
            "local_state": self.game_state.local_state(
                self.config.dead_alive.assume_alive_without_gsi
            ).value,
            "dead_players": self.deaths.dead_players,
            "callout": where(player, self.config.callouts),
            "has_position": player.position is not None,
            "gsi_connected": not player.is_stale,
            "player": player.model_dump(mode="json"),
            "last_error": self.last_error,
        }
