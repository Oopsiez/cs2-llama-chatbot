"""Cutting the speaker feed into utterances.

Whisper wants a whole sentence, not a stream, so the audio has to be chopped somewhere. The
cut is made on loudness: a run of loud blocks is speech, a long enough gap ends it. Two details
matter in a game, where the noise floor is a firefight rather than a quiet room:

* the gate floats. A fixed threshold either misses a quiet teammate or treats gunfire as talking,
  so the quietest recent audio is taken as the floor and speech has to beat it by a margin.
* the blocks just before the gate opened are kept. Speech is recognised a moment after it starts,
  and without that pre-roll every transcript loses its first syllable.

This module is deliberately plain Python over sequences of samples: the capture backend and the
model both need Windows and a download, and none of this logic should need either to be tested.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence


def rms(block: Sequence[float]) -> float:
    if not block:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in block) / len(block))


class Segmenter:
    """Loudness-gated speech segmenter. Feed it blocks, get back finished utterances."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        *,
        floor: float = 0.006,
        margin: float = 2.5,
        min_seconds: float = 0.45,
        max_seconds: float = 12.0,
        hang_seconds: float = 0.7,
        preroll_seconds: float = 0.4,
    ) -> None:
        self.sample_rate = sample_rate
        self.floor = floor
        self.margin = margin
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.hang_seconds = hang_seconds
        self._preroll: deque[list[float]] = deque()
        self._preroll_seconds = preroll_seconds
        self._preroll_samples = 0
        self._speech: list[float] = []
        self._quiet_samples = 0
        # Seeded high so the first blocks of a match are not all treated as speech.
        self._quietest = floor

    @property
    def speaking(self) -> bool:
        return bool(self._speech)

    @property
    def threshold(self) -> float:
        """What a block has to beat right now to count as somebody talking."""
        return max(self.floor, self._quietest * self.margin)

    def reset(self) -> None:
        self._preroll.clear()
        self._preroll_samples = 0
        self._speech = []
        self._quiet_samples = 0
        self._quietest = self.floor

    def feed(self, block: Sequence[float]) -> list[list[float]]:
        """Add one block of mono samples; return any utterances it completed."""
        if not block:
            return []
        loudness = rms(block)
        self._track_floor(loudness)
        done: list[list[float]] = []

        if loudness >= self.threshold:
            if not self._speech:
                self._speech = [sample for chunk in self._preroll for sample in chunk]
                self._preroll.clear()
                self._preroll_samples = 0
            self._speech.extend(block)
            self._quiet_samples = 0
            if len(self._speech) >= self.max_seconds * self.sample_rate:
                # Somebody is holding the key down - cut it rather than grow forever.
                done.append(self._finish(force=True))
            return [chunk for chunk in done if chunk]

        if self._speech:
            self._speech.extend(block)
            self._quiet_samples += len(block)
            if self._quiet_samples >= self.hang_seconds * self.sample_rate:
                done.append(self._finish())
            return [chunk for chunk in done if chunk]

        self._remember(block)
        return []

    def flush(self) -> list[float]:
        """End the current utterance, if it is long enough to be one."""
        return self._finish() if self._speech else []

    def _finish(self, force: bool = False) -> list[float]:
        speech, self._speech = self._speech, []
        self._quiet_samples = 0
        if not force and len(speech) < self.min_seconds * self.sample_rate:
            return []
        return speech

    def _remember(self, block: Sequence[float]) -> None:
        self._preroll.append(list(block))
        self._preroll_samples += len(block)
        limit = self._preroll_seconds * self.sample_rate
        while self._preroll and self._preroll_samples > limit:
            self._preroll_samples -= len(self._preroll.popleft())

    def _track_floor(self, loudness: float) -> None:
        """Follow the quietest thing we hear, quick to drop and slow to rise.

        Quick to drop so a lull between fights becomes the new floor within a second or two;
        slow to rise so one long burst of gunfire does not deafen the gate for the round.
        """
        if loudness < self._quietest:
            self._quietest = loudness
        else:
            self._quietest += (loudness - self._quietest) * 0.001

