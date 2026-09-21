import threading
import time

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
    assert listener._run.pending.get_nowait() == [2.0]


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
    assert config.voice.enabled is False
    assert config.voice.model == "small.en"


def test_a_message_is_typed_chat_unless_it_says_otherwise():
    typed = ChatMessage(raw="r", sender="gavin", text="70 ramp", channel=ChatChannel.TEAM)
    assert typed.source is MessageSource.CHAT
    assert not typed.is_voice
    spoken = ChatMessage(
        raw="r", sender="voice", text="70 ramp",
        channel=ChatChannel.TEAM, source=MessageSource.VOICE,
    )
    assert spoken.is_voice
    assert spoken.model_dump(mode="json")["source"] == "voice"
