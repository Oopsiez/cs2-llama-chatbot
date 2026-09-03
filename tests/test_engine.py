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
async def test_reply_is_capped_by_persona_limit():
    engine = build_engine()
    engine.config.persona.max_reply_chars = 20
    reply = await engine.handle_message(chat())
    assert reply is not None
    assert len(reply.text) <= 20
