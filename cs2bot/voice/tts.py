"""Natural voices: Piper, a small neural text-to-speech that runs on the CPU.

The Windows speech engine is always there but sounds like a satnav. Piper voices are trained on
real speakers, cost ~60-115 MB each, and are fetched once from Hugging Face the way the Whisper
model is, then kept under the user's cache. `piper-tts` ships inside the installer.
"""

from __future__ import annotations

import os
import random
import re
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


@dataclass(frozen=True)
class Voice:
    id: str  # e.g. "en_US-ryan-high"
    label: str
    path: str  # repo folder, e.g. "en/en_US/ryan/high"
    size_mb: int


VOICES: tuple[Voice, ...] = (
    Voice("en_US-ryan-high", "Ryan - US male, clear (default)", "en/en_US/ryan/high", 115),
    Voice("en_US-joe-medium", "Joe - US male, relaxed", "en/en_US/joe/medium", 63),
    Voice("en_US-hfc_male-medium", "HFC - US male, deep", "en/en_US/hfc_male/medium", 63),
    Voice("en_US-lessac-medium", "Lessac - US female, warm", "en/en_US/lessac/medium", 63),
    Voice("en_US-amy-medium", "Amy - US female, bright", "en/en_US/amy/medium", 63),
    Voice("en_US-kristin-medium", "Kristin - US female, calm", "en/en_US/kristin/medium", 63),
    Voice("en_US-bryce-medium", "Bryce - US male, friendly", "en/en_US/bryce/medium", 64),
    Voice("en_US-john-medium", "John - US male, steady", "en/en_US/john/medium", 64),
    Voice("en_US-norman-medium", "Norman - US male, older", "en/en_US/norman/medium", 64),
    Voice("en_US-kusal-medium", "Kusal - US male, light accent", "en/en_US/kusal/medium", 63),
    Voice("en_US-sam-medium", "Sam - US male, casual", "en/en_US/sam/medium", 63),
    Voice("en_US-hfc_female-medium", "HFC - US female, clear", "en/en_US/hfc_female/medium", 63),
    Voice("en_US-lessac-high", "Lessac - US female, warm (high quality)", "en/en_US/lessac/high", 114),
    Voice("en_US-ljspeech-high", "LJ - US female, narrator (high quality)", "en/en_US/ljspeech/high", 114),
    Voice("en_GB-alba-medium", "Alba - Scottish female", "en/en_GB/alba/medium", 63),
    Voice("en_GB-jenny_dioco-medium", "Jenny - Irish female", "en/en_GB/jenny_dioco/medium", 63),
    Voice("en_GB-alan-medium", "Alan - British male", "en/en_GB/alan/medium", 63),
    Voice("en_GB-cori-high", "Cori - British female", "en/en_GB/cori/high", 115),
    Voice(
        "en_GB-northern_english_male-medium",
        "Northern English male",
        "en/en_GB/northern_english_male/medium",
        63,
    ),
)
DEFAULT_VOICE = VOICES[0].id
WINDOWS_PREFIX = "windows:"  # speak_voice values that pick a System.Speech voice instead

_lock = threading.Lock()
_loaded: dict[str, object] = {}
downloading: set[str] = set()


def find(voice_id: str) -> Voice | None:
    return next((v for v in VOICES if v.id == voice_id), None)


def piper_missing() -> str:
    try:
        import piper  # noqa: F401
    except ImportError:
        return "piper-tts is not installed (the Windows installer includes it)"
    return ""


def cache_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "cs2bot" / "voices"
    base.mkdir(parents=True, exist_ok=True)
    return base


def model_files(voice: Voice) -> tuple[Path, Path]:
    folder = cache_dir()
    return folder / f"{voice.id}.onnx", folder / f"{voice.id}.onnx.json"


def is_cached(voice_id: str) -> bool:
    voice = find(voice_id)
    return voice is not None and all(p.exists() and p.stat().st_size > 0 for p in model_files(voice))


def download(voice_id: str) -> None:
    """Fetch a voice's model + config. Idempotent; raises OSError on network trouble."""
    voice = find(voice_id)
    if voice is None:
        raise ValueError(f"unknown voice {voice_id!r}")
    downloading.add(voice_id)
    try:
        for target in model_files(voice):
            if target.exists() and target.stat().st_size > 0:
                continue
            url = f"{HF_BASE}/{voice.path}/{target.name}"
            partial = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:  # noqa: S310
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            partial.replace(target)
    finally:
        downloading.discard(voice_id)


def length_scale(rate: int) -> float:
    """Map the panel's -10..10 speed to Piper's length scale (1.0 = natural, lower = faster)."""
    rate = max(-10, min(10, rate))
    return round(1.0 - rate * 0.04, 3)


_EMOJI = re.compile(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]")
_SHOUT = re.compile(r"\b([A-Z]{2,})\b")


_WRITTEN = re.compile(r"\*[^*]*\*|\([^)]*\)|^\s*[-*\u2022]\s+|\s+[-*\u2022]\s+(?=\w)", re.M)


def for_speech(text: str) -> str:
    """Make chat text sound spoken: no emoji, no 'gg' spelled out as a word, no shouting caps."""
    text = _EMOJI.sub("", text)
    text = _WRITTEN.sub("", text)
    text = re.sub(r"^\s*(?:as an? (?:ai|teammate|language model)[^,.!]*[,.!]\s*)", "", text, flags=re.I)
    text = re.sub(
        r"\s*(?:let me know if[^.!?]*|hope (?:this|that) helps[^.!?]*)[.!?]?\s*$", "", text, flags=re.I
    )
    text = re.sub(r"\s+", " ", text).strip()
    spoken = {
        "gg": "g g",
        "ggs": "g g's",
        "wp": "well played",
        "gl": "good luck",
        "hf": "have fun",
        "nt": "nice try",
        "ns": "nice shot",
        "brb": "be right back",
        "afk": "a f k",
        "idk": "I don't know",
        "imo": "in my opinion",
        "tbh": "to be honest",
        "lol": "ha",
        "lmao": "ha ha",
        "omg": "oh my god",
        "wtf": "what the hell",
        "ez": "easy",
        "1v1": "one v one",
        "awp": "awp",
        "ak": "a k",
        "eco": "eco",
    }
    words = [spoken.get(w.casefold().strip(".,!?"), w) for w in text.split(" ")]
    text = " ".join(words)
    text = _SHOUT.sub(lambda m: m.group(1).capitalize() if len(m.group(1)) > 3 else m.group(1), text)
    return text


def synthesise(text: str, voice_id: str = DEFAULT_VOICE, rate: int = 0) -> tuple[list[float], int]:
    """Mono float samples and sample rate for `text`; the voice must be installed first.

    Each line gets a little random variation in pace and prosody so twenty replies do not come
    out with the exact same cadence - the thing that gives synthetic speech away first.
    """
    from piper import PiperVoice, SynthesisConfig

    voice = find(voice_id) or find(DEFAULT_VOICE)
    assert voice is not None
    if not is_cached(voice.id):
        raise RuntimeError(f"Piper voice {voice.id} is not installed - press Install on the Speech tab")
    with _lock:
        model = _loaded.get(voice.id)
        if model is None:
            onnx, _ = model_files(voice)
            model = PiperVoice.load(onnx)
            _loaded[voice.id] = model
        assert isinstance(model, PiperVoice)
        config = SynthesisConfig(
            length_scale=length_scale(rate) * random.uniform(0.94, 1.06),
            noise_scale=random.uniform(0.6, 0.75),
            noise_w_scale=random.uniform(0.7, 0.9),
        )
        samples: list[float] = []
        rate_hz = 22050
        for chunk in model.synthesize(for_speech(text), config):
            rate_hz = chunk.sample_rate
            samples.extend(float(x) for x in chunk.audio_float_array)
    return samples, rate_hz


def status() -> dict[str, object]:
    return {
        "supported": not piper_missing(),
        "unsupported_reason": piper_missing(),
        "voices": [
            {
                "id": v.id,
                "label": v.label,
                "size_mb": v.size_mb,
                "ready": is_cached(v.id),
                "downloading": v.id in downloading,
            }
            for v in VOICES
        ],
    }
