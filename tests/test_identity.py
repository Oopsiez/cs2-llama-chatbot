from cs2bot.identity import (
    addressed_to,
    detect_name_from_line,
    handle_variants,
    is_same_player,
    normalize_handle,
)


def test_normalize_strips_decoration_and_leet():
    assert normalize_handle("[EZ] xX_N00dle_Xx") == "ezxxnoodlexx"
    assert normalize_handle("Pável") == "pavel"


def test_handle_variants_keeps_words_but_drops_short_fragments():
    variants = handle_variants("[EZ] noodle king", aliases=["nd"])
    assert "noodle" in variants
    assert "king" in variants
    assert "nd" not in variants


def test_is_same_player_ignores_decoration_and_case():
    assert is_same_player("[EZ] Noodle", "noodle", aliases=[])
    assert is_same_player("someone", "noodle", aliases=["someone"])
    assert not is_same_player("noodleking", "noodle")


def test_detect_name_from_cvar_echo_and_command():
    assert detect_name_from_line('"name" = "Oopsiez" ( def. "unnamed" )') == "Oopsiez"
    assert detect_name_from_line('setinfo name "skelly"') == "skelly"
    assert detect_name_from_line('09/03 02:21:00  "name" = "Oopsiez"') == "Oopsiez"
    assert detect_name_from_line("[ALL] someone: hey") is None


def test_detect_rename_only_when_the_old_name_is_ours():
    assert detect_name_from_line("Oopsiez changed name to skelly", known="Oopsiez") == "skelly"
    assert detect_name_from_line("someone changed name to skelly", known="Oopsiez") is None


def test_addressed_by_name_prefix():
    mention = addressed_to("noodle: you awake", "noodle")
    assert mention and mention.reason == "addressed by name"


def test_at_mention_and_inline_name():
    assert addressed_to("@noodle push b", "noodle")
    assert addressed_to("nice one noodle", "noodle")
    assert addressed_to("noodleee wake up", "noodle").reason == "name mentioned"


def test_alias_is_recognised():
    assert addressed_to("ndl smoke please", "[EZ] noodle", aliases=["ndl"])


def test_unrelated_chatter_is_not_addressed():
    assert not addressed_to("who queued this map", "noodle")
    assert not addressed_to("you there?", "noodle")


def test_second_person_counts_only_right_after_the_bot_speaks():
    assert addressed_to("are you serious", "noodle", replying_to_bot=True)
    assert not addressed_to("are you serious", "noodle", replying_to_bot=False)


def test_no_name_configured_still_catches_replies_to_the_bot():
    assert addressed_to("u ok", "", replying_to_bot=True)
    assert not addressed_to("nice shot", "", replying_to_bot=True)
