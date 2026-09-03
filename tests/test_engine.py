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
    config.behavior.reply_delay = 0
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
async def test_dead_sender_still_gets_an_answer():
    engine = build_engine()
    reply = await engine.handle_message(chat(sender_state=LifeState.DEAD))
    assert reply is not None and reply.delivered


@pytest.mark.asyncio
async def test_dead_sender_is_skipped_when_visibility_is_enforced():
    engine = build_engine(
        **{
            "dead_alive.enforce_visibility": True,
            "dead_alive.dead_chat_is_global": False,
            "dead_alive.reply_to_dead_when_alive": False,
        }
    )
    assert await engine.handle_message(chat(sender_state=LifeState.DEAD)) is None
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_dead_players_stay_dead_until_the_round_resets():
    engine = build_engine()
    await engine.handle_message(chat(sender_state=LifeState.DEAD))
    plain = engine.track_state(chat(sender_state=LifeState.UNKNOWN, text="still salty"))
    assert plain.sender_state is LifeState.DEAD

    engine.game_state.player.round_phase = "freezetime"
    fresh = engine.track_state(chat(sender_state=LifeState.UNKNOWN, text="new round"))
    assert fresh.sender_state is LifeState.UNKNOWN


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


class StubBackend:
    """Says the same thing forever unless told otherwise."""

    name = "stub"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls = 0

    async def generate(self, turns, params) -> str:
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]

    async def health(self) -> str:
        return "stub"

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_repeated_reply_is_regenerated():
    engine = build_engine()
    engine._backend = StubBackend(["rotate b now", "rotate b now!", "save for next round"])
    first = await engine.handle_message(chat())
    second = await engine.handle_message(chat(text="and now"))
    assert first is not None and second is not None
    assert first.text == "rotate b now"
    assert second.text == "save for next round"


@pytest.mark.asyncio
async def test_bot_stays_quiet_when_every_retry_repeats():
    engine = build_engine()
    engine._backend = StubBackend(["rotate b now"])
    assert await engine.handle_message(chat()) is not None
    assert await engine.handle_message(chat(text="and now")) is None
    assert engine.recent_replies == ["rotate b now"]


@pytest.mark.asyncio
async def test_repeats_are_allowed_when_the_check_is_off():
    engine = build_engine(**{"behavior.avoid_repeats": False})
    engine._backend = StubBackend(["rotate b now"])
    await engine.handle_message(chat())
    second = await engine.handle_message(chat(text="and now"))
    assert second is not None and second.text == "rotate b now"


@pytest.mark.asyncio
async def test_recent_replies_are_capped_by_memory():
    engine = build_engine(**{"behavior.repeat_memory": 2, "behavior.avoid_repeats": False})
    engine._backend = StubBackend(["one", "two", "three"])
    for text in ("a", "b", "c"):
        await engine.handle_message(chat(text=text))
    assert engine.recent_replies == ["two", "three"]


def test_reply_delay_follows_the_slider_or_typing_speed():
    engine = build_engine(**{"behavior.reply_delay": 4.0})
    assert engine.reply_delay_for("anything") == 4.0

    engine.config.behavior.humanized_typing = True
    short = engine.reply_delay_for("gg")
    long = engine.reply_delay_for("g" * 100)
    assert short < long
    assert short > 0  # it still reads the message first


@pytest.mark.asyncio
async def test_reply_is_capped_by_persona_limit():
    engine = build_engine()
    engine.config.persona.max_reply_chars = 20
    reply = await engine.handle_message(chat())
    assert reply is not None
    assert len(reply.text) <= 20
