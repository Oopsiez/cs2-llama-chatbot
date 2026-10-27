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


def test_leaked_chat_template_tokens_are_never_typed_or_spoken():
    from cs2bot.humanize import humanize

    assert humanize("rush b<|im_end|>", literacy=100, max_chars=0) == "rush b"
    assert "<|" not in humanize("<|start_header_id|>ok <|eot_id|>", literacy=100, max_chars=160)


def test_no_cap_means_no_cap():
    from cs2bot.humanize import humanize

    text = " ".join(["word"] * 60)
    assert humanize(text, literacy=100, max_chars=0) == text
    assert len(humanize(text, literacy=100, max_chars=0).split()) == 60


def test_the_bots_own_name_is_stripped_off_the_front_of_a_reply():
    from cs2bot.humanize import humanize

    assert humanize("Big Dog 99: push b now", literacy=100, max_chars=0, name="Big Dog 99") == "push b now"
    assert humanize("[big dog 99] - rotate", literacy=100, max_chars=0, name="Big Dog 99") == "rotate"
    kept = humanize("heads up: they are b", literacy=100, max_chars=0, name="Big Dog 99")
    assert kept == "heads up: they are b"


def test_spoken_lines_are_cut_after_the_sentence_limit():
    from cs2bot.humanize import first_sentences

    speech = "Push b now. They are all a! Trust me, I saw three. Go go go."
    assert first_sentences(speech, 2) == "Push b now. They are all a!"
    assert first_sentences(speech, 1) == "Push b now."
    assert first_sentences(speech, 0) == speech
    assert first_sentences("no punctuation at all", 1) == "no punctuation at all"


def test_spoken_sentence_cut_keeps_a_stub_with_what_follows():
    from cs2bot.humanize import first_sentences

    assert first_sentences("Nice! Rotate b now, he's one. Go go go.", 1) == "Nice! Rotate b now, he's one."
    assert first_sentences("Okay. Okay. Save this one.", 1) == "Okay. Okay. Save this one."


def test_spoken_lines_are_cut_after_the_word_limit():
    from cs2bot.humanize import first_words

    line = "Push b now, he's lit. Trust me I saw three of them go that way and nobody is a."
    assert first_words(line, 0) == line
    assert first_words(line, 40) == line
    assert first_words(line, 8) == "Push b now, he's lit."
    assert first_words("one two three four five six seven eight", 5) == "one two three four five..."
    assert first_words("one two three four, five six", 4) == "one two three four..."


def test_the_bot_never_bleeps_itself():
    from cs2bot.humanize import humanize, uncensor

    assert uncensor("what the f*** was that, s**t") == "what the fuck was that, shit"
    assert uncensor("F***ing hell [expletive] *sighs*") == "Fucking hell sighs"
    assert uncensor("no stars here") == "no stars here"
    assert humanize("holy s*** he *is* one", literacy=100, max_chars=0) == "holy shit he is one"
