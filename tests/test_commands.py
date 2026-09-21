import pytest

from cs2bot import commands
from cs2bot.config import StrategySettings
from cs2bot.models import ChatChannel


def settings(**overrides) -> StrategySettings:
    return StrategySettings(**overrides)


@pytest.mark.parametrize(
    "text,site",
    [
        ("strat?", ""),
        ("!strat", ""),
        ("strat b", "b"),
        ("!strat a", "a"),
        (".strat mid", "mid"),
        ("whats the plan", ""),
        ("call it", ""),
    ],
)
def test_strategy_requests(text, site):
    command = commands.parse(text, settings())
    assert command is not None and command.kind == commands.STRATEGY
    assert command.site == site


def test_a_sentence_about_strats_is_conversation():
    assert commands.parse("honestly our strats have been awful all game", settings()) is None


def test_an_explicit_command_is_taken_however_long_it_is():
    command = commands.parse("!strat b we have the utility for it", settings())
    assert command is not None and command.kind == commands.STRATEGY and command.site == "b"


@pytest.mark.parametrize("text", ["!quiet", "bot shut up", "stfu bot", "!mute"])
def test_quiet_orders(text):
    command = commands.parse(text, settings())
    assert command is not None and command.kind == commands.QUIET


@pytest.mark.parametrize("text", ["!talk", "bot unmute", "!speak"])
def test_talk_orders(text):
    command = commands.parse(text, settings())
    assert command is not None and command.kind == commands.TALK


def test_orders_can_be_turned_off():
    assert commands.parse("!quiet", settings(obey_commands=False)) is None
    assert commands.parse("strat?", settings(answer_when_asked=False)) is None


def test_ordinary_chat_is_not_a_command():
    assert commands.parse("nice shot", settings()) is None
    assert commands.parse("", settings()) is None


@pytest.mark.parametrize(
    "listen,channel,heard",
    [
        ("both", ChatChannel.ALL, True),
        ("both", ChatChannel.TEAM, True),
        ("both", ChatChannel.SPEC, False),
        ("team", ChatChannel.TEAM, True),
        ("team", ChatChannel.ALL, False),
        ("all", ChatChannel.ALL, True),
        ("all", ChatChannel.TEAM, False),
    ],
)
def test_listen_channel(listen, channel, heard):
    assert commands.listens_to(settings(listen_channel=listen), channel) is heard


@pytest.mark.parametrize(
    "reply,asked_in,team_only",
    [
        ("team", ChatChannel.ALL, True),
        ("all", ChatChannel.TEAM, False),
        ("same", ChatChannel.TEAM, True),
        ("same", ChatChannel.ALL, False),
    ],
)
def test_reply_channel(reply, asked_in, team_only):
    assert commands.answer_in_team_chat(settings(reply_channel=reply), asked_in) is team_only


@pytest.mark.parametrize(
    "text,wanted",
    [
        ("!persona toxic", "toxic"),
        ("!persona angry and toxic", "angry and toxic"),
        ("bot be the coach", "coach"),
        ("act like a silver", "silver"),
        ("!personality deadpan", "deadpan"),
        ("become the therapist", "therapist"),
    ],
)
def test_persona_orders(text, wanted):
    command = commands.parse(text, settings())
    assert command is not None and command.kind == commands.PERSONA
    assert command.persona == wanted


@pytest.mark.parametrize("text", ["!persona", "!persona list", "what personas do you have"])
def test_asking_which_personas_there_are(text):
    command = commands.parse(text, settings())
    assert command is not None and command.kind == commands.PERSONA and command.persona == ""


def test_persona_orders_can_be_turned_off():
    assert commands.parse("!persona toxic", settings(obey_persona_commands=False)) is None


def test_be_quiet_is_still_a_quiet_order():
    command = commands.parse("bot be quiet", settings())
    assert command is not None and command.kind == commands.QUIET


def test_only_an_explicit_persona_order_is_worth_a_complaint():
    assert commands.parse("be careful", settings()).explicit is False
    assert commands.parse("!persona toxic", settings()).explicit is True
