"""Kokoro-82M: the most human of the local voices, at ~1-3 s a line on a CPU.

ONNX build (`kokoro-onnx`), one 310 MB model plus a 27 MB voice pack, fetched once from the
project's GitHub release into the same cache folder as the Piper voices. Runs on the CPU unless
`onnxruntime-gpu` with the CUDA runtime is present, so it never takes VRAM from the game.
"""

from __future__ import annotations

import random
import threading
import urllib.request
from pathlib import Path

from .tts import cache_dir

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"
SIZE_MB = 340

VOICES: tuple[tuple[str, str], ...] = (
    ("am_michael", "Michael - US male, natural"),
    ("am_adam", "Adam - US male, deep"),
    ("am_fenrir", "Fenrir - US male, rough"),
    ("af_heart", "Heart - US female, warm"),
    ("af_bella", "Bella - US female, bright"),
    ("af_nicole", "Nicole - US female, soft"),
    ("bm_george", "George - British male"),
    ("bm_lewis", "Lewis - British male, young"),
    ("bf_emma", "Emma - British female"),
)
DEFAULT_VOICE = VOICES[0][0]

_lock = threading.Lock()
_model: object | None = None
downloading = False


def kokoro_missing() -> str:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return "kokoro-onnx is not installed (the Windows installer includes it)"
    return ""


def files() -> tuple[Path, Path]:
    folder = cache_dir() / "kokoro"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / MODEL_FILE, folder / VOICES_FILE


def is_cached() -> bool:
    return all(p.exists() and p.stat().st_size > 0 for p in files())


def download() -> None:
    global downloading
    downloading = True
    try:
        for target in files():
            if target.exists() and target.stat().st_size > 0:
                continue
            partial = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(f"{RELEASE}/{target.name}", timeout=300) as response:  # noqa: S310
                with partial.open("wb") as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
            partial.replace(target)
    finally:
        downloading = False


def speed(rate: int) -> float:
    return round(1.0 + max(-10, min(10, rate)) * 0.04, 3)


def synthesise(text: str, voice_id: str = DEFAULT_VOICE, rate: int = 0) -> tuple[list[float], int]:
    """Mono float samples and sample rate; downloads the model on first use."""
    global _model
    from kokoro_onnx import Kokoro

    from .tts import for_speech

    if not is_cached():
        download()
    known = {v for v, _ in VOICES}
    voice = voice_id if voice_id in known else DEFAULT_VOICE
    lang = "en-gb" if voice.startswith("b") else "en-us"
    with _lock:
        if _model is None:
            model_path, voices_path = files()
            _model = Kokoro(str(model_path), str(voices_path))
        assert isinstance(_model, Kokoro)
        samples, rate_hz = _model.create(
            for_speech(text), voice=voice, speed=speed(rate) * random.uniform(0.95, 1.05), lang=lang
        )
    return [float(x) for x in samples], int(rate_hz)


def status() -> dict[str, object]:
    return {
        "supported": not kokoro_missing(),
        "unsupported_reason": kokoro_missing(),
        "ready": is_cached(),
        "downloading": downloading,
        "size_mb": SIZE_MB,
        "voices": [{"id": v, "label": label} for v, label in VOICES],
    }
