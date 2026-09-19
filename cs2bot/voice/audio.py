"""Listening to what the speakers are playing.

Windows can hand an application its own output mix back as if it were a microphone (WASAPI
loopback), which is how the bot hears voice comms without opening the real microphone, reading
the game's memory or asking the user to wire up a virtual cable.

Two hard-won details live here. WASAPI records garbage when asked for a single channel, so the
stream is always taken in stereo and averaged down afterwards; and the loopback device is a
*microphone* whose name matches a speaker, which is why devices are listed from the speaker side
and looked up by id.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Protocol, TypedDict, cast

SAMPLE_RATE = 16_000  # what Whisper wants
BLOCK_SECONDS = 0.05


# `soundcard` ships no type information, so the little of it that is used is described here.
class _Samples(Protocol):
    def mean(self, axis: int) -> _Samples: ...
    def tolist(self) -> list[float]: ...


class _Recorder(Protocol):
    def record(self, numframes: int) -> _Samples: ...


class _Microphone(Protocol):
    def recorder(self, samplerate: int, channels: int) -> AbstractContextManager[_Recorder]: ...


class Device(TypedDict):
    id: str
    name: str
    default: bool


def loopback_missing() -> str:
    """Empty when the speakers can be recorded here, otherwise why they cannot."""
    try:
        import soundcard  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on the machine
        return f"soundcard is not installed ({exc})"
    return ""


def output_devices() -> list[Device]:
    """The speakers that can be listened to, with the default one marked."""
    if loopback_missing():
        return []
    import soundcard as sc

    try:
        default = sc.default_speaker()
    except Exception:  # pragma: no cover - no audio hardware at all
        return []
    devices: list[Device] = []
    for speaker in sc.all_speakers():
        devices.append(
            {
                "id": str(speaker.id),
                "name": str(speaker.name),
                "default": default is not None and str(speaker.id) == str(default.id),
            }
        )
    return devices


def _microphone(device_id: str) -> _Microphone:
    """The loopback microphone for a speaker id, or for the default speaker if blank."""
    import soundcard as sc

    if not device_id:
        speaker = sc.default_speaker()
        if speaker is None:  # pragma: no cover - no audio hardware at all
            raise RuntimeError("Windows reports no speakers to listen to")
        device_id = str(speaker.id)
    return cast(_Microphone, sc.get_microphone(device_id, include_loopback=True))


def blocks(device_id: str = "", block_seconds: float = BLOCK_SECONDS) -> Iterator[list[float]]:
    """Yield mono blocks of what the speakers are playing, forever.

    This blocks on the sound card, so it belongs on a thread of its own.
    """
    missing = loopback_missing()
    if missing:
        raise RuntimeError(missing)
    frames = max(1, int(SAMPLE_RATE * block_seconds))
    microphone = _microphone(device_id)
    # Stereo on purpose: WASAPI returns silence or noise for a one-channel loopback stream.
    with microphone.recorder(SAMPLE_RATE, channels=2) as recorder:
        while True:
            data = recorder.record(numframes=frames)
            yield data.mean(axis=1).tolist()
