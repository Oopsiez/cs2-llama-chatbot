import ctypes

import pytest

from cs2bot.output import keyboard
from cs2bot.output.windows_cfg import WindowsCfgSender


def test_bind_names_from_the_cs2_console_map_to_scan_codes():
    assert keyboard.scan_code("p") == 0x19
    assert keyboard.scan_code("F5") == 0x3F
    assert keyboard.scan_code(" ENTER ") == 0x1C
    assert keyboard.scan_code("KP_END") == 0x4F
    assert keyboard.scan_code("uparrow") == keyboard.scan_code("up")


def test_an_unbindable_key_says_so_instead_of_pressing_nothing():
    with pytest.raises(keyboard.KeyPressError):
        keyboard.scan_code("mouse4")


def test_extended_keys_carry_the_extended_flag_and_a_single_byte_code():
    event = keyboard._event(keyboard.scan_code("home"), key_up=False)
    assert event.union.ki.wScan == 0x47
    assert event.union.ki.dwFlags & keyboard.KEYEVENTF_EXTENDEDKEY
    assert not event.union.ki.dwFlags & keyboard.KEYEVENTF_KEYUP


def test_a_press_is_a_key_down_followed_by_a_key_up():
    down = keyboard._event(0x19, key_up=False)
    up = keyboard._event(0x19, key_up=True)
    assert down.union.ki.dwFlags & keyboard.KEYEVENTF_SCANCODE
    assert up.union.ki.dwFlags & keyboard.KEYEVENTF_KEYUP


def test_the_input_struct_is_the_size_windows_insists_on():
    """A keyboard-only union is 32 bytes and SendInput answers every call with error 87."""
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(keyboard._Input) == expected


def test_the_refusal_names_elevation_only_when_that_is_the_difference(monkeypatch):
    monkeypatch.setattr(keyboard, "is_elevated", lambda: False)
    assert "administrator" in keyboard._refusal(keyboard.ERROR_ACCESS_DENIED)

    monkeypatch.setattr(keyboard, "is_elevated", lambda: True)
    assert "already" in keyboard._refusal(keyboard.ERROR_ACCESS_DENIED)
    assert "error 87" in keyboard._refusal(87)


class _FakeUser32:
    """Stands in for Windows, which drops events it does not feel like delivering."""

    def __init__(self, accepts: list[int]) -> None:
        self.accepts = accepts
        self.calls = 0

    def SendInput(self, _count, _events, _size) -> int:  # noqa: N802 - the Windows spelling
        self.calls += 1
        return self.accepts.pop(0) if self.accepts else 1


def _fake_windows(monkeypatch, user32: _FakeUser32) -> None:
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: user32, raising=False)
    # `get_last_error` only exists on Windows, so off it the attribute has to be invented.
    monkeypatch.setattr(
        ctypes, "get_last_error", lambda: keyboard.ERROR_ACCESS_DENIED, raising=False
    )


def test_a_swallowed_key_up_is_retried_rather_than_called_a_block(monkeypatch):
    user32 = _FakeUser32([1, 0, 0, 1])
    _fake_windows(monkeypatch, user32)

    keyboard.press("p")

    assert user32.calls == 4


def test_a_key_that_never_goes_down_is_reported(monkeypatch):
    _fake_windows(monkeypatch, _FakeUser32([0]))

    with pytest.raises(keyboard.KeyPressError, match="administrator"):
        keyboard.press("p")


@pytest.mark.asyncio
async def test_a_console_command_is_run_through_the_same_cfg(tmp_path, monkeypatch):
    pressed: list[str] = []
    monkeypatch.setattr(keyboard, "press", pressed.append)
    sender = WindowsCfgSender(cfg_dir=str(tmp_path), require_focus=False, send_delay=0)

    ran, detail = await sender.run_command("name")

    assert ran and "name" in detail
    assert pressed == ["p"]
    assert (tmp_path / "message.cfg").read_text() == "name"


@pytest.mark.asyncio
async def test_the_panel_is_told_why_the_keypress_did_not_land(tmp_path, monkeypatch):
    sender = WindowsCfgSender(cfg_dir=str(tmp_path), require_focus=False, send_delay=0)

    def refuse(_key: str) -> None:
        raise keyboard.KeyPressError("Windows blocked the keystroke")

    monkeypatch.setattr(keyboard, "press", refuse)
    delivered, detail = await sender.send("hello")
    assert not delivered
    assert detail == "Windows blocked the keystroke"


@pytest.mark.asyncio
async def test_a_delivered_reply_writes_the_cfg_and_presses_the_bound_key(tmp_path, monkeypatch):
    pressed: list[str] = []
    monkeypatch.setattr(keyboard, "press", pressed.append)
    sender = WindowsCfgSender(cfg_dir=str(tmp_path), bind_key="k", require_focus=False, send_delay=0)

    delivered, _ = await sender.send("nice shot", team_only=True)

    assert delivered
    assert pressed == ["k"]
    assert (tmp_path / "message.cfg").read_text() == 'say_team "nice shot"'


class _StickyUser32(_FakeUser32):
    """Windows that only registers the press on the second try and the release on the second."""

    def __init__(self) -> None:
        super().__init__([])
        self.downs = 0
        self.ups = 0

    def SendInput(self, _count, events, _size) -> int:  # noqa: N802
        self.calls += 1
        if events._obj.union.ki.dwFlags & keyboard.KEYEVENTF_KEYUP:
            self.ups += 1
        else:
            self.downs += 1
        return 1

    def MapVirtualKeyW(self, _code, _kind) -> int:  # noqa: N802
        return 0x50

    def GetAsyncKeyState(self, _vk) -> int:  # noqa: N802
        return 0x8000 if self.downs >= 2 and self.ups < 2 else 0


def test_holding_a_key_checks_it_went_down_and_came_back_up(monkeypatch):
    user32 = _StickyUser32()
    _fake_windows(monkeypatch, user32)
    monkeypatch.setattr(keyboard.time, "sleep", lambda _s: None)

    with keyboard.hold("p"):
        assert user32.downs == 2
    assert user32.ups == 2


def test_a_refused_scan_code_falls_back_to_the_legacy_api(monkeypatch):
    user32 = _FakeUser32([0, 1])
    user32.legacy = []
    user32.keybd_event = lambda vk, scan, flags, extra: user32.legacy.append((scan, flags))
    _fake_windows(monkeypatch, user32)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)

    keyboard.press("p")

    assert user32.legacy and user32.legacy[0][0] == keyboard.scan_code("p")
