"""Windows sender: write the reply into a .cfg and press the key bound to `exec message.cfg`.

This is the same trick the original project used and it is why nothing has to hook into the
game process: CS2 executes the config on a keypress and says the line itself.
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import create_unicode_buffer
from pathlib import Path

from . import keyboard
from .base import ChatSender, chunk_message, sanitize_for_console

CS2_WINDOW_TITLE = "Counter-Strike 2"


def foreground_window_title() -> str:
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    except AttributeError:
        return ""
    handle = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(handle)
    buffer = create_unicode_buffer(length + 2)
    user32.GetWindowTextW(handle, buffer, length + 2)
    return buffer.value


class WindowsCfgSender(ChatSender):
    name = "windows"

    def __init__(
        self,
        cfg_dir: str,
        cfg_name: str = "message.cfg",
        bind_key: str = "p",
        char_limit: int = 221,
        send_delay: float = 0.6,
        require_focus: bool = True,
        typing_delay_per_char: float = 0.0,
    ) -> None:
        self.cfg_path = Path(cfg_dir) / cfg_name
        self.bind_key = bind_key
        self.char_limit = char_limit
        self.send_delay = send_delay
        self.require_focus = require_focus
        self.typing_delay_per_char = typing_delay_per_char

    def describe(self) -> str:
        return f"writes {self.cfg_path} and presses '{self.bind_key}'"

    def _press_key(self) -> None:
        keyboard.press(self.bind_key)

    async def send(self, text: str, team_only: bool = False) -> tuple[bool, str]:
        command = "say_team" if team_only else "say"
        chunks = chunk_message(sanitize_for_console(text), self.char_limit)
        if not chunks:
            return False, "empty message"

        try:
            self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"cannot write {self.cfg_path}: {exc}"

        for chunk in chunks:
            if self.require_focus and foreground_window_title() != CS2_WINDOW_TITLE:
                return False, "CS2 is not the focused window"
            try:
                self.cfg_path.write_text(f'{command} "{chunk}"', encoding="utf-8")
            except OSError as exc:
                return False, f"cannot write {self.cfg_path}: {exc}"
            if self.typing_delay_per_char:
                await asyncio.sleep(self.typing_delay_per_char * len(chunk))
            try:
                await asyncio.to_thread(self._press_key)
            except keyboard.KeyPressError as exc:
                return False, str(exc)
            except Exception as exc:  # pragma: no cover - depends on the desktop session
                return False, f"keypress failed: {exc}"
            await asyncio.sleep(self.send_delay)

        return True, f"sent {len(chunks)} chunk(s) via {command}"
