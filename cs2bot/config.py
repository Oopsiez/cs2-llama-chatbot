"""Persisted configuration: game paths, LLM backend, persona, behaviour."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from platformdirs import user_config_dir
from pydantic import BaseModel, Field

from .models import ChatChannel

CONFIG_ENV_VAR = "CS2BOT_CONFIG"


class GameSettings(BaseModel):
    """Where CS2 lives and how we type into it."""

    console_log_path: str = ""
    cfg_dir: str = ""
    exec_cfg_name: str = "message.cfg"
    bind_key: str = "p"
    own_name: str = ""  # blank -> detect from GSI and the console log
    name_aliases: list[str] = Field(default_factory=list)
    auto_detect_name: bool = True
    chat_char_limit: int = 221
    chat_send_delay: float = 0.6
    require_focus: bool = True
    output_backend: str = "auto"  # auto | windows | dry_run


class LLMSettings(BaseModel):
    """Which Llama 3 runtime to talk to."""

    backend: str = "mock"  # llama_cpp | ollama | mock
    model_path: str = ""  # GGUF file for llama_cpp
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3:8b-instruct-q4_K_M"
    n_ctx: int = 4096
    n_gpu_layers: int = -1
    n_threads: int = 0  # 0 -> let the runtime decide
    request_timeout: float = 30.0


class GenerationSettings(BaseModel):
    """Raw sampling knobs. Ignored where `auto_from_intelligence` overrides them."""

    temperature: float = 0.8
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.15
    max_tokens: int = 80
    auto_from_intelligence: bool = True


class PersonaSettings(BaseModel):
    """Who the bot is."""

    name: str = "Cheeky Teammate"
    description: str = (
        "You are a Counter-Strike 2 player hanging out in the in-game chat. "
        "You are sarcastic but good-natured, and you never break character."
    )
    style_notes: str = "Keep it short, like real chat. No emoji spam. No asterisk roleplay actions."
    dead_notes: str = "You just died, so you are salty and backseat-gaming from the grave."
    banned_words: list[str] = Field(default_factory=list)
    max_reply_chars: int = 160


class BehaviorSettings(BaseModel):
    """When and how often the bot talks."""

    intelligence: int = 60  # 0..100, game IQ: how good the tactical thinking is
    literacy: int = 60  # 0..100, how well it writes: spelling, punctuation, sentence length
    unprompted_advice: bool = False  # volunteer pointers instead of only answering
    avoid_repeats: bool = True
    repeat_memory: int = 8  # how many of the bot's own lines to remember
    repeat_similarity: float = 0.75  # 0..1, above this a reply counts as a repeat
    repeat_retries: int = 2
    reply_probability: float = 1.0
    cooldown_seconds: float = 3.0
    reply_channels: list[ChatChannel] = Field(
        default_factory=lambda: [ChatChannel.ALL, ChatChannel.TEAM]
    )
    history_turns: int = 6
    trigger_words: list[str] = Field(default_factory=list)  # empty -> reply to everything
    ignore_players: list[str] = Field(default_factory=list)
    only_reply_when_addressed: bool = False
    always_reply_when_addressed: bool = True  # bypass triggers, cooldown and the probability roll
    reply_delay: float = 1.0  # seconds to wait before answering
    humanized_typing: bool = False  # ignore reply_delay, take as long as typing it would
    typing_simulation: bool = True
    typing_delay_per_char: float = 0.02


class DeadAliveSettings(BaseModel):
    """What the bot does with the `[DEAD]` marker CS2 puts on a corpse's chat.

    By default the marker is only *context*: the bot answers everyone, but it knows whether the
    sender is dead or alive (and whether it is dead itself) and writes accordingly. The
    visibility rules below exist for servers that split dead and living chat; they are off
    unless you turn them on.
    """

    adapt_replies: bool = True  # tell the model who is dead so it answers differently
    track_players: bool = True  # remember who is dead for the rest of the round
    enforce_visibility: bool = False  # skip messages the bot "should not" have seen
    reply_to_dead_when_alive: bool = True
    reply_to_alive_when_dead: bool = True
    reply_when_dead: bool = True
    treat_warmup_as_global: bool = True
    dead_chat_is_global: bool = True  # most servers show dead chat to everyone
    use_dead_persona: bool = True
    assume_alive_without_gsi: bool = True


class GSISettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3000
    auth_token: str = ""
    enabled: bool = True


class WebSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8420


class AppConfig(BaseModel):
    enabled: bool = False
    game: GameSettings = Field(default_factory=GameSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    persona: PersonaSettings = Field(default_factory=PersonaSettings)
    behavior: BehaviorSettings = Field(default_factory=BehaviorSettings)
    dead_alive: DeadAliveSettings = Field(default_factory=DeadAliveSettings)
    gsi: GSISettings = Field(default_factory=GSISettings)
    web: WebSettings = Field(default_factory=WebSettings)
    saved_personas: dict[str, PersonaSettings] = Field(default_factory=dict)


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override)
    return Path(user_config_dir("cs2bot", appauthor=False)) / "config.json"


def default_cs2_dir() -> Path | None:
    """Best-effort guess at `.../Counter-Strike Global Offensive/game/csgo`."""
    candidates: list[Path] = []
    if platform.system() == "Windows":
        for drive in ("C:", "D:", "E:"):
            candidates += [
                Path(f"{drive}/Program Files (x86)/Steam/steamapps/common"),
                Path(f"{drive}/SteamLibrary/steamapps/common"),
                Path(f"{drive}/Steam/steamapps/common"),
            ]
    else:
        home = Path.home()
        candidates += [
            home / ".steam/steam/steamapps/common",
            home / ".local/share/Steam/steamapps/common",
        ]
    for base in candidates:
        csgo = base / "Counter-Strike Global Offensive" / "game" / "csgo"
        if csgo.is_dir():
            return csgo
    return None


def with_detected_paths(config: AppConfig) -> AppConfig:
    """Fill in console.log / cfg paths when we can find the install ourselves."""
    if config.game.console_log_path and config.game.cfg_dir:
        return config
    csgo = default_cs2_dir()
    if csgo is None:
        return config
    if not config.game.console_log_path:
        config.game.console_log_path = str(csgo / "console.log")
    if not config.game.cfg_dir:
        config.game.cfg_dir = str(csgo / "cfg")
    return config


def load_config() -> AppConfig:
    path = config_path()
    if path.is_file():
        try:
            return AppConfig.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            backup = path.with_suffix(".invalid.json")
            try:
                path.replace(backup)
            except OSError:
                pass
    return with_detected_paths(AppConfig())


def save_config(config: AppConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config.model_dump(mode="json"), indent=2), encoding="utf-8")
    tmp.replace(path)
