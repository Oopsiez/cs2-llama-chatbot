"""Press a key the way CS2 will notice, using only what ships with Python.

The game reads DirectInput, which ignores the virtual-key events `keybd_event` and most automation
libraries send; it only reacts to hardware scan codes. So this builds the `INPUT` structures itself
and hands them to `SendInput` with `KEYEVENTF_SCANCODE`.
"""

from __future__ import annotations

import ctypes
import sys

# Spelled out rather than taken from `ctypes.wintypes`, which refuses to import off Windows and
# would take the tests and the type check with it.
WORD = ctypes.c_uint16
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

# Set 1 scan codes. `0xE0` marks the keys the keyboard sends with an extended prefix.
SCAN_CODES: dict[str, int] = {
    "escape": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08,
    "8": 0x09, "9": 0x0A, "0": 0x0B, "-": 0x0C, "=": 0x0D, "backspace": 0x0E, "tab": 0x0F,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16, "i": 0x17,
    "o": 0x18, "p": 0x19, "[": 0x1A, "]": 0x1B, "enter": 0x1C, "ctrl": 0x1D, "a": 0x1E, "s": 0x1F,
    "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26, ";": 0x27,
    "'": 0x28, "`": 0x29, "shift": 0x2A, "\\": 0x2B, "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F,
    "b": 0x30, "n": 0x31, "m": 0x32, ",": 0x33, ".": 0x34, "/": 0x35, "rshift": 0x36, "alt": 0x38,
    "space": 0x39, "capslock": 0x3A, "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F,
    "f6": 0x40, "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44, "f11": 0x57, "f12": 0x58,
    "kp_end": 0x4F, "kp_downarrow": 0x50, "kp_pgdn": 0x51, "kp_leftarrow": 0x4B, "kp_5": 0x4C,
    "kp_rightarrow": 0x4D, "kp_home": 0x47, "kp_uparrow": 0x48, "kp_pgup": 0x49, "kp_ins": 0x52,
    "kp_del": 0x53, "kp_slash": 0xE035, "kp_multiply": 0x37, "kp_minus": 0x4A, "kp_plus": 0x4E,
    "kp_enter": 0xE01C, "ins": 0xE052, "del": 0xE053, "home": 0xE047, "end": 0xE04F,
    "pgup": 0xE049, "pgdn": 0xE051, "uparrow": 0xE048, "downarrow": 0xE050,
    "leftarrow": 0xE04B, "rightarrow": 0xE04D, "rctrl": 0xE01D, "ralt": 0xE038,
}

ALIASES = {
    "return": "enter", "esc": "escape", "spacebar": "space", "up": "uparrow", "down": "downarrow",
    "left": "leftarrow", "right": "rightarrow", "insert": "ins", "delete": "del",
    "pageup": "pgup", "pagedown": "pgdn", "control": "ctrl", "lctrl": "ctrl", "lshift": "shift",
    "lalt": "alt", "semicolon": ";",
}


class KeyPressError(RuntimeError):
    """The key could not be pressed - unknown name, or Windows refused the input."""


def scan_code(key: str) -> int:
    """Translate a CS2 bind name (`p`, `F5`, `KP_END`) into its scan code."""
    name = key.strip().lower()
    name = ALIASES.get(name, name)
    code = SCAN_CODES.get(name)
    if code is None:
        raise KeyPressError(f"'{key}' is not a key this can press - bind a letter, digit or F-key")
    return code


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _MouseInput(ctypes.Structure):
    """Never sent, but it is the largest arm of the union and so sets `INPUT`'s size.

    `SendInput` rejects the whole call with ERROR_INVALID_PARAMETER unless the size it is handed
    matches the real `INPUT`, which is 40 bytes on x64 - a keyboard-only union would be 32.
    """

    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyboardInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", DWORD), ("union", _InputUnion)]


def _event(code: int, key_up: bool) -> _Input:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
    if code > 0xFF:  # extended keys travel as `0xE0` plus the low byte
        flags |= KEYEVENTF_EXTENDEDKEY
        code &= 0xFF
    keyboard = _KeyboardInput(0, code, flags, 0, 0)
    return _Input(INPUT_KEYBOARD, _InputUnion(ki=keyboard))


ERROR_ACCESS_DENIED = 5


RELEASE_ATTEMPTS = 3


def press(key: str) -> None:
    """Tap `key` in the focused window. Raises `KeyPressError` if Windows drops the input.

    Down and up go in one at a time: overlays and anti-cheat filters routinely swallow one of
    the two, and a batch of two only reports how many got through, not which.
    """
    code = scan_code(key)
    try:
        # `use_last_error` is what makes the refusal readable rather than a bare count of 0.
        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - only reachable off Windows
        raise KeyPressError("sending keystrokes only works on Windows") from exc

    def send(key_up: bool) -> int:
        event = _event(code, key_up=key_up)
        return int(user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input)))

    if not send(key_up=False):
        raise KeyPressError(_refusal(int(ctypes.get_last_error())))  # type: ignore[attr-defined]
    for _ in range(RELEASE_ATTEMPTS):
        if send(key_up=True):
            return
    raise KeyPressError(f"'{key}' went down but Windows would not let it back up")


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def is_elevated() -> bool:
    """Whether the bot itself runs as administrator."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError):  # pragma: no cover - only reachable off Windows
        return False


def foreground_is_out_of_reach() -> bool | None:
    """Whether the focused window belongs to a process this one may not touch.

    That is what makes Windows drop the keystroke: an elevated game ignores input from a
    non-elevated sender. None means the question could not be answered.
    """
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - only reachable off Windows
        return None
    pid = DWORD(0)
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    if not pid.value:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    kernel32.CloseHandle(handle)
    return False


def _refusal(error_code: int) -> str:
    """Explain a dropped keystroke, which Windows only ever reports as a count and an error code."""
    if error_code != ERROR_ACCESS_DENIED:
        return f"Windows dropped the keystroke (error {error_code})"
    if is_elevated():
        return (
            "Windows blocked the keystroke (access denied) even though the bot is already "
            "administrator - something else is filtering input, e.g. an anti-cheat or overlay"
        )
    return (
        "Windows blocked the keystroke because CS2 runs as administrator and the bot does not - "
        "use 'Restart as administrator' on the Game tab"
    )


def diagnosis() -> dict[str, object]:
    """What Windows will and will not let this process do, for the panel's self-test."""
    return {
        "windows": sys.platform == "win32",
        "bot_is_administrator": is_elevated(),
        "focused_window_out_of_reach": foreground_is_out_of_reach(),
    }
