from cs2bot.humanize import game_iq_directive, humanize, literacy_directive, sampling_for


def test_low_literacy_is_short_and_lowercase():
    text = "Honestly, that was an excellent execute onto the B site; well played everyone."
    result = humanize(text, literacy=5, max_chars=160, seed=1)
    assert result == result.lower()
    assert "," not in result and "." not in result
    assert len(result.split()) <= 6


def test_high_literacy_preserves_text():
    text = "Rotate B, they are stacking A with two smokes."
    assert humanize(text, literacy=95, max_chars=160, seed=1) == text


def test_strips_name_prefix_and_stage_directions():
    assert humanize("*laughs* Bot: nice one", literacy=90, max_chars=160, seed=0) == "nice one"


def test_respects_character_limit():
    result = humanize("word " * 80, literacy=100, max_chars=40, seed=0)
    assert len(result) <= 40


def test_game_iq_drives_temperature_and_literacy_drives_length():
    assert sampling_for(60, 0)["temperature"] > sampling_for(60, 100)["temperature"]
    assert sampling_for(0, 60)["max_tokens"] < sampling_for(100, 60)["max_tokens"]
    # The dials are independent: writing well does not make the bot play well.
    assert sampling_for(0, 100)["temperature"] == sampling_for(100, 100)["temperature"]


def test_directives_change_with_level():
    assert literacy_directive(0) != literacy_directive(100)
    assert game_iq_directive(0) != game_iq_directive(100)
    assert literacy_directive(50) != game_iq_directive(50)
