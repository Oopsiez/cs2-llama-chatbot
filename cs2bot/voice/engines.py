"""The Hugging Face voices: Supertonic 2, Kitten and Chatterbox-Turbo, all ONNX, all fetched once.

Each engine is a folder of ONNX graphs plus a tokenizer under the voices cache, downloaded on
*Install* (or on first use). Chatterbox clones whatever voice is in `clone.reference()`; the
other two ship fixed voices. Everything runs on the CPU through onnxruntime, like Kokoro.
"""

from __future__ import annotations

import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .tts import cache_dir, for_speech

if TYPE_CHECKING:
    import numpy as np

HF = "https://huggingface.co"


@dataclass(frozen=True)
class Engine:
    id: str
    label: str
    repo: str
    files: tuple[str, ...]
    size_mb: int
    sample_rate: int
    voices: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    clones: bool = False


SUPERTONIC_VOICES = tuple(
    (v, f"{'Female' if v[0] == 'F' else 'Male'} {v[1]} - Supertonic")
    for v in ("M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5")
)
KITTEN_VOICES = tuple(
    (f"expr-voice-{n}-{s}", f"{'Male' if s == 'm' else 'Female'} {n} - Kitten")
    for n in (2, 3, 4, 5)
    for s in ("m", "f")
)
CHATTERBOX_VOICES = (("clone", "Cloned voice (from the clip on this tab)"),)

ENGINES: tuple[Engine, ...] = (
    Engine(
        "supertonic",
        "Supertonic 2 - fast, 10 voices (260 MB)",
        "onnx-community/Supertonic-TTS-2-ONNX",
        (
            "onnx/text_encoder.onnx",
            "onnx/text_encoder.onnx_data",
            "onnx/latent_denoiser.onnx",
            "onnx/latent_denoiser.onnx_data",
            "onnx/voice_decoder.onnx",
            "onnx/voice_decoder.onnx_data",
            "tokenizer.json",
        )
        + tuple(f"voices/{v}.bin" for v, _ in SUPERTONIC_VOICES),
        260,
        44100,
        SUPERTONIC_VOICES,
    ),
    Engine(
        "kitten",
        "Kitten TTS - tiny, 8 voices (25 MB)",
        "onnx-community/kitten-tts-nano-0.1-ONNX",
        ("onnx/model_quantized.onnx", "tokenizer.json") + tuple(f"voices/{v}.bin" for v, _ in KITTEN_VOICES),
        25,
        24000,
        KITTEN_VOICES,
    ),
    Engine(
        "chatterbox",
        "Chatterbox-Turbo - most realistic, clones a voice (1.1 GB)",
        "ResembleAI/chatterbox-turbo-ONNX",
        (
            "onnx/speech_encoder_quantized.onnx",
            "onnx/speech_encoder_quantized.onnx_data",
            "onnx/embed_tokens_quantized.onnx",
            "onnx/embed_tokens_quantized.onnx_data",
            "onnx/language_model_quantized.onnx",
            "onnx/language_model_quantized.onnx_data",
            "onnx/conditional_decoder_quantized.onnx",
            "onnx/conditional_decoder_quantized.onnx_data",
            "tokenizer.json",
        ),
        1120,
        24000,
        CHATTERBOX_VOICES,
        clones=True,
    ),
)
BY_ID = {e.id: e for e in ENGINES}

_lock = threading.Lock()
_sessions: dict[str, object] = {}
downloading: dict[str, bool] = {}
install_error: dict[str, str] = {}


def find(engine_id: str) -> Engine | None:
    return BY_ID.get(engine_id)


def runtime_missing() -> str:
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError as exc:
        return f"{exc.name} is not installed (the Windows installer includes it)"
    return ""


def folder(engine: Engine) -> Path:
    path = cache_dir() / engine.id
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_cached(engine: Engine) -> bool:
    return all(
        (folder(engine) / f).exists() and (folder(engine) / f).stat().st_size > 0 for f in engine.files
    )


def download(engine: Engine) -> None:
    """Fetch every file of `engine` that is not there yet (resumable: each lands via a .part)."""
    downloading[engine.id] = True
    install_error.pop(engine.id, None)
    try:
        for name in engine.files:
            target = folder(engine) / name
            if target.exists() and target.stat().st_size > 0:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(target.suffix + ".part")
            url = f"{HF}/{engine.repo}/resolve/main/{name}"
            with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310
                with partial.open("wb") as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
            partial.replace(target)
    except Exception as exc:
        install_error[engine.id] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        downloading[engine.id] = False


def status() -> list[dict[str, object]]:
    return [
        {
            "id": e.id,
            "label": e.label,
            "size_mb": e.size_mb,
            "ready": is_cached(e),
            "downloading": downloading.get(e.id, False),
            "error": install_error.get(e.id, ""),
            "clones": e.clones,
            "voices": [{"id": v, "label": label} for v, label in e.voices],
        }
        for e in ENGINES
    ]


def speed(rate: int) -> float:
    return round(1.0 + max(-10, min(10, rate)) * 0.04, 3)


def _session(engine: Engine, name: str) -> object:
    import onnxruntime as ort

    key = f"{engine.id}/{name}"
    if key not in _sessions:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        _sessions[key] = ort.InferenceSession(str(folder(engine) / "onnx" / name), opts)
    return _sessions[key]


def _tokenizer(engine: Engine) -> object:
    key = f"{engine.id}/tokenizer"
    if key not in _sessions:
        from tokenizers import Tokenizer

        _sessions[key] = Tokenizer.from_file(str(folder(engine) / "tokenizer.json"))
    return _sessions[key]


def _style(engine: Engine, voice: str, dim: int) -> np.ndarray[Any, Any]:
    import numpy as np

    known = {v for v, _ in engine.voices}
    chosen = voice if voice in known else engine.voices[0][0]
    return np.fromfile(folder(engine) / "voices" / f"{chosen}.bin", dtype=np.float32).reshape(1, -1, dim)


def synthesise(engine_id: str, text: str, voice: str = "", rate: int = 0) -> tuple[list[float], int]:
    """Mono samples + rate from one of the Hugging Face engines; it must be installed first."""
    engine = find(engine_id)
    if engine is None:
        raise ValueError(f"unknown voice engine {engine_id}")
    missing = runtime_missing()
    if missing:
        raise RuntimeError(missing)
    if not is_cached(engine):
        name = engine.label.split(" - ")[0]
        raise RuntimeError(f"{name} is not installed - press Install on the Speech tab")
    spoken = for_speech(text)
    with _lock:
        if engine.id == "supertonic":
            samples = _supertonic(engine, spoken, voice, rate)
        elif engine.id == "kitten":
            samples = _kitten(engine, spoken, voice, rate)
        else:
            samples = _chatterbox(engine, spoken)
    return [float(x) for x in samples], engine.sample_rate


def _supertonic(engine: Engine, text: str, voice: str, rate: int) -> list[float]:
    import numpy as np

    tok = _tokenizer(engine)
    ids = np.array([tok.encode(f"<en>{text}</en>").ids], dtype=np.int64)  # type: ignore[attr-defined]
    mask = np.ones_like(ids)
    style = _style(engine, voice, 128)
    hidden, raw_durations = _session(engine, "text_encoder.onnx").run(  # type: ignore[attr-defined]
        None, {"input_ids": ids, "attention_mask": mask, "style": style}
    )
    latent_size = 512 * 6
    durations = (raw_durations / speed(rate) * engine.sample_rate).astype(np.int64)
    lengths = (durations + latent_size - 1) // latent_size
    max_len = int(lengths.max())
    latent_mask = (np.arange(max_len) < lengths[:, None]).astype(np.int64)
    latents = np.random.randn(1, 24 * 6, max_len).astype(np.float32) * latent_mask[:, None, :]
    steps = 8
    denoiser = _session(engine, "latent_denoiser.onnx")
    for step in range(steps):
        latents = denoiser.run(  # type: ignore[attr-defined]
            None,
            {
                "noisy_latents": latents,
                "latent_mask": latent_mask,
                "style": style,
                "encoder_outputs": hidden,
                "attention_mask": mask,
                "timestep": np.full(1, step, dtype=np.float32),
                "num_inference_steps": np.full(1, steps, dtype=np.float32),
            },
        )[0]
    wave = _session(engine, "voice_decoder.onnx").run(None, {"latents": latents})[0]  # type: ignore[attr-defined]
    length = int(latent_mask.sum() * latent_size)
    return list(wave[0, :length])


def _kitten(engine: Engine, text: str, voice: str, rate: int) -> list[float]:
    import numpy as np
    from kokoro_onnx.tokenizer import Tokenizer as Phonemizer

    key = "kitten/phonemizer"
    if key not in _sessions:
        _sessions[key] = Phonemizer()
    phonemes = _sessions[key].phonemize(text, "en-us")  # type: ignore[attr-defined]
    ids = np.array([_tokenizer(engine).encode(phonemes).ids], dtype=np.int64)  # type: ignore[attr-defined]
    style = _style(engine, voice, 256).reshape(1, 256)
    wave = _session(engine, "model_quantized.onnx").run(  # type: ignore[attr-defined]
        None, {"input_ids": ids, "style": style, "speed": np.array([speed(rate)], dtype=np.float32)}
    )[0]
    return list(np.asarray(wave).reshape(-1))


START_SPEECH, STOP_SPEECH, SILENCE = 6561, 6562, 4299


def text_ids(engine: Engine, text: str) -> list[int]:
    """Chatterbox's text prompt: the tokenizer's own template, which ends every prompt with two
    <|endoftext|> markers - without them the model mumbles."""
    return list(_tokenizer(engine).encode(text).ids)  # type: ignore[attr-defined]


def _chatterbox(engine: Engine, text: str) -> list[float]:
    import numpy as np

    from . import clone

    reference = clone.reference()
    if reference is None:
        raise RuntimeError(
            "no voice to clone yet - add a clip (upload, URL or last voice heard) on the Speech tab"
        )
    audio = np.asarray(reference, dtype=np.float32)[np.newaxis, :]
    ids = np.array([text_ids(engine, text)], dtype=np.int64)
    embed = _session(engine, "embed_tokens_quantized.onnx")
    lm = _session(engine, "language_model_quantized.onnx")
    cond_emb, prompt_token, speaker_emb, speaker_feat = _session(engine, "speech_encoder_quantized.onnx").run(  # type: ignore[attr-defined]
        None, {"audio_values": audio}
    )
    inputs_embeds = np.concatenate((cond_emb, embed.run(None, {"input_ids": ids})[0]), axis=1)  # type: ignore[attr-defined]
    seq_len = inputs_embeds.shape[1]
    past = {
        i.name: np.zeros([1, 16, 0, 64], dtype=np.float16 if i.type == "tensor(float16)" else np.float32)
        for i in lm.get_inputs()  # type: ignore[attr-defined]
        if "past_key_values" in i.name
    }
    attention: Any = np.ones((1, seq_len), dtype=np.int64)
    position: Any = np.arange(seq_len, dtype=np.int64).reshape(1, -1)
    generated = [START_SPEECH]
    for _ in range(1024):
        logits, *present = lm.run(  # type: ignore[attr-defined]
            None,
            {"inputs_embeds": inputs_embeds, "attention_mask": attention, "position_ids": position, **past},
        )
        scores = logits[0, -1, :].astype(np.float32)
        seen = np.array(generated)
        scores[seen] = np.where(scores[seen] < 0, scores[seen] * 1.2, scores[seen] / 1.2)
        token = int(np.argmax(scores))
        generated.append(token)
        if token == STOP_SPEECH:
            break
        inputs_embeds = embed.run(None, {"input_ids": np.array([[token]], dtype=np.int64)})[0]  # type: ignore[attr-defined]
        attention = np.concatenate([attention, np.ones((1, 1), dtype=np.int64)], axis=1)
        position = position[:, -1:] + 1
        for name, value in zip(past, present, strict=False):
            past[name] = value
    spoken = np.array([generated[1:-1] if generated[-1] == STOP_SPEECH else generated[1:]], dtype=np.int64)
    speech = np.concatenate([prompt_token, spoken, np.full((1, 3), SILENCE, dtype=np.int64)], axis=1)
    wave = _session(engine, "conditional_decoder_quantized.onnx").run(  # type: ignore[attr-defined]
        None, {"speech_tokens": speech, "speaker_embeddings": speaker_emb, "speaker_features": speaker_feat}
    )[0]
    return list(np.asarray(wave).reshape(-1))
