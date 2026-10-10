"""Saying a reply out loud over the team's voice channel.

CS2 has no console command that talks, so the bot speaks the way a player does: it synthesises
the line with the Windows speech engine, plays it into a *virtual microphone* (a VB-Audio
Cable: the bot plays into "CABLE Input", CS2 is told its microphone is "CABLE Output") and
holds the push-to-talk key for as long as the clip lasts. Nothing here reaches into the game.
"""

from __future__ import annotations

import asyncio
import io
import math
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..novelty import similarity
from ..output.keyboard import hold
from . import clone, engines, kokoro, tts
from .audio import com_apartment, loopback_missing

# The Windows speech engine (System.Speech) is reached through PowerShell so the frozen exe
# needs no extra package or model download; the voice is whatever Windows has installed.
_SYNTH = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:CS2BOT_VOICE) { try { $s.SelectVoice($env:CS2BOT_VOICE) } catch {} }
$s.Rate = [int]$env:CS2BOT_RATE
$s.SetOutputToWaveFile($env:CS2BOT_WAV)
$s.Speak($env:CS2BOT_TEXT)
$s.Dispose()
"""
_LIST_VOICES = r"""
Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |
  ForEach-Object { $_.VoiceInfo.Name }
"""


def speaking_missing() -> str:
    """Why the bot cannot talk here, or empty when it can."""
    if sys.platform != "win32":
        return "talking holds a key and plays into a Windows audio device, so it only works on Windows"
    return loopback_missing()


def uses_windows_voice(voice: str) -> bool:
    """Whether `speak_voice` names a Windows System.Speech voice ("windows:Microsoft Zira Desktop")."""
    return voice.startswith(tts.WINDOWS_PREFIX)


ENGINES = ("piper", "kokoro", "windows") + tuple(e.id for e in engines.ENGINES)


def render(text: str, voice: str = "", rate: int = 0, engine: str = "piper") -> tuple[list[float], int]:
    """Samples + rate for `text` from the chosen engine: Piper (quick), Kokoro (most human) or Windows."""
    if engine == "windows" or uses_windows_voice(voice) or (tts.piper_missing() and sys.platform == "win32"):
        return wav_samples(synthesise(text, voice.removeprefix(tts.WINDOWS_PREFIX), rate))
    if engine == "kokoro" and not kokoro.kokoro_missing():
        return kokoro.synthesise(text, voice or kokoro.DEFAULT_VOICE, rate)
    if engines.find(engine) is not None:
        return engines.synthesise(engine, text, voice, rate)
    return tts.synthesise(text, voice or tts.DEFAULT_VOICE, rate)


def installed_voices() -> list[str]:
    """Names of the Windows voices available to speak with ("Microsoft Zira Desktop", ...)."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_VOICES],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def synthesise(text: str, voice: str = "", rate: int = 0) -> bytes:
    """A 16-bit WAV of `text` from the Windows speech engine."""
    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / "say.wav"
        env = {
            "CS2BOT_TEXT": text,
            "CS2BOT_VOICE": voice,
            "CS2BOT_RATE": str(max(-10, min(10, rate))),
            "CS2BOT_WAV": str(wav),
        }
        import os

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SYNTH],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env={**os.environ, **env},
        )
        if result.returncode != 0 or not wav.exists():
            raise RuntimeError(result.stderr.strip() or "the Windows speech engine produced nothing")
        return wav.read_bytes()


def wav_samples(data: bytes) -> tuple[list[float], int]:
    """Mono float samples and the sample rate of a 16-bit PCM WAV."""
    with wave.open(io.BytesIO(data)) as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
    import array

    pcm = array.array("h")
    pcm.frombytes(frames[: len(frames) - len(frames) % 2])
    mono = [pcm[i] / 32768.0 for i in range(0, len(pcm), channels)]
    return mono, rate


CABLE_RATE = 48000  # what VB-Cable and CS2's voice path expect; other rates come out wavy


def resample(samples: list[float], rate: int, target: int) -> list[float]:
    """Linear resample to `target` Hz; the engines render at 22.05 or 24 kHz."""
    if rate == target or not samples:
        return samples
    import numpy as np

    data = np.asarray(samples, dtype="float32")
    count = int(round(len(data) * target / rate))
    points = np.linspace(0, len(data) - 1, count)
    return np.interp(points, np.arange(len(data)), data).astype("float32").tolist()


def play_targets(device_id: str = "", monitor: bool = False, monitor_device: str = "") -> list[str]:
    """Where a clip goes: the chosen device, plus the monitor speakers when the player wants
    to hear it too. Blank already means the default speakers, so it is never played twice."""
    if device_id and monitor and monitor_device != device_id:
        return [device_id, monitor_device]
    return [device_id]


def find_speaker(sc: Any, target: str) -> Any:
    """The output device for a saved id or name; a device id changes when the driver is
    reinstalled, so fall back to the name (CABLE Input ...) before giving up."""
    try:
        return sc.get_speaker(target)
    except Exception:
        wanted = target.casefold()
        for speaker in sc.all_speakers():
            if wanted in str(speaker.name).casefold() or wanted == str(speaker.id).casefold():
                return speaker
        names = ", ".join(str(s.name) for s in sc.all_speakers()) or "none"
        raise RuntimeError(f"output device '{target}' is not there (found: {names})") from None


def describe(samples: list[float], rate: int, device: str) -> str:
    """What was played and how loud: a silent clip and a wrong device both read as "spoken"
    otherwise, which is exactly the report that cannot be debugged."""
    seconds = len(samples) / rate if rate else 0.0
    peak = max((abs(x) for x in samples), default=0.0)
    level = f"{20 * math.log10(peak):.0f} dB" if peak > 0 else "silent"
    return f"{seconds:.1f} s, peak {level}, into '{device}'"


def play(
    samples: list[float],
    rate: int,
    device_id: str = "",
    monitor: bool = False,
    monitor_device: str = "",
    resample_48k: bool = False,
) -> str:
    """Play samples on an output device; blank means the default speakers.

    With `monitor`, the same clip also plays on `monitor_device` (blank = default speakers) at
    the same time, so the player hears what the bot is saying into the virtual microphone. A
    monitor that fails, or that turns out to be the same device as the virtual microphone, is
    reported rather than silently skipped. Returns what played where (`describe`).
    """
    import numpy as np
    import soundcard as sc

    if not samples:
        raise RuntimeError("the voice engine produced no audio - pick another voice or engine")
    if resample_48k:
        samples, rate = resample(samples, rate, CABLE_RATE), CABLE_RATE
    data = np.asarray(samples, dtype="float32")
    problems: list[str] = []
    played: list[str] = []

    def resolve(target: str) -> Any:
        return sc.default_speaker() if not target else find_speaker(sc, target)

    def one(target: str, main: bool) -> None:
        try:
            with com_apartment():
                speaker = resolve(target)
                if not main and str(speaker.id) == str(resolve(device_id).id):
                    problems.append(
                        "monitor skipped: the default speakers ARE the virtual microphone - "
                        "pick your real speakers/headset under 'Also play on'"
                    )
                    return
                speaker.play(data, samplerate=rate)
                if main:
                    played.append(describe(samples, rate, str(speaker.name)))
        except Exception as exc:
            if main:
                raise
            problems.append(f"monitor failed on '{target or 'default speakers'}': {exc}")

    targets = play_targets(device_id, monitor, monitor_device)
    extra = [threading.Thread(target=one, args=(t, False), daemon=True) for t in targets[1:]]
    for thread in extra:
        thread.start()
    one(targets[0], True)
    for thread in extra:
        thread.join()
    if problems:
        raise MonitorError("; ".join(problems), played[0] if played else "")
    return played[0] if played else ""


class MonitorError(RuntimeError):
    """The clip reached the virtual microphone but the player's own copy did not play."""

    def __init__(self, problem: str, played: str = "") -> None:
        super().__init__(problem)
        self.played = played


@dataclass
class Speaker:
    """Talks over push-to-talk: synthesise, hold the key, play into the virtual mic, release."""

    device: str = ""
    monitor: bool = True  # also play on the monitor speakers so the player hears it
    monitor_device: str = ""  # blank = default speakers
    resample: bool = False  # 48 kHz for the cable; some headset drivers play that back as silence
    talk_key: str = "k"
    engine: str = "piper"
    voice: str = ""
    rate: int = 0
    lead_seconds: float = 0.25  # CS2 opens the mic a beat after the key goes down
    said: int = 0
    last_text: str = ""
    last_error: str = ""
    last_spoke_at: float = 0.0
    talk_started_at: float = 0.0
    echo_grace_seconds: float = 2.0  # the mix reaches the capture a little after the clip ends
    recent: list[tuple[str, float]] = field(default_factory=list)  # (text, said_at)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def talking(self) -> bool:
        return self.talk_started_at > self.last_spoke_at

    def was_talking(self, started: float, ended: float, now: float | None = None) -> bool:
        """Whether the bot's clip was playing (or had just finished) anywhere in `started..ended`."""
        if not self.talk_started_at:
            return False
        now = time.time() if now is None else now
        end = (now if self.talking else self.last_spoke_at) + self.echo_grace_seconds
        return started <= end and ended >= self.talk_started_at

    def heard_itself(
        self, text: str, heard_at: float, seconds: float = 0.0, now: float | None = None
    ) -> bool:
        """Whether a transcript is the bot's own voice coming back through the speakers/cable.

        Two tells: the audio overlapped a clip the bot was playing, or the words are what it
        just said. Either way it is not a teammate, and answering it would be a conversation
        with itself.
        """
        now = time.time() if now is None else now
        started = heard_at - seconds
        if self.talk_started_at and started <= (self.last_spoke_at or now) + self.echo_grace_seconds:
            if heard_at >= self.talk_started_at:
                return True
        self.recent = [(said, at) for said, at in self.recent if now - at < 60]
        return any(similarity(text, said) >= 0.6 for said, _ in self.recent)

    async def say(self, text: str) -> tuple[bool, str]:
        """Speak `text` over the team voice channel. `(spoken, detail)`."""
        missing = speaking_missing()
        if missing:
            self.last_error = missing
            return False, missing
        async with self._lock:
            self.recent.append((text, time.time()))
            warning = ""
            try:
                played = await asyncio.to_thread(self._speak, text)
            except MonitorError as exc:
                warning, played = str(exc), exc.played
            except Exception as exc:  # a device error must show in the panel, not a 500
                self.last_error = f"{type(exc).__name__}: {exc}"
                return False, self.last_error
            finally:
                self.last_spoke_at = time.time()
        self.said += 1
        self.last_text = text
        self.last_error = warning
        detail = f"spoken {played}" if played else "spoken"
        return True, f"{detail} - {warning}" if warning else detail

    def _speak(self, text: str) -> str:
        samples, rate = render(text, self.voice, self.rate, self.engine)
        # Only playback counts as talking: a slow engine can take seconds to render, and the
        # listener must not be muted for that.
        self.talk_started_at = time.time()
        with hold(self.talk_key):
            time.sleep(self.lead_seconds)
            played = play(samples, rate, self.device, self.monitor, self.monitor_device, self.resample)
            time.sleep(0.15)
        return f"{played}; held {self.talk_key} for {time.time() - self.talk_started_at:.1f} s"

    def status(self) -> dict[str, object]:
        return {
            "said": self.said,
            "last_said": self.last_text,
            "last_spoke_at": self.last_spoke_at,
            "speak_error": self.last_error,
            "speak_supported": not speaking_missing(),
            "speak_unsupported_reason": speaking_missing(),
            "tts": tts.status(),
            "kokoro": kokoro.status(),
            "engines": engines.status(),
            "clone": clone.info(),
        }
