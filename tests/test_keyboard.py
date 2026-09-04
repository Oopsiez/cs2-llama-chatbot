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
