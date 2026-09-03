import pytest

from cs2bot.config import AppConfig
from cs2bot.engine import Engine
from cs2bot.models import ChatChannel, ChatMessage, LifeState
from cs2bot.output.dry_run import DryRunSender


def build_engine(**overrides) -> Engine:
    config = AppConfig(enabled=True)
    config.llm.backend = "mock"
    config.game.output_backend = "dry_run"
    config.behavior.cooldown_seconds = 0
    for path, value in overrides.items():
        section, field = path.split(".")
        setattr(getattr(config, section), field, value)
    engine = Engine(config)
    engine._sender = DryRunSender()
    return engine


def chat(**kwargs) -> ChatMessage:
    base = {"raw": "raw", "sender": "enemy", "text": "ez", "channel": ChatChannel.ALL,
            "sender_state": LifeState.ALIVE}
    base.update(kwargs)
    return ChatMessage(**base)


@pytest.mark.asyncio
async def test_replies_and_delivers():
    engine = build_engine()
    reply = await engine.handle_message(chat())
    assert reply is not None and reply.delivered
    assert engine._sender.sent


@pytest.mark.asyncio
async def test_dead_sender_is_skipped_while_alive():
    engine = build_engine()
    assert await engine.handle_message(chat(sender_state=LifeState.DEAD)) is None
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_disabled_engine_only_records_chat():
    engine = build_engine()
    engine.config.enabled = False
    assert await engine.handle_message(chat()) is None
    assert engine.history[-1].text == "ez"


@pytest.mark.asyncio
async def test_cooldown_blocks_second_reply():
    engine = build_engine()
    engine.config.behavior.cooldown_seconds = 60
    assert await engine.handle_message(chat()) is not None
    assert await engine.handle_message(chat(text="again")) is None


@pytest.mark.asyncio
async def test_team_message_is_sent_with_say_team():
    engine = build_engine()
    await engine.handle_message(chat(channel=ChatChannel.TEAM))
    assert engine._sender.sent[0][1] is True


@pytest.mark.asyncio
async def test_being_addressed_beats_cooldown_and_triggers():
    engine = build_engine(**{"game.own_name": "noodle"})
    engine.config.behavior.cooldown_seconds = 60
    engine.config.behavior.trigger_words = ["bot"]
    assert await engine.handle_message(chat(text="hey")) is None
    reply = await engine.handle_message(chat(text="noodle: you awake"))
    assert reply is not None
    assert engine.history[-2].addressed_to_me


@pytest.mark.asyncio
async def test_only_reply_when_addressed():
    engine = build_engine(**{"game.own_name": "noodle"})
    engine.config.behavior.only_reply_when_addressed = True
    assert await engine.handle_message(chat(text="who queued this")) is None
    assert await engine.handle_message(chat(text="noodle stop")) is not None


def test_own_name_falls_back_from_panel_to_gsi_to_log():
    engine = build_engine()
    assert engine.own_name == "" and engine.name_source == "unknown"

    engine._note_identity('"name" = "skelly" ( def. "unnamed" )')
    assert engine.own_name == "skelly" and engine.name_source == "console log"

    engine.game_state.update({"provider": {"steamid": "1"}, "player": {"steamid": "1", "name": "gsiname"}})
    assert engine.own_name == "gsiname" and engine.name_source == "game state integration"

    engine.config.game.own_name = "manual"
    assert engine.own_name == "manual" and engine.name_source == "set in panel"


def test_auto_detect_can_be_turned_off():
    engine = build_engine(**{"game.auto_detect_name": False})
    engine._note_identity('"name" = "skelly"')
    assert engine.own_name == ""


@pytest.mark.asyncio
async def test_bare_you_counts_only_after_the_bot_speaks():
    engine = build_engine(**{"game.own_name": "noodle"})
    assert engine.annotate(chat(text="you suck")).addressed_to_me is False
    await engine.handle_message(chat(text="noodle hey"))
    assert engine.annotate(chat(text="you suck")).addressed_to_me is True


@pytest.mark.asyncio
async def test_reply_is_capped_by_persona_limit():
    engine = build_engine()
    engine.config.persona.max_reply_chars = 20
    reply = await engine.handle_message(chat())
    assert reply is not None
    assert len(reply.text) <= 20
