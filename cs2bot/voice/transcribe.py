"""Turning an utterance into text with a local Whisper model.

`faster-whisper` runs the model on the CPU in int8 by default, which keeps a `small` model at
roughly real time on a gaming machine while CS2 has the GPU. The model itself is not shipped in
the installer - it is a few hundred megabytes and most of them are languages nobody here needs -
so it is fetched once on first use and cached; `model_is_cached` is what lets the panel say
"downloading" instead of looking frozen.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol, cast

# What Whisper writes when it is handed silence or noise: subtitle-scraped boilerplate from its
# training data. These are dropped before anything reaches the bot.
HALLUCINATIONS = frozenset(
    {
        "you",
        "thank you",
        "thanks for watching",
        "thanks for watching!",
        "thank you for watching",
        "bye",
        "bye.",
        "okay",
        ".",
        "..",
        "...",
        "[music]",
        "[applause]",
        "[silence]",
        "subs by www.zeoranger.co.uk",
        "thanks very much",
        "thank you very much",
        "i appreciate it",
        "alright",
        "all right",
        "see you",
        "see you next time",
        "goodbye",
        "the end",
        "so",
        "yeah",
        "hmm",
        "mm",
    }
)

# A segment Whisper itself is unsure of: likely silence, hum or gunfire, not a teammate.
NO_SPEECH_LIMIT = 0.5
LOGPROB_LIMIT = -0.9


# `faster-whisper` ships no type information; this is the part of it that is used.
class _Segment(Protocol):
    text: str
    no_speech_prob: float
    avg_logprob: float


class _WhisperModel(Protocol):
    def transcribe(
        self,
        audio: object,
        *,
        language: str | None,
        beam_size: int,
        vad_filter: bool,
        condition_on_previous_text: bool,
        no_speech_threshold: float,
        log_prob_threshold: float,
    ) -> tuple[Iterable[_Segment], object]: ...


class Transcriber(Protocol):
    """Anything that can turn 16 kHz mono samples into text."""

    def transcribe(self, samples: Sequence[float]) -> str: ...


def whisper_missing() -> str:
    """Empty when the speech model can run here, otherwise why it cannot."""
    try:
        import faster_whisper  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on the machine
        return f"faster-whisper is not installed ({exc})"
    try:
        import numpy  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on the machine
        return f"numpy is not installed ({exc})"
    return ""


def cache_dir() -> Path:
    """Where the downloaded model lands, following Hugging Face's own environment variables."""
    for variable in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if value := os.environ.get(variable):
            return Path(value)
    if home := os.environ.get("HF_HOME"):
        return Path(home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


# Where faster-whisper fetches each name from (its own table), so the cache check can find them.
MODEL_REPOS = {
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "distil-medium.en": "Systran/faster-distil-whisper-medium.en",
    "distil-small.en": "Systran/faster-distil-whisper-small.en",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}


def model_is_cached(name: str) -> bool:
    """Whether the model is already on disk, so first use will not stall on a download."""
    if Path(name).is_dir():  # a local model directory
        return True
    repo = MODEL_REPOS.get(name, f"Systran/faster-whisper-{name}")
    folder = cache_dir() / f"models--{repo.replace('/', '--')}"
    return folder.is_dir() and any(folder.rglob("model.bin"))


class WhisperTranscriber:
    """A `faster-whisper` model, loaded on first use."""

    def __init__(
        self,
        model: str = "small.en",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        beam_size: int = 1,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self._model: _WhisperModel | None = None
        self.note = ""

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Build the model, downloading it if this machine has never run it before."""
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        try:
            model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        except RuntimeError as exc:
            if self.device == "cpu" or not wants_cuda_runtime(exc):
                raise
            # CTranslate2 saw an NVIDIA card and reached for CUDA 12 libraries that are not
            # shipped: the CPU runs a small model fine, and the GPU is CS2's anyway.
            self.note = f"speech runs on the CPU ({exc})"
            self.device = "cpu"
            model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        self._model = cast(_WhisperModel, model)

    def transcribe(self, samples: Sequence[float]) -> str:
        import numpy as np

        self.load()
        model = self._model
        if model is None:  # pragma: no cover - load() either builds it or raises
            raise RuntimeError("the speech model failed to load")
        segments, _ = model.transcribe(
            np.asarray(samples, dtype=np.float32),
            language=self.language or None,
            beam_size=self.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            no_speech_threshold=NO_SPEECH_LIMIT,
            log_prob_threshold=LOGPROB_LIMIT,
        )
        kept = [
            segment.text
            for segment in segments
            if segment.no_speech_prob < NO_SPEECH_LIMIT and segment.avg_logprob > LOGPROB_LIMIT
        ]
        return clean(" ".join(kept))


def wants_cuda_runtime(exc: BaseException) -> bool:
    """Whether a load failure is CTranslate2 missing CUDA DLLs (cublas, cudnn) rather than a bad model."""
    text = str(exc).casefold()
    return any(word in text for word in ("cublas", "cudnn", "cuda", "cannot be loaded"))


def _is_boilerplate(sentence: str) -> bool:
    return sentence.casefold().strip(" .!?,") in {phrase.strip(" .!?") for phrase in HALLUCINATIONS}


def clean(text: str) -> str:
    """Trim Whisper's output and throw away the things it says about silence.

    Silence does not only produce one stock phrase: it produces a string of them ("Thanks very
    much. I appreciate it. Bye. Bye."), so every sentence is checked, and a transcript that is
    mostly stock phrases, or the same sentence over and over, is thrown away whole.
    """
    text = " ".join(text.split())
    if not text:
        return ""
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip(" .!?,")]
    if not sentences:
        return ""
    boilerplate = sum(1 for part in sentences if _is_boilerplate(part))
    if boilerplate * 2 >= len(sentences):
        return ""
    distinct = {part.casefold().strip(" .!?,") for part in sentences}
    if len(sentences) >= 3 and len(distinct) * 2 <= len(sentences):
        return ""
    return " ".join(part for part in sentences if not _is_boilerplate(part))
