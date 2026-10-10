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

# (id, label, tier) - tier follows Kokoro's own VOICES.md grades: A/B- = best, C+/C = better, D = good.
VOICES: tuple[tuple[str, str, str], ...] = (
    ("af_heart", "Heart - US female, warm (top grade)", "best"),
    ("af_bella", "Bella - US female, bright (top grade)", "best"),
    ("af_nicole", "Nicole - US female, soft, close-mic", "best"),
    ("bf_emma", "Emma - British female", "best"),
    ("am_michael", "Michael - US male, natural", "better"),
    ("am_fenrir", "Fenrir - US male, rough", "better"),
    ("am_puck", "Puck - US male, lively", "better"),
    ("af_aoede", "Aoede - US female, clear", "better"),
    ("af_kore", "Kore - US female, firm", "better"),
    ("af_sarah", "Sarah - US female, friendly", "better"),
    ("af_alloy", "Alloy - US female, even", "better"),
    ("af_nova", "Nova - US female, upbeat", "better"),
    ("af_sky", "Sky - US female, light", "better"),
    ("bm_george", "George - British male", "better"),
    ("bm_fable", "Fable - British male, storyteller", "better"),
    ("bf_isabella", "Isabella - British female", "better"),
    ("am_adam", "Adam - US male, deep", "good"),
    ("am_echo", "Echo - US male, calm", "good"),
    ("am_eric", "Eric - US male, plain", "good"),
    ("am_liam", "Liam - US male, young", "good"),
    ("am_onyx", "Onyx - US male, low", "good"),
    ("am_santa", "Santa - US male, jolly", "good"),
    ("af_jessica", "Jessica - US female", "good"),
    ("af_river", "River - US female, relaxed", "good"),
    ("bm_lewis", "Lewis - British male, young", "good"),
    ("bm_daniel", "Daniel - British male", "good"),
    ("bf_alice", "Alice - British female", "good"),
    ("bf_lily", "Lily - British female, soft", "good"),
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
    """Mono float samples and sample rate; the model must be installed first."""
    global _model
    if not is_cached():
        raise RuntimeError("Kokoro is not installed - press Install on the Speech tab")
    from kokoro_onnx import Kokoro

    from .tts import for_speech

    known = {v for v, _, _ in VOICES}
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
        "voices": [{"id": v, "label": label, "tier": tier} for v, label, tier in VOICES],
    }
