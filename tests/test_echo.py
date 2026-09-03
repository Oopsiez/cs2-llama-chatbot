import pytest

from cs2bot.echo import EchoGuard, echo_key
from tests.test_engine import build_engine, chat


def test_key_ignores_case_punctuation_and_spacing():
    assert echo_key("Nice one, mate!") == echo_key("nice one   mate")


def test_remembers_what_was_just_sent():
    guard = EchoGuard()
    guard.remember("rotating b, hold a")
    assert guard.is_echo("Rotating B, hold A")
    assert not guard.is_echo("stacking a")


def test_a_chunk_of_a_long_reply_still_counts_as_our_own():
    guard = EchoGuard()
    guard.remember("they are stacking b so we should take mid control first")
    assert guard.is_echo("they are stacking b so we should")


def test_short_agreement_from_a_real_player_is_not_swallowed():
    guard = EchoGuard()
    guard.remember("gg")
    assert not guard.is_echo("gg wp everyone that was close")


def test_memory_expires():
    guard = EchoGuard(window=30.0)
    guard.remember("hold this angle", now=1000.0)
    assert guard.is_echo("hold this angle", now=1020.0)
    assert not guard.is_echo("hold this angle", now=1100.0)


@pytest.mark.asyncio
async def test_bot_does_not_answer_its_own_line_echoed_back():
    engine = build_engine()
    reply = await engine.handle_message(chat(text="where is everyone"))
    assert reply is not None

    echoed = chat(sender="someone", text=reply.text)
    assert await engine.handle_message(echoed) is None


@pytest.mark.asyncio
async def test_own_echo_is_caught_before_the_name_is_known():
    """The team-chat loop: no GSI, no name, so the only clue is the text itself."""
    engine = build_engine(**{"game.own_name": ""})
    reply = await engine.handle_message(chat(text="anyone alive"))
    assert reply is not None

    echoed = engine.flag_own_echo(chat(sender="mystery", text=reply.text))
    assert echoed.is_self
    assert not echoed.addressed_to_me


@pytest.mark.asyncio
async def test_other_players_are_still_answered_after_the_bot_speaks():
    engine = build_engine()
    await engine.handle_message(chat(text="first"))
    reply = await engine.handle_message(chat(sender="teammate", text="rotate a now"))
    assert reply is not None and reply.delivered
