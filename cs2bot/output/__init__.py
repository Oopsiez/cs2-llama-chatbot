"""Chat delivery adapters."""

from __future__ import annotations

import platform

from ..config import AppConfig
from .base import ChatSender, chunk_message, sanitize_for_console
from .dry_run import DryRunSender
from .windows_cfg import WindowsCfgSender


def build_sender(config: AppConfig) -> ChatSender:
    backend = config.game.output_backend
    if backend == "auto":
        backend = "windows" if platform.system() == "Windows" else "dry_run"
    if backend == "windows":
        if not config.game.cfg_dir:
            return DryRunSender()
        return WindowsCfgSender(
            cfg_dir=config.game.cfg_dir,
            cfg_name=config.game.exec_cfg_name,
            bind_key=config.game.bind_key,
            char_limit=config.game.chat_char_limit,
            send_delay=config.game.chat_send_delay,
            require_focus=config.game.require_focus,
            typing_delay_per_char=(
                config.behavior.typing_delay_per_char if config.behavior.typing_simulation else 0.0
            ),
        )
    return DryRunSender()


__all__ = [
    "ChatSender",
    "DryRunSender",
    "WindowsCfgSender",
    "build_sender",
    "chunk_message",
    "sanitize_for_console",
]
