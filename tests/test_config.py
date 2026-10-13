

def test_stale_voice_cutoff_defaults_to_ninety_seconds_and_zero_means_never():
    from cs2bot.config import VoiceSettings

    assert VoiceSettings().stale_seconds == 90.0
    assert VoiceSettings(stale_seconds=0).stale_seconds == 0
