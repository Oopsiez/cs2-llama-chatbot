from cs2bot.config import AppConfig
from cs2bot.models import ChatChannel, ChatMessage, LifeState, LocalPlayer
from cs2bot.persona import PRESETS, build_system_prompt, build_turns


def message(**kwargs) -> ChatMessage:
    base = {"raw": "raw", "sender": "enemy", "text": "ez", "channel": ChatChannel.ALL,
            "sender_state": LifeState.ALIVE}
    base.update(kwargs)
    return ChatMessage(**base)


def prompt(config: AppConfig, recent: list[str] | None = None) -> str:
    return build_system_prompt(
        config, LocalPlayer(), LifeState.ALIVE, message(), "noodle", recent
    )


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


def test_turns_carry_the_recent_replies_into_the_system_turn():
    config = AppConfig()
    turns = build_turns(
        config, LocalPlayer(), LifeState.ALIVE, message(), [], "noodle", ["nice shot"]
    )
    assert turns[0].role == "system" and "nice shot" in turns[0].content
    assert turns[-1].content == "enemy: ez"
