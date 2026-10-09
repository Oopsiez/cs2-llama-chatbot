"""Saying a reply out loud over the team's voice channel.

CS2 has no console command that talks, so the bot speaks the way a player does: it synthesises
the line with the Windows speech engine, plays it into a *virtual microphone* (a VB-Audio
Cable: the bot plays into "CABLE Input", CS2 is told its microphone is "CABLE Output") and
holds the push-to-talk key for as long as the clip lasts. Nothing here reaches into the game.
"""

from __future__ import annotations

import asyncio
import io
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

from ..novelty import similarity
from ..output.keyboard import KeyPressError, hold
from . import kokoro, tts
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


ENGINES = ("piper", "kokoro", "windows")


def render(text: str, voice: str = "", rate: int = 0, engine: str = "piper") -> tuple[list[float], int]:
    """Samples + rate for `text` from the chosen engine: Piper (quick), Kokoro (most human) or Windows."""
    if engine == "windows" or uses_windows_voice(voice) or (tts.piper_missing() and sys.platform == "win32"):
        return wav_samples(synthesise(text, voice.removeprefix(tts.WINDOWS_PREFIX), rate))
    if engine == "kokoro" and not kokoro.kokoro_missing():
        return kokoro.synthesise(text, voice or kokoro.DEFAULT_VOICE, rate)
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


def play_targets(device_id: str = "", monitor: bool = False) -> list[str]:
    """Where a clip goes: the chosen device, plus the default speakers when the player wants
    to hear it too. Blank already means the default speakers, so it is never played twice."""
    if device_id and monitor:
        return [device_id, ""]
    return [device_id]


def play(samples: list[float], rate: int, device_id: str = "", monitor: bool = False) -> None:
    """Play samples on an output device; blank means the default speakers.

    With `monitor`, the same clip also plays on the default speakers at the same time, so the
    player hears what the bot is saying into the virtual microphone.
    """
    import numpy as np
    import soundcard as sc

    data = np.asarray(samples, dtype="float32")

    def one(target: str) -> None:
        with com_apartment():
            speaker = sc.default_speaker() if not target else sc.get_speaker(target)
            speaker.play(data, samplerate=rate)

    targets = play_targets(device_id, monitor)
    extra = [threading.Thread(target=one, args=(t,), daemon=True) for t in targets[1:]]
    for thread in extra:
        thread.start()
    one(targets[0])
    for thread in extra:
        thread.join()


@dataclass
class Speaker:
    """Talks over push-to-talk: synthesise, hold the key, play into the virtual mic, release."""

    device: str = ""
    monitor: bool = True  # also play on the default speakers so the player hears it
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
            self.talk_started_at = time.time()
            self.recent.append((text, self.talk_started_at))
            try:
                await asyncio.to_thread(self._speak, text)
            except (KeyPressError, RuntimeError, OSError) as exc:
                self.last_error = str(exc)
                return False, str(exc)
            finally:
                self.last_spoke_at = time.time()
        self.said += 1
        self.last_text = text
        self.last_error = ""
        return True, "spoken"

    def _speak(self, text: str) -> None:
        samples, rate = render(text, self.voice, self.rate, self.engine)
        with hold(self.talk_key):
            time.sleep(self.lead_seconds)
            play(samples, rate, self.device, self.monitor)
            time.sleep(0.15)

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
        }
