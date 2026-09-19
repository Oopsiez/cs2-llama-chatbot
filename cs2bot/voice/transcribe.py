"""Turning an utterance into text with a local Whisper model.

`faster-whisper` runs the model on the CPU in int8 by default, which keeps a `small` model at
roughly real time on a gaming machine while CS2 has the GPU. The model itself is not shipped in
the installer - it is a few hundred megabytes and most of them are languages nobody here needs -
so it is fetched once on first use and cached; `model_is_cached` is what lets the panel say
"downloading" instead of looking frozen.
"""

from __future__ import annotations

import os
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
    }
)


# `faster-whisper` ships no type information; this is the part of it that is used.
class _Segment(Protocol):
    text: str


class _WhisperModel(Protocol):
    def transcribe(
        self,
        audio: object,
        *,
        language: str | None,
        beam_size: int,
        vad_filter: bool,
        condition_on_previous_text: bool,
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


def model_is_cached(name: str) -> bool:
    """Whether the model is already on disk, so first use will not stall on a download."""
    if Path(name).is_dir():  # a local model directory
        return True
    folder = cache_dir() / f"models--Systran--faster-whisper-{name}"
    return folder.is_dir() and any(folder.rglob("model.bin"))


class WhisperTranscriber:
    """A `faster-whisper` model, loaded on first use."""

    def __init__(
        self,
        model: str = "small.en",
        *,
        device: str = "auto",
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

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Build the model, downloading it if this machine has never run it before."""
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = cast(
            _WhisperModel,
            WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type),
        )

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
        )
        return clean(" ".join(segment.text for segment in segments))


def clean(text: str) -> str:
    """Trim Whisper's output and throw away the things it says about silence."""
    text = " ".join(text.split())
    if text.casefold().strip(" .!?") in {phrase.strip(" .!?") for phrase in HALLUCINATIONS}:
        return ""
    return text
