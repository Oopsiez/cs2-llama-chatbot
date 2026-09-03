from cs2bot.humanize import humanize, intelligence_directive, sampling_for_intelligence


def test_low_intelligence_is_short_and_lowercase():
    text = "Honestly, that was an excellent execute onto the B site; well played everyone."
    result = humanize(text, intelligence=5, max_chars=160, seed=1)
    assert result == result.lower()
    assert "," not in result and "." not in result
    assert len(result.split()) <= 6


def test_high_intelligence_preserves_text():
    text = "Rotate B, they are stacking A with two smokes."
    assert humanize(text, intelligence=95, max_chars=160, seed=1) == text


def test_strips_name_prefix_and_stage_directions():
    assert humanize('*laughs* Bot: nice one', intelligence=90, max_chars=160, seed=0) == "nice one"


def test_respects_character_limit():
    result = humanize("word " * 80, intelligence=100, max_chars=40, seed=0)
    assert len(result) <= 40


def test_sampling_gets_hotter_as_intelligence_drops():
    dumb = sampling_for_intelligence(0)
    smart = sampling_for_intelligence(100)
    assert dumb["temperature"] > smart["temperature"]
    assert dumb["max_tokens"] < smart["max_tokens"]


def test_directive_changes_with_level():
    assert intelligence_directive(0) != intelligence_directive(100)
