

def test_any_playback_failure_is_reported_instead_of_raised(monkeypatch):
    import asyncio

    import cs2bot.voice.speak as module

    def boom(text: str) -> None:
        raise IndexError("no such device")

    monkeypatch.setattr(module, "speaking_missing", lambda: "")
    speaker = module.Speaker()
    monkeypatch.setattr(speaker, "_speak", boom)
    spoken, detail = asyncio.run(speaker.say("mic check"))
    assert spoken is False
    assert "IndexError" in detail and "no such device" in detail
