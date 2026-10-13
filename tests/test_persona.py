import random

import pytest

from cs2bot import persona, playbook
from cs2bot.config import AppConfig, PersonaSettings
from cs2bot.models import ChatChannel, ChatMessage, LifeState, LocalPlayer, Team
from cs2bot.persona import (
    PRESETS,
    build_strategy_turns,
    build_system_prompt,
    build_turns,
    state_note,
)


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


def prompt(config: AppConfig, recent: list[str] | None = None) -> str:
    return build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, message(), "noodle", recent)


def test_new_presets_are_selectable():
    for name in ("Coach", "Gaming Therapist", "Angry and Toxic"):
        assert PRESETS[name].name == name
        assert PRESETS[name].description and PRESETS[name].style_notes


def test_literacy_and_game_iq_appear_independently():
    config = AppConfig()
    config.behavior.literacy = 5
    config.behavior.intelligence = 95
    smart_but_illiterate = prompt(config)

    config.behavior.literacy = 95
    config.behavior.intelligence = 5
    literate_but_clueless = prompt(config)

    assert smart_but_illiterate != literate_but_clueless


def test_unprompted_advice_is_opt_in():
    config = AppConfig()
    assert "even when nobody asked" not in prompt(config)
    config.behavior.unprompted_advice = True
    assert "even when nobody asked" in prompt(config)


def test_recent_replies_are_listed_only_when_avoiding_repeats():
    config = AppConfig()
    assert "rotate b now" in prompt(config, ["rotate b now"])
    config.behavior.avoid_repeats = False
    assert "rotate b now" not in prompt(config, ["rotate b now"])


def test_each_dead_alive_combination_gets_its_own_instruction():
    notes = {
        (bot, sender): state_note(bot, message(sender_state=sender))
        for bot in (LifeState.ALIVE, LifeState.DEAD)
        for sender in (LifeState.ALIVE, LifeState.DEAD)
    }
    assert all(notes.values())
    assert len(set(notes.values())) == 4
    assert state_note(LifeState.ALIVE, message(sender_state=LifeState.UNKNOWN)) is None


def test_dead_state_guidance_can_be_switched_off():
    config = AppConfig()
    dead = message(sender_state=LifeState.DEAD)
    assert "dead" in build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, dead, "noodle")

    config.dead_alive.adapt_replies = False
    without = build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, dead, "noodle")
    assert state_note(LifeState.ALIVE, dead) not in without


def test_turns_carry_the_recent_replies_into_the_system_turn():
    config = AppConfig()
    turns = build_turns(config, LocalPlayer(), LifeState.ALIVE, message(), [], "noodle", ["nice shot"])
    assert turns[0].role == "system" and "nice shot" in turns[0].content
    assert turns[-1].content == "enemy: ez"


def test_the_strategy_prompt_hands_the_model_the_call_verbatim():
    config = AppConfig()
    strategy = playbook.pick("de_mirage", Team.T, rng=random.Random(0))
    assert strategy is not None

    turns = build_strategy_turns(
        config,
        LocalPlayer(map_name="de_mirage", team=Team.T),
        strategy,
        asked_by="Gavin",
        names=["kenny"],
    )
    system, user = turns[0], turns[-1]
    assert system.role == "system"
    assert "Change nothing tactical" in system.content
    assert "kenny " in user.content  # the first job goes out with a teammate's name on it
    assert "Mirage" in system.content and "T" in system.content
    assert all(step in user.content for step in strategy.steps)
    assert f"{len(strategy.steps)} lines in total" in system.content
    assert "Gavin" in user.content


@pytest.mark.parametrize(
    "asked,name",
    [
        ("toxic", "Angry and Toxic"),
        ("Angry and Toxic", "Angry and Toxic"),
        ("coach", "Coach"),
        ("therapist", "Gaming Therapist"),
        ("silver", "Silver Enjoyer"),
    ],
)
def test_finding_a_preset_by_the_name_people_type(asked, name):
    found = persona.find_persona(asked, {})
    assert found is not None and found.name == name


def test_a_saved_persona_wins_over_a_preset_of_the_same_name():
    mine = PersonaSettings(name="Coach", description="You are my coach.")
    found = persona.find_persona("coach", {"Coach": mine})
    assert found is mine


def test_an_unknown_persona_is_not_guessed_at():
    assert persona.find_persona("astronaut", {}) is None
    assert persona.find_persona("  ", {}) is None


def test_a_persona_is_written_from_an_order():
    from cs2bot.config import PersonaSettings
    from cs2bot.persona import persona_from_order

    current = PersonaSettings(game_aware=False, dead_notes="salty")
    made = persona_from_order("you are now a friendly operator who never swears", current)
    assert made.description.startswith("You are a friendly operator who never swears.")
    assert made.name == "a friendly operator who"
    assert made.game_aware is False and made.dead_notes == ""


def test_unprompted_lines_are_asked_for_in_the_live_persona():
    from cs2bot.config import AppConfig
    from cs2bot.gamestate import LocalPlayer
    from cs2bot.models import LifeState
    from cs2bot.persona import build_initiative_turns, persona_from_order

    config = AppConfig()
    config.persona = persona_from_order("you are now a friendly operator", config.persona)
    turns = build_initiative_turns(config, LocalPlayer(), LifeState.ALIVE, "round_start", [])
    assert "friendly operator" in turns[0].content
    assert "new round" in turns[-1].content and "your team" in turns[-1].content


def test_spoken_lines_get_the_talking_directive_instead_of_the_typed_one():
    config = AppConfig()
    config.persona.max_reply_chars = 0
    spoken = prompt(config)
    assert "talking out loud" in spoken and "chat message only" not in spoken
    assert "Sound like these" in spoken
    config.persona.max_reply_chars = 120
    typed = prompt(config)
    assert "chat message only" in typed and "talking out loud" not in typed
