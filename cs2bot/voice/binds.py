"""Reading CS2's push-to-talk key out of its own key config.

CS2 keeps a player's bindings in Steam's userdata, one file per account:
`Steam/userdata/<account>/730/local/cfg/cs2_user_keys.vcfg`, a KeyValues block of
`"key" "command"` lines. The voice key is whatever is bound to `+voicerecord`. Older autoexec
style `bind "k" "+voicerecord"` lines in the game's cfg folder are honoured too.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

VOICE_COMMAND = "+voicerecord"

_VCFG_LINE = re.compile(r'^\s*"([^"]+)"\s+"([^"]*)"', re.MULTILINE)
_BIND_LINE = re.compile(r'^\s*bind\s+"?([^"\s]+)"?\s+"?\+voicerecord"?', re.MULTILINE | re.IGNORECASE)


def steam_roots() -> list[Path]:
    """Where Steam itself (not a game library) may live - userdata sits under it."""
    roots: list[Path] = []
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:  # type: ignore[attr-defined]
                roots.append(Path(str(winreg.QueryValueEx(key, "SteamPath")[0])))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - registry key missing
            pass
        for drive in ("C:", "D:", "E:"):
            roots += [Path(f"{drive}/Program Files (x86)/Steam"), Path(f"{drive}/Steam")]
    else:
        home = Path.home()
        roots += [home / ".steam/steam", home / ".local/share/Steam"]
    if extra := os.environ.get("CS2BOT_STEAM_ROOT"):
        roots.insert(0, Path(extra))
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return seen


def key_files(roots: list[Path] | None = None) -> list[Path]:
    """Every account's CS2 key config, newest first - the one last played with wins."""
    files: list[Path] = []
    for root in roots if roots is not None else steam_roots():
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        files += userdata.glob("*/730/local/cfg/cs2_user_keys.vcfg")
    return sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)


def voice_key_in(text: str) -> str:
    """The key bound to `+voicerecord` in a vcfg or cfg text, or blank."""
    for key, command in _VCFG_LINE.findall(text):
        if command.strip().casefold() == VOICE_COMMAND:
            return key.strip().lower()
    match = _BIND_LINE.search(text)
    return match.group(1).lower() if match else ""


def detect_voice_key(cfg_dir: str = "", roots: list[Path] | None = None) -> tuple[str, str]:
    """(key, where it was found) for the push-to-talk bind, or ("", why not)."""
    for path in key_files(roots):
        try:
            key = voice_key_in(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if key:
            return key, str(path)
    if cfg_dir:
        for path in sorted(Path(cfg_dir).glob("*.cfg")):
            try:
                key = voice_key_in(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if key:
                return key, str(path)
    return "", "no +voicerecord bind found in Steam userdata - is CS2 installed on this PC?"
