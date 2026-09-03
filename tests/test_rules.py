import pytest

from cs2bot.config import AppConfig
from cs2bot.models import ChatChannel, ChatMessage, LifeState, LocalPlayer
from cs2bot.rules import should_reply


def message(**kwargs) -> ChatMessage:
    base = {
        "raw": "raw",
        "sender": "enemy",
        "text": "ez",
        "channel": ChatChannel.ALL,
        "sender_state": LifeState.ALIVE,
    }
    base.update(kwargs)
    return ChatMessage(**base)


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


def test_alive_bot_answers_alive_player(config):
    allowed, _ = should_reply(config, message(), LifeState.ALIVE, LocalPlayer())
    assert allowed


def test_alive_bot_ignores_dead_player(config):
    allowed, reason = should_reply(
        config, message(sender_state=LifeState.DEAD), LifeState.ALIVE, LocalPlayer()
    )
    assert not allowed
    assert "dead" in reason


def test_dead_bot_ignores_alive_player(config):
    allowed, reason = should_reply(config, message(), LifeState.DEAD, LocalPlayer())
    assert not allowed
    assert "cannot see dead chat" in reason


def test_dead_bot_answers_dead_player(config):
    allowed, _ = should_reply(
        config, message(sender_state=LifeState.DEAD), LifeState.DEAD, LocalPlayer()
    )
    assert allowed


def test_warmup_merges_the_audiences(config):
    player = LocalPlayer(map_phase="warmup")
    allowed, _ = should_reply(
        config, message(sender_state=LifeState.DEAD), LifeState.ALIVE, player
    )
    assert allowed


def test_global_dead_chat_override(config):
    config.dead_alive.dead_chat_is_global = True
    allowed, _ = should_reply(config, message(), LifeState.DEAD, LocalPlayer())
    assert allowed


def test_disabled_channel(config):
    config.behavior.reply_channels = [ChatChannel.TEAM]
    allowed, reason = should_reply(config, message(), LifeState.ALIVE, LocalPlayer())
    assert not allowed
    assert "all chat is disabled" in reason


def test_trigger_words(config):
    config.behavior.trigger_words = ["bot"]
    allowed, _ = should_reply(config, message(text="hey bot"), LifeState.ALIVE, LocalPlayer())
    assert allowed
    allowed, _ = should_reply(config, message(text="hey"), LifeState.ALIVE, LocalPlayer())
    assert not allowed


def test_ignore_list_and_self(config):
    config.behavior.ignore_players = ["ENEMY"]
    allowed, _ = should_reply(config, message(), LifeState.ALIVE, LocalPlayer())
    assert not allowed
    allowed, _ = should_reply(config, message(is_self=True), LifeState.ALIVE, LocalPlayer())
    assert not allowed
