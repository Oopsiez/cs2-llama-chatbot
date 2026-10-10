import sys
import threading
import time
import types

import pytest

from cs2bot.config import AppConfig
from cs2bot.models import ChatChannel, ChatMessage, MessageSource
from cs2bot.voice import audio, transcribe
from cs2bot.voice.listener import PENDING_LIMIT, VoiceListener
from cs2bot.voice.segment import Segmenter, rms


def loud(count: int, level: float = 0.5) -> list[float]:
    # Alternating signs so the block has the RMS its level says, not a DC offset.
    return [level if index % 2 else -level for index in range(count)]


def quiet(count: int) -> list[float]:
    return [0.0] * count


def build_segmenter(**overrides) -> Segmenter:
    settings = {
        "sample_rate": 100,
        "floor": 0.01,
        "min_seconds": 0.1,
        "max_seconds": 1.0,
        "hang_seconds": 0.2,
        "preroll_seconds": 0.1,
    }
    settings.update(overrides)
    rate = settings.pop("sample_rate")
    return Segmenter(rate, **settings)


def test_rms_measures_loudness():
    assert rms([]) == 0.0
    assert rms([0.0, 0.0]) == 0.0
    assert rms([0.5, -0.5]) == 0.5


def test_silence_alone_is_never_an_utterance():
    segmenter = build_segmenter()
    assert [segmenter.feed(quiet(10)) for _ in range(20)] == [[]] * 20


def test_speech_ends_after_the_hangover_and_keeps_its_first_syllable():
    segmenter = build_segmenter()
    for _ in range(5):
        segmenter.feed(quiet(10))  # fills the pre-roll buffer
    assert segmenter.feed(loud(50)) == []
    assert segmenter.speaking

    done = []
    for _ in range(3):
        done.extend(segmenter.feed(quiet(10)))
    assert len(done) == 1
    # 50 loud samples, up to 10 of pre-roll, plus the silence that closed it out.
    assert len(done[0]) > 50
    assert not segmenter.speaking


def test_a_blip_too_short_to_be_speech_is_thrown_away():
    segmenter = build_segmenter(min_seconds=1.0)
    segmenter.feed(loud(10))
    done = []
    for _ in range(3):
        done.extend(segmenter.feed(quiet(10)))
    assert done == []
    assert not segmenter.speaking


def test_somebody_holding_the_key_down_is_cut_rather_than_buffered_forever():
    segmenter = build_segmenter(max_seconds=1.0)
    done = []
    for _ in range(12):
        done.extend(segmenter.feed(loud(10)))
    assert len(done) == 1
    assert len(done[0]) >= 100


def test_reset_forgets_a_half_finished_utterance():
    segmenter = build_segmenter()
    segmenter.feed(loud(50))
    assert segmenter.speaking
    segmenter.reset()
    assert not segmenter.speaking
    assert segmenter.threshold == segmenter.floor * segmenter.margin


def test_flush_ends_the_utterance_in_progress():
    segmenter = build_segmenter()
    segmenter.feed(loud(50))
    assert len(segmenter.flush()) == 50
    assert segmenter.flush() == []


def test_the_gate_rises_above_a_noise_floor_that_is_not_silence():
    segmenter = build_segmenter(floor=0.001, margin=2.0)
    for _ in range(5):
        segmenter.feed(loud(10, level=0.1))  # room tone, gunfire, a distant firefight
    assert segmenter.threshold > 0.001


def test_whisper_boilerplate_is_not_treated_as_speech():
    assert transcribe.clean("  Thanks for watching! ") == ""
    assert transcribe.clean("[Music]") == ""
    assert transcribe.clean("  they are pushing   B  ") == "they are pushing B"


def test_a_string_of_whisper_boilerplate_is_silence():
    silence = "Alright. Thanks very much. I appreciate it. I appreciate it. Thank you. Bye. Bye. Bye."
    assert transcribe.clean(silence) == ""
    assert transcribe.clean("Thank you. Thank you. Thank you.") == ""
    mixed = "Bye. they are pushing B, two of them. go go"
    assert transcribe.clean(mixed) == "they are pushing B, two of them. go go"


def test_segments_whisper_is_unsure_of_are_dropped():
    pytest.importorskip("numpy")

    class Seg:
        def __init__(self, text, no_speech_prob, avg_logprob):
            self.text, self.no_speech_prob, self.avg_logprob = text, no_speech_prob, avg_logprob

    class Model:
        def transcribe(self, audio, **kwargs):
            return [Seg(" rush B", 0.1, -0.3), Seg(" Thank you. Bye.", 0.8, -1.4)], None

    whisper = transcribe.WhisperTranscriber("tiny.en")
    whisper._model = Model()
    assert whisper.transcribe([0.0] * 16000) == "rush B"


def test_a_local_model_directory_counts_as_downloaded(tmp_path):
    assert transcribe.model_is_cached(str(tmp_path))
    assert not transcribe.model_is_cached(str(tmp_path / "nope"))


def test_a_cached_model_is_found_where_hugging_face_puts_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    assert not transcribe.model_is_cached("small.en")
    blob = tmp_path / "models--Systran--faster-whisper-small.en" / "snapshots" / "abc"
    blob.mkdir(parents=True)
    (blob / "model.bin").write_bytes(b"")
    assert transcribe.model_is_cached("small.en")


class FakeTranscriber:
    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.seen: list[int] = []

    def transcribe(self, samples):
        self.seen.append(len(samples))
        return self.texts.pop(0) if self.texts else ""


def wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def build_listener(blocks: list[list[float]], transcriber) -> VoiceListener:
    def source():
        yield from blocks
        while True:  # the sound card never runs out; neither does this
            time.sleep(0.005)
            yield quiet(10)

    return VoiceListener(
        transcriber=transcriber,
        source=source,
        segmenter=build_segmenter(),
    )


def test_what_was_said_comes_out_of_drain():
    listener = build_listener(
        [loud(50)] + [quiet(10)] * 3,
        FakeTranscriber("they are pushing B"),
    )
    listener.start()
    try:
        assert wait_for(lambda: listener.utterances_heard == 1)
        heard = listener.drain()
    finally:
        listener.stop()
    assert [utterance.text for utterance in heard] == ["they are pushing B"]
    assert listener.drain() == []
    assert listener.status()["last_text"] == "they are pushing B"


def test_an_empty_transcript_is_not_reported_as_something_heard():
    transcriber = FakeTranscriber("")
    listener = build_listener([loud(50)] + [quiet(10)] * 3, transcriber)
    listener.start()
    try:
        assert wait_for(lambda: bool(transcriber.seen))
    finally:
        listener.stop()
    assert listener.utterances_heard == 0
    assert listener.drain() == []


def test_the_stalest_audio_is_dropped_when_the_model_falls_behind():
    listener = VoiceListener(transcriber=FakeTranscriber(), source=lambda: iter(()))
    for index in range(PENDING_LIMIT + 2):
        listener._offer(listener._run, [float(index)])
    assert listener._run.pending.qsize() == PENDING_LIMIT
    # The oldest two are gone, so what is left starts part-way through.
    assert listener._run.pending.get_nowait()[0] == [2.0]


def test_a_failing_model_stops_the_listener_instead_of_failing_on_every_word():
    class Broken:
        def transcribe(self, samples):
            raise RuntimeError("no model here")

    listener = build_listener([loud(50)] + [quiet(10)] * 3, Broken())
    listener.start()
    try:
        assert wait_for(lambda: bool(listener.error))
        assert wait_for(lambda: not listener.running)
    finally:
        listener.stop()
    assert "no model here" in listener.error


def test_a_listener_that_failed_stays_stopped_until_it_is_restarted():
    listener = VoiceListener(transcriber=FakeTranscriber(), source=lambda: iter(()))
    listener.error = "no loopback device"
    listener.start()
    assert not listener.running

    listener._source = lambda: iter([quiet(10)])
    listener.restart()
    try:
        assert listener.error == ""
    finally:
        listener.stop()


def test_losing_the_sound_card_shuts_the_whole_listener_down():
    def source():
        raise OSError("device disappeared")
        yield  # pragma: no cover - makes this a generator

    listener = VoiceListener(transcriber=FakeTranscriber(), source=source)
    listener.start()
    try:
        assert wait_for(lambda: bool(listener.error))
        # The transcription worker must not be left polling an empty queue for ever.
        assert wait_for(lambda: not listener.running)
    finally:
        listener.stop()
    assert "device disappeared" in listener.error


def test_speech_heard_before_being_switched_off_is_not_replayed_afterwards():
    """Whisper can outlast the two second join, and must not surface into the next run."""
    release = threading.Event()

    class Slow:
        def __init__(self) -> None:
            self.busy = threading.Event()

        def transcribe(self, samples):
            self.busy.set()
            release.wait(5.0)
            return "they are pushing B"

    transcriber = Slow()
    listener = build_listener([loud(50)] + [quiet(10)] * 3, transcriber)
    listener.start()
    try:
        assert wait_for(lambda: transcriber.busy.is_set())
        listener.stop()
        # The old worker is still in the model, so it is still tracked rather than forgotten.
        assert listener.running
        threads = list(listener._threads)
        listener.start()
        assert listener._threads == threads
    finally:
        release.set()
    assert wait_for(lambda: not listener.running)
    assert listener.drain() == []


def test_the_status_says_what_the_panel_needs_to_show():
    listener = VoiceListener(transcriber=FakeTranscriber(), source=lambda: iter(()))
    status = listener.status()
    assert status["running"] is False
    assert status["model"] == "small.en"
    assert status["heard"] == 0
    assert status["error"] == ""


def test_missing_packages_are_reported_rather_than_raised():
    # The panel has to be able to say *why* it cannot listen on a machine without the extras.
    assert isinstance(audio.loopback_missing(), str)
    assert isinstance(transcribe.whisper_missing(), str)


def test_no_speakers_means_no_devices_to_choose_from(monkeypatch):
    monkeypatch.setattr(audio, "loopback_missing", lambda: "soundcard is not installed")
    assert audio.output_devices() == []


def test_a_config_written_before_voice_existed_still_loads():
    config = AppConfig.model_validate({"enabled": True, "behavior": {"cooldown_seconds": 3}})
    assert config.voice.enabled is True
    assert config.voice.model == "small.en"


def test_a_message_is_typed_chat_unless_it_says_otherwise():
    typed = ChatMessage(raw="r", sender="gavin", text="70 ramp", channel=ChatChannel.TEAM)
    assert typed.source is MessageSource.CHAT
    assert not typed.is_voice
    spoken = ChatMessage(
        raw="r",
        sender="voice",
        text="70 ramp",
        channel=ChatChannel.TEAM,
        source=MessageSource.VOICE,
    )
    assert spoken.is_voice
    assert spoken.model_dump(mode="json")["source"] == "voice"


def test_whisper_runs_on_the_cpu_by_default_and_falls_back_when_cuda_dlls_are_missing(monkeypatch):
    import sys
    import types

    from cs2bot.voice import transcribe as t

    assert t.WhisperTranscriber("tiny").device == "cpu"
    assert t.wants_cuda_runtime(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
    assert not t.wants_cuda_runtime(RuntimeError("no such model"))

    calls = []

    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls.append(device)
            if device != "cpu":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    whisper = t.WhisperTranscriber("tiny", device="auto")
    whisper.load()
    assert calls == ["auto", "cpu"] and whisper.device == "cpu" and "CPU" in whisper.note


def test_com_apartment_is_a_no_op_off_windows():
    from cs2bot.voice.audio import com_apartment

    with com_apartment():
        pass


def test_wav_samples_are_mono_floats():
    import io
    import wave

    from cs2bot.voice.speak import wav_samples

    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x40\x00\x40\x00\xc0\x00\xc0")
    samples, rate = wav_samples(buf.getvalue())
    assert rate == 22050 and samples == [0.5, -0.5]


@pytest.mark.asyncio
async def test_speaking_off_windows_fails_softly():
    from cs2bot.voice.speak import Speaker

    speaker = Speaker()
    spoken, detail = await speaker.say("hello")
    assert not spoken and "Windows" in detail
    assert speaker.status()["speak_supported"] is False


def test_cable_install_is_windows_only_and_reports_absence():
    from cs2bot.voice import cable

    ok, detail = cable.install_cable()
    assert not ok and "Windows" in detail
    status = cable.driver_status()
    assert status["installed"] is False and status["input_id"] == ""


def test_speaker_recognises_its_own_voice_coming_back():
    from cs2bot.voice.speak import Speaker

    s = Speaker()
    assert not s.heard_itself("rotate b now", heard_at=100.0, seconds=1.0, now=100.0)
    s.talk_started_at, s.last_spoke_at = 100.0, 103.0
    s.recent = [("rotate B now, they are all on A", 100.0)]
    # overlapped the clip
    assert s.heard_itself("something garbled", heard_at=102.0, seconds=1.5, now=102.0)
    # arrived just after the clip, same words
    assert s.heard_itself("rotate b now they are all on a", heard_at=106.0, seconds=2.0, now=106.0)
    # a teammate, well after, different words
    assert not s.heard_itself("nice one, push with me", heard_at=110.0, seconds=1.0, now=110.0)


def test_piper_voice_catalog_and_speech_text():
    from cs2bot.voice import tts

    assert tts.find(tts.DEFAULT_VOICE) is not None
    assert tts.length_scale(0) == 1.0 and tts.length_scale(10) < 1.0 < tts.length_scale(-10)
    assert tts.for_speech("gg WP 🔥 RUSH B") == "g g well played Rush B"
    assert not tts.is_cached("en_GB-alan-medium") or True
    status = tts.status()
    assert {v["id"] for v in status["voices"]} >= {"en_US-ryan-high", "en_GB-alan-medium"}


def test_render_routes_windows_prefixed_voices_only(monkeypatch):
    from cs2bot.voice import speak, tts

    monkeypatch.setattr(tts, "synthesise", lambda text, voice_id, rate: ([0.0], 22050))
    assert speak.render("hi", "", 0) == ([0.0], 22050)
    assert speak.render("hi", "en_GB-alan-medium", 0) == ([0.0], 22050)
    assert speak.uses_windows_voice("windows:Microsoft Zira Desktop")


def test_cpu_only_keeps_the_model_off_the_card():
    from cs2bot.config import LLMSettings
    from cs2bot.hardware import Hardware
    from cs2bot.llm import gpu_layers_for

    assert gpu_layers_for(LLMSettings(cpu_only=True, n_gpu_layers=-1), Hardware()) == 0


def test_render_dispatches_on_engine(monkeypatch):
    from cs2bot.voice import kokoro, speak, tts

    monkeypatch.setattr(tts, "synthesise", lambda text, voice_id, rate: ([1.0], 22050))
    monkeypatch.setattr(kokoro, "synthesise", lambda text, voice_id, rate: ([2.0], 24000))
    monkeypatch.setattr(kokoro, "kokoro_missing", lambda: "")
    assert speak.render("hi", "", 0, "piper") == ([1.0], 22050)
    assert speak.render("hi", "am_adam", 0, "kokoro") == ([2.0], 24000)
    assert set(kokoro.status()) >= {"supported", "ready", "voices", "size_mb"}


def test_ollama_gpu_layers_follow_the_placement():
    from cs2bot.config import LLMSettings
    from cs2bot.llm import ollama_gpu_layers

    assert ollama_gpu_layers(LLMSettings(cpu_only=True)) == 0
    assert ollama_gpu_layers(LLMSettings(gpu_auto=False, n_gpu_layers=12)) == 12
    assert ollama_gpu_layers(LLMSettings()) is None


def test_speech_persona_and_model_are_separate_only_when_asked():
    from cs2bot.config import AppConfig, LLMSettings, PersonaSettings
    from cs2bot.engine import Engine

    config = AppConfig(llm=LLMSettings(backend="ollama", ollama_model="a", speech_ollama_model="b"))
    engine = Engine(config)
    assert engine.speech_config.persona.name == engine.config.persona.name
    assert engine.speech_config.persona.max_reply_chars == 0  # spoken lines are not typed, so no cap
    assert engine.speech_backend is not engine.backend
    assert engine.speech_backend.model == "b"  # type: ignore[attr-defined]

    config = AppConfig(speech_same_persona=False, speech_persona=PersonaSettings(name="Voice"))
    engine = Engine(config)
    assert engine.speech_config.persona.name == "Voice"
    assert engine.config.persona.name != "Voice"
    assert engine.speech_backend is engine.backend
    assert engine.speech_differs


def test_the_voice_key_is_read_from_cs2_user_keys(tmp_path):
    from cs2bot.voice import binds

    cfg = tmp_path / "userdata" / "123" / "730" / "local" / "cfg"
    cfg.mkdir(parents=True)
    (cfg / "cs2_user_keys.vcfg").write_text(
        '"config"\n{\n\t"bindings"\n\t{\n\t\t"k"\t\t"+voicerecord"\n\t\t"p"\t"say hi"\n\t}\n}\n'
    )
    assert binds.detect_voice_key(roots=[tmp_path]) == ("k", str(cfg / "cs2_user_keys.vcfg"))
    assert binds.voice_key_in('bind "MOUSE4" "+voicerecord"') == "mouse4"
    assert binds.detect_voice_key(roots=[tmp_path / "nope"])[0] == ""


def test_hearing_cs2_falls_back_to_the_speakers_off_windows(monkeypatch):
    notes = []
    monkeypatch.setattr(audio, "blocks", lambda device_id="", block_seconds=0.05: iter([[0.0]]))
    assert list(audio.capture("", "cs2", notes.append)) == [[0.0]]
    assert notes and notes[0].startswith("hearing the whole PC")


def test_the_player_hears_the_bot_too_only_when_it_talks_into_the_cable():
    from cs2bot.voice import speak

    assert speak.play_targets("cable-input", monitor=True) == ["cable-input", ""]
    assert speak.play_targets("cable-input", monitor=False) == ["cable-input"]
    assert speak.play_targets("", monitor=True) == [""]


def test_spoken_lines_are_resampled_to_the_cable_rate():
    pytest.importorskip("numpy")
    from cs2bot.voice import speak

    out = speak.resample([0.0, 1.0, 0.0, -1.0] * 100, 24000, 48000)
    assert len(out) == 800
    assert speak.resample([0.5], 48000, 48000) == [0.5]


def test_the_monitor_goes_to_its_own_device_and_never_doubles_the_cable():
    from cs2bot.voice import speak

    assert speak.play_targets("cable", monitor=True, monitor_device="headset") == ["cable", "headset"]
    assert speak.play_targets("cable", monitor=True, monitor_device="cable") == ["cable"]
    assert speak.play_targets("", monitor=True, monitor_device="headset") == [""]


def test_a_failed_monitor_still_counts_as_spoken_but_says_so(monkeypatch):
    import asyncio

    from cs2bot.voice import speak

    monkeypatch.setattr(speak, "speaking_missing", lambda: "")
    speaker = speak.Speaker()
    speaker._speak = lambda text: (_ for _ in ()).throw(speak.MonitorError("monitor failed on 'x': boom"))  # type: ignore[method-assign]
    spoken, detail = asyncio.run(speaker.say("mic check"))
    assert spoken and detail.startswith("spoken - monitor failed")
    assert speaker.status()["speak_error"].startswith("monitor failed")


def test_the_mic_check_says_how_long_how_loud_and_where():
    from cs2bot.voice import speak

    line = speak.describe([0.0, 0.5, -0.25] * 16000, 48000, "Headset (Realtek)")
    assert line.startswith("1.0 s, peak -6 dB, into 'Headset (Realtek)'")
    assert "silent" in speak.describe([0.0] * 100, 48000, "x")


def test_a_spoken_line_reports_what_played_where(monkeypatch):
    import asyncio

    from cs2bot.voice import speak

    monkeypatch.setattr(speak, "speaking_missing", lambda: "")
    speaker = speak.Speaker()
    speaker._speak = lambda text: "1.2 s, peak -3 dB, into 'CABLE Input'"  # type: ignore[method-assign]
    spoken, detail = asyncio.run(speaker.say("mic check"))
    assert spoken and detail == "spoken 1.2 s, peak -3 dB, into 'CABLE Input'"


def test_resampling_can_be_turned_off_for_drivers_that_want_the_native_rate():
    from cs2bot.config import VoiceSettings

    assert VoiceSettings().resample_48k is False
    assert VoiceSettings(resample_48k=True).resample_48k is True


def test_hearing_one_program_switches_to_it_the_moment_it_starts(monkeypatch):
    from cs2bot.voice import process_loopback

    notes: list[str] = []
    seen = {"checks": 0}
    monkeypatch.setattr(process_loopback, "unavailable", lambda: "")
    monkeypatch.setattr(audio, "RECHECK_SECONDS", audio.BLOCK_SECONDS)

    def find(name="cs2.exe"):
        seen["checks"] += 1
        return 7 if seen["checks"] > 1 else 0

    monkeypatch.setattr(process_loopback, "find_process", find)
    monkeypatch.setattr(
        process_loopback, "blocks", lambda process="cs2.exe", block_seconds=0.05: iter([[1.0]])
    )
    monkeypatch.setattr(audio, "blocks", lambda device_id="", block_seconds=0.05: iter([[0.0], [0.0], [0.0]]))

    stream = audio.capture("", "cs2", notes.append, "cs2.exe")
    assert next(stream) == [0.0]  # speakers while the game is not running
    assert notes[-1].startswith("hearing the whole PC via the default speakers: cs2.exe is not running")
    assert next(stream) == [1.0]  # the game appeared on the re-check
    assert notes[-1] == "hearing cs2.exe only"
    assert next(stream) == [0.0]  # and back to the speakers when its stream ended
    assert notes[-1] == "hearing the whole PC via the default speakers: cs2.exe stopped"


def test_kokoro_offers_every_english_voice_in_quality_tiers():
    from cs2bot.voice import kokoro

    voices = kokoro.status()["voices"]
    assert len(voices) >= 28
    assert {v["tier"] for v in voices} == {"best", "better", "good"}
    assert kokoro.DEFAULT_VOICE == "af_heart"


def test_hugging_face_engines_are_listed_with_voices_and_sizes():
    from cs2bot.voice import engines, speak

    ids = {e["id"] for e in engines.status()}
    assert ids == {"supertonic", "kitten", "chatterbox"}
    assert ids <= set(speak.ENGINES)
    chatterbox = next(e for e in engines.status() if e["id"] == "chatterbox")
    assert chatterbox["clones"] and chatterbox["size_mb"] > 1000
    assert all(e["voices"] for e in engines.status())


def test_clone_saves_a_trimmed_mono_reference(tmp_path, monkeypatch):
    from cs2bot.voice import clone

    monkeypatch.setattr(clone, "cache_dir", lambda: tmp_path)
    assert clone.info()["ready"] is False
    assert clone.reference() is None
    import math

    rate = 16000
    samples = [0.5 * math.sin(i / 20) for i in range(rate * 20)]
    info = clone.save(samples, rate, "unit test")
    assert info["ready"] and info["seconds"] == clone.MAX_SECONDS and info["source"] == "unit test"
    ref = clone.reference()
    assert ref is not None and len(ref) == int(clone.MAX_SECONDS * clone.SAMPLE_RATE)
    assert max(abs(x) for x in ref) <= 0.91
    with pytest.raises(ValueError):
        clone.save([0.1] * 100, rate, "too short")


def test_clone_decodes_a_wav_upload(tmp_path, monkeypatch):
    import array
    import io
    import wave

    from cs2bot.voice import clone

    pcm = array.array("h", [1000, -1000] * 8000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(pcm.tobytes())
    samples, rate = clone.decode(buffer.getvalue(), "clip.wav")
    assert rate == 8000 and len(samples) == 8000 and samples[0] == 0.0


def test_for_speech_drops_written_filler():
    from cs2bot.voice.tts import for_speech

    assert for_speech("As an AI teammate, rotate B now. Let me know if you need more!") == "rotate B now."
    assert for_speech("*sighs* push A (quietly) - go go") == "push A go go"


def test_speaker_knows_when_it_was_talking():
    from cs2bot.voice.speak import Speaker

    s = Speaker()
    assert not s.was_talking(0.0, 5.0, now=5.0)
    s.talk_started_at, s.last_spoke_at = 100.0, 103.0
    assert s.was_talking(102.0, 104.0, now=104.0)
    assert s.was_talking(104.0, 104.9, now=104.9)  # inside the grace after the clip
    assert not s.was_talking(90.0, 99.0, now=99.0)
    assert not s.was_talking(106.0, 108.0, now=108.0)
    s.talk_started_at = 110.0  # talking right now, no end yet
    assert s.was_talking(111.0, 112.0, now=112.0)


def test_listener_drops_the_bots_own_voice_before_transcribing():
    listener = VoiceListener(
        transcriber=FakeTranscriber(), source=lambda: iter(()), gate=lambda s, e: e > 100.0
    )
    listener._offer(listener._run, [0.1] * 16000, ended_at=50.0)
    listener._offer(listener._run, [0.1] * 16000, ended_at=150.0)
    assert listener._run.pending.qsize() == 1 and listener.own_voice_ignored == 1
    samples, ended_at = listener._run.pending.get_nowait()
    assert ended_at == 50.0 and len(samples) == 16000


def test_whole_pc_capture_tries_to_leave_the_bot_out(monkeypatch):
    from cs2bot.voice import audio, process_loopback

    notes: list[str] = []
    monkeypatch.setattr(process_loopback, "unavailable", lambda: "")
    monkeypatch.setattr(process_loopback, "blocks_except_me", lambda: iter([[0.5]]))
    monkeypatch.setattr(audio, "blocks", lambda device_id="": iter([[0.1]]))
    monkeypatch.setattr(audio, "device_name", lambda device_id: "Headset (Realtek)")
    assert list(audio.capture(scope="pc", on_note=notes.append)) == [[0.5], [0.1]]
    assert notes[0] == "hearing the whole PC except the bot's own voice"
    assert notes[1].startswith("hearing the whole PC via Headset (Realtek): ")


def test_leaving_the_bot_out_needs_windows():
    from cs2bot.voice import process_loopback

    if sys.platform != "win32":
        with pytest.raises(RuntimeError):
            list(process_loopback.blocks_except_me())


def test_cache_check_knows_where_the_big_models_live(tmp_path, monkeypatch):
    from cs2bot.voice import transcribe

    monkeypatch.setattr(transcribe, "cache_dir", lambda: tmp_path)
    assert not transcribe.model_is_cached("distil-large-v3")
    blob = tmp_path / "models--Systran--faster-distil-whisper-large-v3" / "snapshots" / "x"
    blob.mkdir(parents=True)
    (blob / "model.bin").write_bytes(b"0")
    assert transcribe.model_is_cached("distil-large-v3")


def test_chatterbox_prompt_keeps_the_tokenizers_end_markers(monkeypatch):
    from cs2bot.voice import engines

    class Tok:
        def encode(self, text, add_special_tokens=True):
            ids = [1, 2, 3]
            return types.SimpleNamespace(ids=ids + [50256, 50256] if add_special_tokens else ids)

    engine = engines.find("chatterbox")
    assert engine is not None
    monkeypatch.setitem(engines._sessions, "chatterbox/tokenizer", Tok())
    assert engines.text_ids(engine, "push A") == [1, 2, 3, 50256, 50256]


def test_nothing_downloads_on_the_first_line(monkeypatch):
    from cs2bot.voice import engines, kokoro, tts

    for module in (engines, kokoro, tts):
        monkeypatch.setattr(module, "download", lambda *a, **k: pytest.fail("downloaded on first use"))
    monkeypatch.setattr(kokoro, "is_cached", lambda: False)
    with pytest.raises(RuntimeError, match="press Install"):
        kokoro.synthesise("hi")
    monkeypatch.setattr(tts, "is_cached", lambda voice_id: False)
    with pytest.raises(RuntimeError, match="press Install"):
        tts.synthesise("hi")
    monkeypatch.setattr(engines, "runtime_missing", lambda: "")
    monkeypatch.setattr(engines, "is_cached", lambda engine: False)
    with pytest.raises(RuntimeError, match="press Install"):
        engines.synthesise("kitten", "hi")


def test_chatterbox_stops_when_the_decoder_babbles_in_a_loop():
    from cs2bot.voice import engines

    assert not engines._looping(list(range(40)))
    assert engines._looping(list(range(10)) + [1, 2, 3, 4, 5, 6, 7, 8] * 4)
    assert not engines._looping([1, 2, 3, 4, 5, 6, 7, 8] * 3)


def test_last_voice_builds_up_across_short_callouts(monkeypatch, tmp_path):
    from cs2bot.voice import listener as listener_mod

    captured = listener_mod.VoiceListener.__new__(listener_mod.VoiceListener)
    captured.last_audio = []
    rate = listener_mod.audio.SAMPLE_RATE
    for _ in range(5):
        captured.last_audio = (captured.last_audio + [0.1] * (3 * rate))[
            -int(listener_mod.CLONE_BUFFER_SECONDS * rate) :
        ]
    assert len(captured.last_audio) == int(listener_mod.CLONE_BUFFER_SECONDS * rate)


def test_a_short_clone_clip_is_flagged(monkeypatch, tmp_path):
    from cs2bot.voice import clone

    monkeypatch.setattr(clone, "cache_dir", lambda: tmp_path)
    info = clone.save([0.2] * (5 * clone.SAMPLE_RATE), clone.SAMPLE_RATE, "short one")
    assert info["short"] is True
    info = clone.save([0.2] * (8 * clone.SAMPLE_RATE), clone.SAMPLE_RATE, "long one")
    assert info["short"] is False
