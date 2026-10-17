from cs2bot import commands
from cs2bot.config import StrategySettings
from cs2bot.parser import parse_chat_line
from cs2bot.radio import is_radio, is_radio_tagged


def test_radio_lines_are_recognised_however_whisper_writes_them():
    assert is_radio("Enemy spotted")
    assert is_radio("enemy spotted.")
    assert is_radio("Affirmative, sector clear.")
    assert is_radio("Enemy spotted (Catwalk)")
    assert is_radio("Need backup!")
    assert not is_radio("enemy spotted behind the box, two of them")
    assert not is_radio("where are they")
    assert not is_radio("")


def test_radio_tagged_log_lines_are_not_chat():
    assert is_radio_tagged("Gavin (RADIO): Enemy spotted")
    assert is_radio_tagged("[RADIO] Gavin: Need backup")
    assert parse_chat_line("[ALL] Gavin (RADIO): Enemy spotted") is None
    assert parse_chat_line("[ALL] Gavin: enemy spotted behind box") is not None


def test_radio_lines_are_not_orders_but_explicit_ones_still_are():
    assert commands.parse("go go go", StrategySettings()) is None
    assert commands.parse("!talk", StrategySettings()) is not None
