import pytest

from cs2bot import playbook
from cs2bot.config import AppConfig
from cs2bot.engine import Engine
from cs2bot.models import ChatChannel, ChatMessage, LifeState, Team
from cs2bot.output.dry_run import DryRunSender


def build_engine(map_name: str = "de_mirage", team: Team = Team.T, **overrides) -> Engine:
    config = AppConfig(enabled=True)
    config.llm.backend = "mock"
    config.game.output_backend = "dry_run"
    config.behavior.cooldown_seconds = 0
    config.behavior.reply_delay = 0
    config.strategy.in_character = False
    for path, value in overrides.items():
        section, field = path.split(".")
        setattr(getattr(config, section), field, value)
    engine = Engine(config, seed=11)
    engine._sender = DryRunSender()
    engine.game_state.player = engine.game_state.player.model_copy(
        update={"map_name": map_name, "team": team, "round_phase": "freezetime"}
    )
    return engine


def chat(text: str, channel: ChatChannel = ChatChannel.TEAM) -> ChatMessage:
    return ChatMessage(
        raw="raw", sender="Gavin", text=text, channel=channel, sender_state=LifeState.ALIVE
    )


@pytest.mark.asyncio
async def test_answers_a_strat_request_with_a_real_call():
    engine = build_engine()
    reply = await engine.handle_message(chat("strat?"))
    assert reply is not None and reply.delivered
    calls = {playbook.call_text(s) for s in playbook.strategies_for("de_mirage", Team.T)}
    assert reply.text in calls


@pytest.mark.asyncio
async def test_the_call_matches_the_side_we_are_on():
    engine = build_engine(team=Team.CT)
    reply = await engine.handle_message(chat("!strat"))
    assert reply is not None
    ct_calls = {playbook.call_text(s) for s in playbook.strategies_for("de_mirage", Team.CT)}
    assert reply.text in ct_calls


@pytest.mark.asyncio
async def test_the_asked_for_site_is_honoured():
    engine = build_engine(map_name="de_inferno")
    reply = await engine.handle_message(chat("!strat b"))
    assert reply is not None and "B" in reply.text.upper()


@pytest.mark.asyncio
async def test_unknown_map_still_gets_a_generic_call():
    engine = build_engine(map_name="")
    reply = await engine.handle_message(chat("strat?"))
    assert reply is not None and reply.delivered


@pytest.mark.asyncio
async def test_orders_from_the_wrong_channel_are_ignored():
    engine = build_engine(**{"strategy.listen_channel": "team"})
    assert await engine.handle_message(chat("strat?", ChatChannel.ALL)) is None
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_the_call_goes_to_team_chat_even_when_all_chat_asked():
    engine = build_engine(**{"strategy.listen_channel": "both"})
    await engine.handle_message(chat("strat?", ChatChannel.ALL))
    assert engine._sender.sent and engine._sender.sent[-1][1] is True


@pytest.mark.asyncio
async def test_round_start_only_refuses_mid_round():
    engine = build_engine(**{"strategy.round_start_only": True})
    engine.game_state.player = engine.game_state.player.model_copy(
        update={"round_phase": "live", "updated_at": 1e18}
    )
    engine._round_started_at = float("-inf")
    assert await engine.handle_message(chat("strat?")) is None
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_quiet_shuts_the_bot_up_and_talk_brings_it_back():
    engine = build_engine()
    assert await engine.handle_message(chat("!quiet")) is None
    assert engine.quiet
    assert await engine.handle_message(chat("nice shot")) is None
    assert not engine._sender.sent

    await engine.handle_message(chat("!talk"))
    assert not engine.quiet
    reply = await engine.handle_message(chat("nice shot"))
    assert reply is not None and reply.delivered


@pytest.mark.asyncio
async def test_strategy_mode_off_leaves_a_strat_request_to_the_model():
    engine = build_engine(**{"strategy.enabled": False})
    reply = await engine.handle_message(chat("strat?"))
    assert reply is not None
    calls = {playbook.call_text(s) for s in playbook.strategies_for("de_mirage", Team.T)}
    assert reply.text not in calls


@pytest.mark.asyncio
async def test_calling_every_round_fires_once_per_round():
    engine = build_engine(**{"strategy.call_every_round": True})
    engine.game_state.player = engine.game_state.player.model_copy(update={"round_number": 4})
    await engine.maybe_call_strategy()
    await engine.maybe_call_strategy()
    assert len(engine._sender.sent) == 1

    engine.game_state.player = engine.game_state.player.model_copy(update={"round_number": 5})
    await engine.maybe_call_strategy()
    assert len(engine._sender.sent) == 2


@pytest.mark.asyncio
async def test_no_unprompted_call_outside_freezetime():
    engine = build_engine(**{"strategy.call_every_round": True})
    engine.game_state.player = engine.game_state.player.model_copy(update={"round_phase": "live"})
    await engine.maybe_call_strategy()
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_the_same_call_is_not_made_twice_in_a_row():
    engine = build_engine()
    first = await engine.handle_message(chat("strat?"))
    second = await engine.handle_message(chat("strat?"))
    assert first is not None and second is not None
    assert first.text != second.text


@pytest.mark.asyncio
async def test_in_character_calls_go_through_the_model():
    engine = build_engine(**{"strategy.in_character": True})
    reply = await engine.handle_message(chat("strat?"))
    assert reply is not None and reply.delivered
    calls = {playbook.call_text(s) for s in playbook.strategies_for("de_mirage", Team.T)}
    assert reply.text not in calls
