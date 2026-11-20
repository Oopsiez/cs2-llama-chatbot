def test_stale_voice_cutoff_defaults_to_ninety_seconds_and_zero_means_never():
    from cs2bot.config import VoiceSettings

    assert VoiceSettings().stale_seconds == 90.0
    assert VoiceSettings(stale_seconds=0).stale_seconds == 0


def test_chat_log_falls_back_to_con_logfile(tmp_path):
    import os

    from cs2bot.config import chat_log_path

    console = tmp_path / "console.log"
    assert chat_log_path(str(console)) is None
    own = tmp_path / "cs2bot_chat.log"
    own.write_text("x\n", encoding="utf-8")
    assert chat_log_path(str(console)) == own
    console.write_text("y\n", encoding="utf-8")
    os.utime(own, (1, 1))
    assert chat_log_path(str(console)) == console
    assert chat_log_path("") is None
