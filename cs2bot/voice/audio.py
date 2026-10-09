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

import ctypes
import sys
import warnings
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
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
    return output_devices_report()[0]


def output_devices_report() -> tuple[list[Device], str]:
    """`(devices, error)` - the error says why the list is empty when it is, so the panel can
    show it instead of a blank drop-down."""
    missing = loopback_missing()
    if missing:
        return [], missing
    import soundcard as sc

    with com_apartment():
        try:
            default = sc.default_speaker()
        except Exception as exc:  # no default output set - the others may still be there
            default = None
            note = f"no default output device ({type(exc).__name__}: {exc})"
        else:
            note = ""
        try:
            speakers = list(sc.all_speakers())
        except Exception as exc:  # pragma: no cover - needs real hardware to fail
            return [], f"could not list output devices ({type(exc).__name__}: {exc})"
    devices: list[Device] = [
        {
            "id": str(speaker.id),
            "name": str(speaker.name),
            "default": default is not None and str(speaker.id) == str(default.id),
        }
        for speaker in speakers
    ]
    if not devices:
        return [], note or "Windows reports no output devices"
    return devices, note


def _microphone(device_id: str) -> _Microphone:
    """The loopback microphone for a speaker id, or for the default speaker if blank."""
    import soundcard as sc

    if not device_id:
        speaker = sc.default_speaker()
        if speaker is None:  # pragma: no cover - no audio hardware at all
            raise RuntimeError("Windows reports no speakers to listen to")
        device_id = str(speaker.id)
    return cast(_Microphone, sc.get_microphone(device_id, include_loopback=True))


COINIT_MULTITHREADED = 0x0
CO_E_NOTINITIALIZED = 0x800401F0


@contextmanager
def com_apartment() -> Iterator[None]:
    """Join this thread to COM for as long as the block runs.

    WASAPI is COM, and COM is per thread: `soundcard` initialises it on whichever thread imports
    it, which is not the capture thread, and Windows answers the first uninitialised call with
    `0x800401f0` (CO_E_NOTINITIALIZED). Only the thread that actually recorded needs this.
    """
    if sys.platform != "win32":
        yield
        return
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
    result = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    initialised = result >= 0  # S_OK or S_FALSE; RPC_E_CHANGED_MODE means somebody else did it
    try:
        yield
    finally:
        if initialised:
            ole32.CoUninitialize()


RECHECK_SECONDS = 2.0  # how often the speakers fallback looks for the program to appear


def capture(
    device_id: str = "",
    scope: str = "cs2",
    on_note: Callable[[str], None] | None = None,
    process: str = "cs2.exe",
) -> Iterator[list[float]]:
    """Blocks of audio from the chosen scope: one program alone when possible, else the speakers.

    The program is usually not running yet when the panel starts, so the speakers fallback keeps
    looking for it and switches over the moment it appears (and back when it quits). `on_note`
    is told what is being heard and why, so the panel can say so.
    """
    note = on_note or (lambda text: None)
    from . import process_loopback

    reason = process_loopback.unavailable()
    if scope != "cs2":
        if not reason:
            note("hearing the whole PC except the bot's own voice")
            try:
                yield from process_loopback.blocks_except_me()
            except Exception as exc:
                reason = f"could not leave out the bot's own voice: {exc}"
        note(f"hearing the whole PC: {reason}")
        yield from blocks(device_id)
        return
    if reason:
        note(f"hearing the whole PC: {reason}")
        yield from blocks(device_id)
        return
    while True:
        if process_loopback.find_process(process):
            note(f"hearing {process} only")
            try:
                yield from process_loopback.blocks(process)
            except Exception as exc:
                reason = f"{process} capture failed: {exc}"
            else:
                reason = f"{process} stopped"
        else:
            reason = f"{process} is not running - listening to the speakers until it is"
        note(f"hearing the whole PC: {reason}")
        yield from speakers_until(device_id, lambda: bool(process_loopback.find_process(process)))


def speakers_until(device_id: str, found: Callable[[], bool]) -> Iterator[list[float]]:
    """The speakers' audio until `found()` says the program to hear is there."""
    every = max(1, int(RECHECK_SECONDS / BLOCK_SECONDS))
    for index, block in enumerate(blocks(device_id), 1):
        yield block
        if index % every == 0 and found():
            return


def blocks(device_id: str = "", block_seconds: float = BLOCK_SECONDS) -> Iterator[list[float]]:
    """Yield mono blocks of what the speakers are playing, forever.

    This blocks on the sound card, so it belongs on a thread of its own.
    """
    missing = loopback_missing()
    if missing:
        raise RuntimeError(missing)
    frames = max(1, int(SAMPLE_RATE * block_seconds))
    # soundcard warns every time the reader is a little late (Whisper or a clip playing hogs the
    # CPU); a few lost milliseconds do not matter to speech, and the warning floods the console.
    warnings.filterwarnings("ignore", message="data discontinuity in recording")
    with com_apartment():
        microphone = _microphone(device_id)
        # Stereo on purpose: WASAPI returns silence or noise for a one-channel loopback stream.
        with microphone.recorder(SAMPLE_RATE, channels=2) as recorder:
            while True:
                data = recorder.record(numframes=frames)
                yield data.mean(axis=1).tolist()
