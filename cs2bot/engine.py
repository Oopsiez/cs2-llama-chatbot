"""The bot itself: tail the log, decide, generate, deliver."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from .config import AppConfig, load_config, save_config
from .events import EventBus
from .gamestate import GameStateStore
from .humanize import humanize, sampling_for_intelligence
from .llm import LLMBackend, LLMError, SamplingParams, build_backend
from .logtail import LogTailer
from .models import BotReply, ChatChannel, ChatMessage, LifeState
from .output import ChatSender, build_sender
from .parser import parse_chat_line
from .persona import build_turns
from .rules import should_reply

POLL_INTERVAL = 0.25


class Engine:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.bus = EventBus()
        self.game_state = GameStateStore()
        self.history: list[ChatMessage] = []
        self.last_reply_at = 0.0
        self.last_error: str = ""
        self.llm_status: str = "not checked"
        self._backend: LLMBackend | None = None
        self._sender: ChatSender | None = None
        self._tailer: LogTailer | None = None
        self._task: asyncio.Task[None] | None = None
        self._random = random.Random()

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
            message = parse_chat_line(line, self.config.game.own_name or self.game_state.player.name)
            if message is None:
                continue
            await self.handle_message(message)

    # ---- message handling -------------------------------------------------------

    async def handle_message(self, message: ChatMessage) -> BotReply | None:
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

        now = time.monotonic()
        if now - self.last_reply_at < self.config.behavior.cooldown_seconds:
            self.bus.publish(
                "skipped",
                {"message": message.model_dump(mode="json"), "reason": "cooling down"},
            )
            return None
        if self._random.random() > self.config.behavior.reply_probability:
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
            self.bus.publish(
                "skipped",
                {"message": message.model_dump(mode="json"), "reason": "model returned nothing"},
            )
            return None

        delivered, detail = await self.sender.send(text, team_only=message.channel is ChatChannel.TEAM)
        reply = BotReply(
            in_reply_to=message,
            text=text,
            delivered=delivered,
            reason=detail,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        own_message = message.model_copy(
            update={
                "sender": self.config.game.own_name or self.game_state.player.name or "me",
                "text": text,
                "is_self": True,
                "sender_state": local_state,
            }
        )
        self.history.append(own_message)
        self.bus.publish("reply", reply.model_dump(mode="json"))
        return reply

    async def generate_reply(self, message: ChatMessage, local_state: LifeState) -> str:
        params = self._sampling_params()
        turns = build_turns(self.config, self.game_state.player, local_state, message, self.history[:-1])
        raw = await self.backend.generate(turns, params)
        return humanize(
            raw,
            intelligence=self.config.behavior.intelligence,
            max_chars=self.config.persona.max_reply_chars,
        )

    def _sampling_params(self) -> SamplingParams:
        generation = self.config.generation
        if generation.auto_from_intelligence:
            auto = sampling_for_intelligence(self.config.behavior.intelligence)
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
            "local_state": self.game_state.local_state(
                self.config.dead_alive.assume_alive_without_gsi
            ).value,
            "gsi_connected": not player.is_stale,
            "player": player.model_dump(mode="json"),
            "last_error": self.last_error,
        }
