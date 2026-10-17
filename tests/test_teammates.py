from cs2bot.config import AppConfig
from cs2bot.engine import Engine
from cs2bot.models import ChatChannel, ChatMessage, LifeState, LocalPlayer
from cs2bot.persona import PRESETS, build_system_prompt, find_persona


def _msg(sender="Gavin", channel=ChatChannel.ALL, text="nice shot"):
    return ChatMessage(raw=text, sender=sender, text=text, channel=channel)


def test_clean_slate_does_not_know_it_is_in_a_game():
    config = AppConfig()
    config.persona = PRESETS["Clean slate"]
    player = LocalPlayer(map_name="de_mirage")
    prompt = build_system_prompt(config, player, LifeState.DEAD, _msg(), own_name="Bot")
    assert "mirage" not in prompt.casefold()
    assert "DEAD" not in prompt
    assert "Counter-Strike" not in prompt
    assert "Gavin wrote the message" in prompt
    assert find_persona("blank", {}) is PRESETS["Clean slate"]


def test_a_toxic_persona_is_told_to_be_nice_to_a_teammate():
    config = AppConfig()
    config.persona = PRESETS["Angry and Toxic"]
    config.teammates.stance = "nice"
    team = build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, _msg(), is_teammate=True)
    enemy = build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, _msg(), is_teammate=False)
    assert "Gavin is on YOUR team" in team and "friendly" in team
    assert "YOUR team" not in enemy


def test_custom_teammate_instructions_go_in_verbatim_and_same_adds_nothing():
    config = AppConfig()
    config.teammates.stance = "custom"
    config.teammates.custom = "Hype them up after every kill."
    prompt = build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, _msg(), is_teammate=True)
    assert "Hype them up after every kill." in prompt
    config.teammates.stance = "same"
    prompt = build_system_prompt(config, LocalPlayer(), LifeState.ALIVE, _msg(), is_teammate=True)
    assert "YOUR team" not in prompt


def test_engine_recognises_teammates_from_team_chat_and_voice():
    engine = Engine(AppConfig())
    assert engine.is_teammate(_msg(channel=ChatChannel.TEAM))
    assert not engine.is_teammate(_msg("Rat"))
    engine.roster.observe(_msg("Rat", ChatChannel.TEAM))
    assert engine.is_teammate(_msg("Rat"))
    assert not engine.is_teammate(_msg("rat2"))
