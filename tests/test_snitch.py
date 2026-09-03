import pytest

from cs2bot.callouts import Callout, CalloutBook, Position
from cs2bot.config import SnitchSettings
from cs2bot.gamestate import GameStateStore
from cs2bot.models import LifeState, LocalPlayer
from cs2bot.snitch import announcement, facts, is_request, prompt_note
from tests.test_engine import build_engine, chat


def book_with(*callouts: Callout, map_name: str = "de_dust2") -> CalloutBook:
    book = CalloutBook()
    for callout in callouts:
        book.record(map_name, callout)
    return book


def player(**kwargs) -> LocalPlayer:
    base = {"name": "noodle", "map_name": "de_dust2", "state": LifeState.ALIVE}
    base.update(kwargs)
    return LocalPlayer(**base)


def test_position_parses_the_gsi_string():
    parsed = Position.parse("1234.00, -567.50, 128.03")
    assert parsed == Position(x=1234.0, y=-567.5, z=128.03)


def test_position_rejects_anything_else():
    assert Position.parse("nowhere") is None
    assert Position.parse(None) is None
    assert Position.parse("1.0, 2.0") is None


def test_nearest_recorded_spot_wins():
    book = book_with(
        Callout(name="banana", x=0, y=0, z=0),
        Callout(name="car", x=300, y=0, z=0),
    )
    assert book.resolve("de_dust2", Position(x=250, y=0, z=0)) == "car"


def test_standing_nowhere_near_anything_has_no_callout():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    assert book.resolve("de_dust2", Position(x=5000, y=5000, z=0)) == ""
    assert book.resolve("de_mirage", Position(x=0, y=0, z=0)) == ""


def test_the_floor_above_is_a_different_place():
    book = book_with(Callout(name="pit", x=0, y=0, z=0, radius=200))
    assert book.resolve("de_dust2", Position(x=0, y=0, z=150)) == ""


def test_recording_the_same_name_twice_moves_it():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    book.record("de_dust2", Callout(name="Banana", x=900, y=0, z=0))
    assert len(book.for_map("de_dust2")) == 1
    assert book.resolve("de_dust2", Position(x=900, y=0, z=0)) == "Banana"


def test_forgetting_a_callout():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    assert book.forget("de_dust2", "BANANA")
    assert not book.forget("de_dust2", "banana")
    assert book.for_map("de_dust2") == []


def test_recognises_someone_asking_where_you_are():
    phrases = SnitchSettings().request_phrases
    assert is_request("yo where are you", phrases)
    assert is_request("WRU", phrases)
    assert not is_request("where is the bomb", phrases)


def test_facts_use_the_callout_when_there_is_one():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    spot = player(position=Position(x=10, y=10, z=0), health=42, active_weapon="ak47", bomb="planted")
    settings = SnitchSettings(enabled=True, reveal_weapon=True)
    assert facts(settings, spot, book) == [
        "you are at banana",
        "you have 42 hp",
        "you are holding a ak47",
        "the bomb is down",
    ]


def test_facts_are_limited_to_what_is_switched_on():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    spot = player(position=Position(x=0, y=0, z=0), health=42, active_weapon="ak47")
    settings = SnitchSettings(enabled=True, reveal_position=False, reveal_weapon=False)
    assert facts(settings, spot, book) == ["you have 42 hp"]


def test_the_prompt_says_nothing_when_snitching_is_off():
    spot = player(position=Position(x=0, y=0, z=0), health=100)
    assert prompt_note(SnitchSettings(), spot, CalloutBook()) is None


def test_the_prompt_pushes_harder_when_asked_outright():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    spot = player(position=Position(x=0, y=0, z=0), health=100)
    note = prompt_note(SnitchSettings(enabled=True), spot, book, asked=True)
    assert note is not None
    assert "you are at banana" in note
    assert "asked where you are" in note


def test_announcement_switches_to_first_person():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    spot = player(position=Position(x=0, y=0, z=0), health=88)
    assert announcement(SnitchSettings(enabled=True), spot, book) == "i am at banana, i have 88 hp"


def test_death_announcement_names_the_spot():
    book = book_with(Callout(name="banana", x=0, y=0, z=0))
    dead = player(position=Position(x=0, y=0, z=0), state=LifeState.DEAD)
    assert announcement(SnitchSettings(enabled=True), dead, book) == "i died at banana"


def test_death_announcement_without_a_recorded_spot():
    dead = player(position=Position(x=0, y=0, z=0), state=LifeState.DEAD)
    assert announcement(SnitchSettings(enabled=True), dead, CalloutBook()) == "im dead"


def test_gsi_payload_gives_position_weapon_and_bomb():
    store = GameStateStore()
    store.update(
        {
            "provider": {"steamid": "76561198000000000"},
            "map": {"name": "de_dust2", "phase": "live", "mode": "competitive"},
            "round": {"phase": "live", "bomb": "planted"},
            "player": {
                "steamid": "76561198000000000",
                "name": "noodle",
                "team": "T",
                "state": {"health": 63},
                "position": "1234.00, -567.50, 128.03",
                "weapons": {
                    "weapon_0": {"name": "weapon_knife", "state": "holstered"},
                    "weapon_1": {"name": "weapon_ak47", "state": "active"},
                },
            },
        }
    )
    assert store.player.position == Position(x=1234.0, y=-567.5, z=128.03)
    assert store.player.active_weapon == "ak47"
    assert store.player.bomb == "planted"
    assert store.player.health == 63


def test_a_spectated_player_does_not_overwrite_your_own_position():
    """GSI keeps sending `player` while you spectate, but it is somebody else."""
    store = GameStateStore()
    store.update(
        {
            "provider": {"steamid": "76561198000000000"},
            "player": {
                "steamid": "76561198000000000",
                "name": "noodle",
                "position": "10.0, 20.0, 30.0",
            },
        }
    )
    store.update(
        {
            "provider": {"steamid": "76561198000000000"},
            "player": {"steamid": "76561198999999999", "name": "someone else",
                       "position": "900.0, 900.0, 900.0"},
        }
    )
    assert store.player.position == Position(x=10.0, y=20.0, z=30.0)


@pytest.mark.asyncio
async def test_being_asked_where_you_are_bypasses_the_cooldown():
    engine = build_engine(**{"snitch.enabled": True, "behavior.cooldown_seconds": 600})
    await engine.handle_message(chat(text="hello"))
    reply = await engine.handle_message(chat(text="yo where are you"))
    assert reply is not None and reply.delivered


@pytest.mark.asyncio
async def test_timed_announcement_goes_out_and_is_not_answered_as_input():
    engine = build_engine(
        **{"snitch.enabled": True, "snitch.announce_interval": 0.01, "snitch.reveal_health": True}
    )
    engine.game_state.update(
        {
            "provider": {"steamid": "1"},
            "map": {"name": "de_dust2", "phase": "live"},
            "player": {"steamid": "1", "name": "noodle", "state": {"health": 70},
                       "position": "0.0, 0.0, 0.0"},
        }
    )
    engine.last_announce_at -= 5
    await engine.maybe_announce()
    assert [text for text, _ in engine._sender.sent] == ["i have 70 hp"]
    assert engine.echo.is_echo("i have 70 hp")


@pytest.mark.asyncio
async def test_nothing_is_announced_while_snitching_is_off():
    engine = build_engine(**{"snitch.announce_interval": 0.01})
    engine.last_announce_at -= 5
    await engine.maybe_announce()
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_the_bot_owns_up_once_when_the_match_ends():
    engine = build_engine()
    engine.game_state.update(
        {"provider": {"steamid": "1"}, "map": {"name": "de_dust2", "phase": "gameover"}}
    )
    await engine.maybe_reveal()
    await engine.maybe_reveal()

    sent = [text for text, _ in engine._sender.sent]
    assert len(sent) == 1
    assert "github.com/Oopsiez/cs2-llama-chatbot" in sent[0]


@pytest.mark.asyncio
async def test_nothing_is_revealed_mid_match():
    engine = build_engine()
    engine.game_state.update(
        {"provider": {"steamid": "1"}, "map": {"name": "de_dust2", "phase": "live"}}
    )
    await engine.maybe_reveal()
    assert not engine._sender.sent


@pytest.mark.asyncio
async def test_the_next_match_gets_its_own_reveal():
    engine = build_engine()
    for phase in ("gameover", "live", "gameover"):
        engine.game_state.update(
            {"provider": {"steamid": "1"}, "map": {"name": "de_dust2", "phase": phase}}
        )
        await engine.maybe_reveal()
    assert len(engine._sender.sent) == 2


@pytest.mark.asyncio
async def test_the_reveal_can_be_turned_off():
    engine = build_engine(**{"reveal.enabled": False})
    engine.game_state.update(
        {"provider": {"steamid": "1"}, "map": {"name": "de_dust2", "phase": "gameover"}}
    )
    await engine.maybe_reveal()
    assert not engine._sender.sent
