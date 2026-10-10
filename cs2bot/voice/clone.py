"""The voice Chatterbox imitates: a clip from a file, a URL, or the last teammate heard.

Whatever the source, it ends up as `clone.wav` in the voices cache - mono, 24 kHz, 16-bit, at
most `MAX_SECONDS` long - and `reference()` hands it to the engine as floats.
"""

from __future__ import annotations

import array
import io
import subprocess
import sys
import urllib.request
import wave
from collections.abc import Sequence
from pathlib import Path

from .tts import cache_dir

SAMPLE_RATE = 24000
MAX_SECONDS = 12.0
MIN_SECONDS = 4.0
GOOD_SECONDS = 7.0  # below this Chatterbox has too little voice to go on and tends to babble


def path() -> Path:
    return cache_dir() / "clone.wav"


def info() -> dict[str, object]:
    target = path()
    if not target.exists():
        return {"ready": False, "seconds": 0.0, "source": ""}
    with wave.open(str(target)) as handle:
        seconds = handle.getnframes() / handle.getframerate()
    note = target.with_suffix(".txt")
    return {
        "ready": True,
        "seconds": round(seconds, 1),
        "short": seconds < GOOD_SECONDS,
        "source": note.read_text() if note.exists() else "",
    }


def reference() -> list[float] | None:
    target = path()
    if not target.exists():
        return None
    with wave.open(str(target)) as handle:
        frames = handle.readframes(handle.getnframes())
    pcm = array.array("h")
    pcm.frombytes(frames)
    return [x / 32768.0 for x in pcm]


def resample(samples: Sequence[float], rate: int, target: int = SAMPLE_RATE) -> list[float]:
    """Linear resampling - plenty for a reference clip."""
    if rate == target or not samples:
        return list(samples)
    count = int(len(samples) * target / rate)
    out = []
    for i in range(count):
        pos = i * rate / target
        left = int(pos)
        right = min(left + 1, len(samples) - 1)
        frac = pos - left
        out.append(samples[left] * (1 - frac) + samples[right] * frac)
    return out


def save(samples: Sequence[float], rate: int, source: str) -> dict[str, object]:
    """Store `samples` as the clone reference; trims to MAX_SECONDS, refuses very short clips."""
    mono = resample(samples, rate)
    if len(mono) < MIN_SECONDS * SAMPLE_RATE:
        raise ValueError(
            f"the clip is too short ({len(mono) / SAMPLE_RATE:.1f} s) - at least {MIN_SECONDS:g} s of"
            f" speech are needed, {GOOD_SECONDS:g}-{MAX_SECONDS:g} s for a clean clone"
        )
    mono = mono[: int(MAX_SECONDS * SAMPLE_RATE)]
    peak = max(abs(x) for x in mono) or 1.0
    pcm = array.array("h", (int(max(-1.0, min(1.0, x / peak * 0.9)) * 32767) for x in mono))
    with wave.open(str(path()), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    path().with_suffix(".txt").write_text(source)
    from . import engines

    engines._sessions.pop("chatterbox/reference", None)
    return info()


def decode(data: bytes, name: str = "") -> tuple[list[float], int]:
    """Mono floats + rate from a WAV or, when PyAV is around, any audio/video file."""
    try:
        with wave.open(io.BytesIO(data)) as handle:
            rate, channels, width = handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
            frames = handle.readframes(handle.getnframes())
        if width != 2:
            raise wave.Error("only 16-bit WAV is read directly")
        pcm = array.array("h")
        pcm.frombytes(frames)
        mono = [sum(pcm[i : i + channels]) / channels / 32768.0 for i in range(0, len(pcm), channels)]
        return mono, rate
    except wave.Error:
        pass
    try:
        import av
    except ImportError as exc:
        raise ValueError(f"{name or 'the clip'} is not a WAV file and the audio decoder is missing") from exc
    out: list[float] = []
    with av.open(io.BytesIO(data)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError(f"no audio in {name or 'the clip'}")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(stream):
            for piece in resampler.resample(frame):
                out.extend(piece.to_ndarray().reshape(-1).tolist())
            if len(out) > (MAX_SECONDS + 1) * SAMPLE_RATE:
                break
    return out, SAMPLE_RATE


def fetch(url: str) -> tuple[list[float], int]:
    """Audio from a URL: a direct audio/video link, or any page yt-dlp can read (YouTube etc.)."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("the URL must start with http:// or https://")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            kind = response.headers.get("Content-Type", "")
            if kind.startswith(("audio/", "video/")) or kind == "application/octet-stream":
                return decode(response.read(), url)
    except OSError as exc:
        raise ValueError(f"could not fetch {url}: {exc}") from exc
    exe = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    try:
        result = subprocess.run(
            [
                exe,
                "-q",
                "-x",
                "--audio-format",
                "wav",
                "--postprocessor-args",
                "-ac 1 -ar 24000 -t 15",
                "-o",
                "-",
                url,
            ],
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            "that page is not a direct audio link, and yt-dlp is not installed to pull it"
        ) from exc
    if result.returncode != 0 or not result.stdout:
        raise ValueError(
            f"yt-dlp could not get audio from {url}: {result.stderr.decode(errors='replace')[-200:]}"
        )
    return decode(result.stdout, url)
