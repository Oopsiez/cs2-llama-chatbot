import time

import pytest

from cs2bot.config import AppConfig
from cs2bot.engine import Engine
from cs2bot.models import ChatChannel, ChatMessage, LifeState
from cs2bot.output.dry_run import DryRunSender
from cs2bot.voice.listener import Utterance


def build_engine(**overrides) -> Engine:
    config = AppConfig(enabled=True)
    config.llm.backend = "mock"
    config.game.output_backend = "dry_run"
    config.behavior.cooldown_seconds = 0
    config.behavior.reply_delay = 0
    for path, value in overrides.items():
        section, field = path.split(".")
        setattr(getattr(config, section), field, value)
    engine = Engine(config, seed=7)
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
async def test_the_first_reply_is_not_held_back_on_a_freshly_booted_machine():
    # The cooldown is measured against a monotonic clock that starts at boot, so a machine
    # that came up seconds ago must not look like the bot has just spoken.
    engine = build_engine()
    engine.config.behavior.cooldown_seconds = 60
    assert engine.last_reply_at < time.monotonic() - 86400
    assert await engine.handle_message(chat()) is not None


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


@pytest.mark.asyncio
async def test_asking_the_game_runs_the_name_command():
    engine = build_engine()
    await engine.ask_game_for_name()
    assert engine._sender.commands == ["name"]
    engine._note_identity('"name" = "skelly" ( def. "unnamed" )')
    assert engine.own_name == "skelly" and engine.name_source == "asked the game"


@pytest.mark.asyncio
async def test_the_name_question_repeats_on_its_own_timer():
    engine = build_engine(**{"game.name_probe_seconds": 120.0})
    await engine._maybe_ask_for_name()
    await engine._maybe_ask_for_name()
    assert engine._sender.commands == ["name"]

    engine._probed_at -= 121
    await engine._maybe_ask_for_name()
    assert engine._sender.commands == ["name", "name"]


@pytest.mark.asyncio
async def test_the_game_is_not_asked_when_the_name_is_set_by_hand():
    engine = build_engine(**{"game.own_name": "noodle"})
    await engine._maybe_ask_for_name()
    engine.config.game.own_name = ""
    engine.config.game.name_probe_seconds = 0
    await engine._maybe_ask_for_name()
    assert engine._sender.commands == []


@pytest.mark.asyncio
async def test_a_rename_replaces_the_detected_name():
    engine = build_engine()
    engine._note_identity('"name" = "skelly"')
    engine._note_identity("skelly changed name to noodle")
    assert engine.own_name == "noodle"


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


def build_voice_engine(**overrides) -> Engine:
    engine = build_engine(**overrides)
    engine.config.voice.enabled = True
    engine.config.voice.trigger_words = []
    engine.config.voice.cooldown_seconds = 0
    return engine


@pytest.mark.asyncio
async def test_a_transcript_is_answered_in_team_chat():
    engine = build_voice_engine()
    reply = await engine.handle_voice("they are pushing b, we need help")
    assert reply is not None and reply.delivered
    assert engine._sender.sent[-1][1] is True  # team_only


@pytest.mark.asyncio
async def test_voice_answers_team_chat_even_when_the_bot_only_talks_in_all_chat():
    engine = build_voice_engine(**{"behavior.reply_channels": [ChatChannel.ALL]})
    reply = await engine.handle_voice("they are pushing b, we need help")
    assert reply is not None
    assert engine._sender.sent[-1][1] is True


@pytest.mark.asyncio
async def test_a_grunt_is_not_worth_answering():
    engine = build_voice_engine(**{"voice.min_words": 3})
    assert await engine.handle_voice("uh what") is None
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_voice_only_answers_when_its_own_trigger_word_is_said():
    engine = build_voice_engine()
    engine.config.voice.trigger_words = ["bot"]
    engine.config.behavior.trigger_words = ["hey"]
    assert await engine.handle_voice("hey are they pushing b") is None
    assert await engine.handle_voice("bot are they pushing b") is not None


@pytest.mark.asyncio
async def test_voice_is_paced_on_a_clock_of_its_own():
    engine = build_voice_engine()
    engine.config.voice.cooldown_seconds = 60
    engine.config.behavior.cooldown_seconds = 60
    assert await engine.handle_voice("they are pushing b right now") is not None
    assert await engine.handle_voice("they are going a instead") is None
    # Answering the voice does not spend the typed chat's cooldown, or a talkative lobby
    # would keep the bot out of chat entirely.
    assert await engine.handle_message(chat()) is not None
    assert await engine.handle_voice("they are going a instead") is None


class FakeListener:
    """A listener that hands over one transcript and never touches a sound card."""

    def __init__(self, text: str) -> None:
        self.waiting = [Utterance(text=text, seconds=1.0)]
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def drain(self) -> list[Utterance]:
        out, self.waiting = self.waiting, []
        return out


@pytest.mark.asyncio
async def test_the_bot_listens_even_when_it_cannot_find_console_log():
    """Speech comes off the speakers, so a missing console.log must not silence it."""
    engine = build_voice_engine(**{"game.console_log_path": ""})
    engine._voice = FakeListener("they are pushing b, we need help")
    await engine._tick()
    assert engine._voice.started
    assert engine._sender.sent[-1][1] is True


@pytest.mark.asyncio
async def test_a_spoken_transcript_never_puts_a_name_on_a_strat_job():
    engine = build_voice_engine()
    await engine.handle_voice("they are pushing b, we need help")
    assert engine.roster.names() == []


@pytest.mark.asyncio
async def test_a_spoken_order_is_answered_in_team_chat_even_when_strats_go_to_all_chat():
    engine = build_voice_engine()
    engine.config.strategy.enabled = True
    engine.config.strategy.reply_channel = "all"
    engine.config.strategy.round_start_only = False
    engine.game_state.player.map_name = "de_mirage"
    reply = await engine.handle_voice("what is the plan here")
    assert reply is not None
    assert engine._sender.sent
    assert all(team_only for _, team_only in engine._sender.sent)


@pytest.mark.asyncio
async def test_spoken_orders_can_be_ignored():
    engine = build_voice_engine(**{"voice.obey_commands": False})
    engine.config.strategy.enabled = True
    engine.config.strategy.round_start_only = False
    engine.game_state.player.map_name = "de_mirage"
    engine.config.voice.trigger_words = ["bot"]
    assert await engine.handle_voice("what is the plan here") is None


@pytest.mark.asyncio
async def test_nothing_listens_until_voice_is_turned_on():
    engine = build_engine()
    engine.config.voice.enabled = False
    await engine.pump_voice()
    assert engine._voice is None
    assert engine.voice_status()["enabled"] is False


@pytest.mark.asyncio
async def test_changing_the_voice_settings_builds_a_fresh_listener():
    engine = build_voice_engine()
    listener = engine.voice
    updated = engine.config.model_copy(deep=True)
    updated.voice.device = "some other speakers"
    await engine.apply_config(updated, persist=False)
    assert engine._voice is None
    assert engine.voice is not listener
