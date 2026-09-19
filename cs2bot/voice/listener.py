"""The voice pipeline: speakers -> utterances -> text, off the event loop.

Two threads, not one. Recording must never stop to think - the sound card keeps filling its
buffer whether or not anybody is reading it - so the capture thread only cuts the stream into
utterances and hands them over, and a second thread does the slow part of running Whisper. If
the model falls behind, the oldest waiting utterance is dropped: in a match, a transcript that
arrives thirty seconds late is worse than no transcript.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

from . import audio
from .segment import Segmenter
from .transcribe import Transcriber, WhisperTranscriber, model_is_cached, whisper_missing

log = logging.getLogger(__name__)

# How many finished utterances may wait for the model before the oldest is dropped.
PENDING_LIMIT = 3


@dataclass(frozen=True)
class Utterance:
    """Something that was said over voice comms."""

    text: str
    seconds: float
    heard_at: float = field(default_factory=time.time)


BlockSource = Callable[[], Iterator[list[float]]]


class VoiceListener:
    """Hears the speakers, transcribes speech, queues the text for the engine."""

    def __init__(
        self,
        *,
        device: str = "",
        transcriber: Transcriber | None = None,
        source: BlockSource | None = None,
        segmenter: Segmenter | None = None,
        model_name: str = "small.en",
    ) -> None:
        self.device = device
        self.model_name = model_name
        self._transcriber = transcriber
        self._source = source or (lambda: audio.blocks(device))
        self._segmenter = segmenter or Segmenter(audio.SAMPLE_RATE)
        self._pending: queue.Queue[Sequence[float]] = queue.Queue(maxsize=PENDING_LIMIT)
        self._heard: queue.Queue[Utterance] = queue.Queue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.error: str = ""
        self.loading: bool = False
        self.utterances_heard = 0
        self.last_text = ""
        self.last_heard_at = 0.0

    # ---- lifecycle --------------------------------------------------------------

    @property
    def running(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def start(self) -> None:
        """Begin listening. A listener that has already failed stays stopped.

        The poll loop calls this every tick, and a machine with no loopback device will fail
        every time; retrying it four times a second would bury the real error under its own
        repeats. `restart` is the way back.
        """
        if self.running or self.error:
            return
        self._stop.clear()
        self._segmenter.reset()
        self._threads = [
            threading.Thread(target=self._listen, name="cs2bot-voice-listen", daemon=True),
            threading.Thread(target=self._transcribe, name="cs2bot-voice-whisper", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []

    def restart(self) -> None:
        """Try again after a failure - the sound card may have come back."""
        self.stop()
        self.error = ""
        self.start()

    def drain(self) -> list[Utterance]:
        """Everything heard since the last call, for the poll loop to act on."""
        out = []
        while True:
            try:
                out.append(self._heard.get_nowait())
            except queue.Empty:
                return out

    # ---- threads ----------------------------------------------------------------

    def _listen(self) -> None:
        try:
            for block in self._source():
                if self._stop.is_set():
                    break
                for utterance in self._segmenter.feed(block):
                    self._offer(utterance)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("voice capture stopped: %s", self.error)

    def _offer(self, samples: Sequence[float]) -> None:
        """Queue an utterance, throwing away the stalest one if the model is behind."""
        while True:
            try:
                self._pending.put_nowait(samples)
                return
            except queue.Full:
                try:
                    self._pending.get_nowait()
                except queue.Empty:  # pragma: no cover - raced with the worker
                    pass

    def _transcribe(self) -> None:
        while not self._stop.is_set():
            try:
                samples = self._pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                text = self._model().transcribe(samples)
            except Exception as exc:
                # A model that cannot run once cannot run on the next utterance either, so
                # stop the whole listener rather than failing on every word spoken all match.
                self.error = f"{type(exc).__name__}: {exc}"
                log.warning("transcription failed: %s", self.error)
                self._stop.set()
                return
            finally:
                self.loading = False
            if not text:
                continue
            self.utterances_heard += 1
            self.last_text = text
            self.last_heard_at = time.time()
            self._heard.put(
                Utterance(text=text, seconds=len(samples) / audio.SAMPLE_RATE)
            )

    def _model(self) -> Transcriber:
        if self._transcriber is None:
            missing = whisper_missing()
            if missing:
                raise RuntimeError(missing)
            self.loading = not model_is_cached(self.model_name)
            self._transcriber = WhisperTranscriber(self.model_name)
        return self._transcriber

    # ---- introspection ----------------------------------------------------------

    def status(self) -> dict[str, object]:
        return {
            "running": self.running,
            "device": self.device,
            "model": self.model_name,
            "model_ready": model_is_cached(self.model_name),
            "downloading": self.loading,
            "heard": self.utterances_heard,
            "last_text": self.last_text,
            "last_heard_at": self.last_heard_at,
            "error": self.error,
        }
