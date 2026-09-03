from cs2bot.novelty import avoid_note, is_repetitive, similarity


def test_identical_and_reworded_lines_score_high():
    assert similarity("nice shot", "nice shot!") == 1.0
    assert similarity("nice shot dude", "dude nice shot") > 0.9


def test_different_lines_score_low():
    assert similarity("rotate b now", "buy armour and a smoke") < 0.4


def test_filler_words_alone_do_not_make_lines_similar():
    assert similarity("i was the one", "you are it") < 0.5


def test_is_repetitive_returns_the_echoed_line():
    recent = ["ez", "rotate b now"]
    assert is_repetitive("rotate b now!", recent, 0.75) == "rotate b now"
    assert is_repetitive("save for next round", recent, 0.75) is None


def test_avoid_note_lists_previous_lines():
    note = avoid_note(["ez", "  ", "gg"])
    assert note is not None and '"ez"' in note and '"gg"' in note
    assert avoid_note([]) is None
