"""One-click timing of every stage a reply goes through, so "the bot is slow" has a number per
stage and a verdict: hardware-bound, or waiting on something else (network, a model on the CPU,
a setting).

Each stage runs on its own inside a try/except: a broken voice engine must not hide the Ollama
timing. The result doubles as a plain-text report the user can paste back.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from typing import TYPE_CHECKING, Any

from . import RELEASE, gpu
from .hardware import probe
from .llm import LLMError
from .llm.base import ChatTurn
from .output import keyboard
from .voice import audio
from .voice.speak import render, speaking_missing
from .voice.transcribe import WhisperTranscriber, whisper_missing

if TYPE_CHECKING:
    from .engine import Engine

_PROMPT = [
    ChatTurn("system", "You are a Counter-Strike 2 player. Answer in one short line."),
    ChatTurn("user", "they are all pushing B, what do we do?"),
]
_SPOKEN_SAMPLE = "rotate B now, they are all pushing, I will hold the door."
_CLIP_SECONDS = 5.0


class Stage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.seconds = 0.0
        self.detail = ""
        self.verdict = ""
        self.ok = True
        self._started = time.perf_counter()

    def done(self, detail: str, verdict: str = "") -> Stage:
        self.seconds = time.perf_counter() - self._started
        self.detail = detail
        self.verdict = verdict
        return self

    def failed(self, exc: BaseException) -> Stage:
        self.seconds = time.perf_counter() - self._started
        self.detail = f"{type(exc).__name__}: {exc}"
        self.verdict = "failed - fix this before timing matters"
        self.ok = False
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seconds": round(self.seconds, 2),
            "detail": self.detail,
            "verdict": self.verdict,
            "ok": self.ok,
        }


def _machine() -> dict[str, Any]:
    hardware = probe()
    return {
        "version": RELEASE,
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count() or 0,
        "ram_gb": round(hardware.ram_gb, 1),
        "gpu": hardware.gpu or "unknown",
        "vram_gb": round(hardware.vram_gb, 1),
    }


async def _model_placement(engine: Engine) -> Stage:
    stage = Stage("where the model sits")
    llm = engine.config.llm
    try:
        loaded = await gpu.loaded_models(llm.ollama_url, llm.ollama_api_key, llm.ollama_verify_tls)
    except Exception as exc:
        return stage.failed(exc)
    if not loaded:
        return stage.done(
            f"nothing loaded on {llm.ollama_url} yet (first reply pays the load time)",
            "run the test again after a reply so the load is not counted",
        )
    parts = []
    verdict = "model is on the GPU - speed is down to the card and the model size"
    for model in loaded:
        on_gpu = model.vram_gb / model.size_gb if model.size_gb else 0.0
        if on_gpu >= 0.95:
            place = "GPU"
        elif on_gpu > 0:
            place = f"{on_gpu:.0%} GPU, rest CPU"
            verdict = (
                "model is split between GPU and CPU - CS2 is taking VRAM; "
                "use a smaller model or free the card"
            )
        else:
            place = "CPU"
            verdict = "model runs on the CPU - that is the slowness; it needs to fit next to CS2 on the GPU"
        parts.append(f"{model.name}: {model.size_gb:.1f} GB, {place}")
    return stage.done("; ".join(parts), verdict)


def _gpu_users() -> Stage:
    stage = Stage("what else is on the GPU")
    try:
        procs = gpu.gpu_processes()
    except Exception as exc:
        return stage.failed(exc)
    if not procs:
        return stage.done("no per-process GPU numbers available on this machine")
    top = sorted(procs, key=lambda p: p.used_mb, reverse=True)[:6]
    return stage.done(", ".join(f"{p.name} {p.used_mb} MB" for p in top))


async def _warm(engine: Engine) -> Stage:
    stage = Stage("reach Ollama and load the model")
    try:
        note = await engine.backend.warm()
    except LLMError as exc:
        return stage.failed(exc)
    verdict = ""
    if stage.seconds > 20:
        verdict = "loading alone takes long - the model is being paged in from disk or the server is far away"
    return stage.done(note, verdict)


async def _reply(engine: Engine) -> Stage:
    stage = Stage("one typed reply from the chat model")
    try:
        text = await engine.backend.generate(_PROMPT, engine._sampling_params())
    except LLMError as exc:
        return stage.failed(exc)
    stage.done("")
    words = len(text.split())
    rate = words / stage.seconds if stage.seconds else 0.0
    if stage.seconds <= 3:
        verdict = "fine"
    elif rate < 3:
        verdict = "slow token rate - the model is on the CPU or the card is shared with CS2 (hardware)"
    else:
        verdict = (
            "tokens come fast but the call still took long - waiting on the network or a busy "
            "server, not hardware"
        )
    return stage.done(f"{words} words, {rate:.1f} words/s: {text.strip()[:80]!r}", verdict)


async def _speech_rewrite(engine: Engine) -> Stage:
    stage = Stage("reword the reply for speech")
    if not engine.config.speech_rewrite:
        return stage.done("off (Reword typed replies for speech is unticked)")
    try:
        spoken = await engine.rewrite_for_speech(_SPOKEN_SAMPLE)
    except Exception as exc:
        return stage.failed(exc)
    verdict = (
        "this is a second model call per reply - untick Reword if it costs too much"
        if stage.seconds > 3
        else ""
    )
    return stage.done(f"{spoken[:80]!r}", verdict)


def _transcribe(engine: Engine) -> Stage:
    stage = Stage(f"Whisper {engine.config.voice.model} on a {_CLIP_SECONDS:g} s clip")
    if not engine.config.voice.enabled:
        return stage.done("off (Listen to voice comms is unticked)")
    missing = whisper_missing()
    if missing:
        return stage.done(missing, "speech-to-text is not installed")
    listener = engine.listener
    transcriber = getattr(listener, "_transcriber", None) if listener is not None else None
    try:
        if not isinstance(transcriber, WhisperTranscriber):
            transcriber = WhisperTranscriber(engine.config.voice.model)
        load_started = time.perf_counter()
        transcriber.load()
        load_seconds = time.perf_counter() - load_started
        started = time.perf_counter()
        transcriber.transcribe([0.0] * int(_CLIP_SECONDS * audio.SAMPLE_RATE))
        run_seconds = time.perf_counter() - started
    except Exception as exc:
        return stage.failed(exc)
    factor = run_seconds / _CLIP_SECONDS
    detail = (
        f"load {load_seconds:.1f} s, transcribe {run_seconds:.1f} s ({factor:.2f}x real time) "
        f"on the {transcriber.device}"
    )
    if factor < 0.5:
        verdict = "fine"
    elif factor < 1.5:
        verdict = "keeps up but adds seconds - a smaller Whisper model (base.en) would help"
    else:
        verdict = "slower than real time on the CPU - this is hardware; use base.en or tiny.en"
    return stage.done(detail, verdict)


def _render(engine: Engine) -> Stage:
    settings = engine.config.voice
    stage = Stage(f"voice engine {settings.speak_engine} renders a line")
    if settings.reply_with == "text":
        return stage.done("off (Reply with is set to text only)")
    missing = speaking_missing()
    if missing:
        return stage.done(missing, "speaking is not installed")
    try:
        samples, rate = render(
            _SPOKEN_SAMPLE, settings.speak_voice, settings.speak_rate, settings.speak_engine
        )
    except Exception as exc:
        return stage.failed(exc)
    clip = len(samples) / rate if rate else 0.0
    stage.done("")
    factor = stage.seconds / clip if clip else 0.0
    detail = f"{clip:.1f} s of audio in {stage.seconds:.1f} s ({factor:.2f}x real time)"
    if factor < 0.5:
        verdict = "fine"
    elif settings.speak_engine in ("chatterbox", "chatterbox-turbo"):
        verdict = "Chatterbox is heavy - on the CPU it is always this slow; Kokoro is near instant"
    else:
        verdict = "slow for this engine - CPU is busy (CS2 + model) or the engine fell back to the CPU"
    return stage.done(detail, verdict)


def _keys() -> Stage:
    stage = Stage("key presses reach the game")
    try:
        diag = keyboard.diagnosis()
    except Exception as exc:
        return stage.failed(exc)
    if not diag.get("windows"):
        return stage.done("not Windows - nothing to press")
    verdict = ""
    if diag.get("focused_window_out_of_reach"):
        verdict = "the focused window runs with more rights than the bot - run the bot as administrator"
    return stage.done(", ".join(f"{k}={v}" for k, v in diag.items()), verdict)


def _slowest(stages: list[Stage]) -> str:
    timed = [s for s in stages if s.ok and s.seconds > 0.5 and "load" not in s.name]
    if not timed:
        return (
            "every stage is quick - if replies still land late, the delay is in CS2 itself "
            "(log write, chat open) or the cooldown/delay settings"
        )
    worst = max(timed, key=lambda s: s.seconds)
    return f"the slow stage is '{worst.name}' at {worst.seconds:.1f} s - {worst.verdict or 'see its line'}"


def _report(machine: dict[str, Any], stages: list[Stage], summary: str) -> str:
    lines = [
        f"CS2 Chatbot {machine['version']} speed test",
        f"machine: {machine['os']}, {machine['cpu']} x{machine['cores']}, {machine['ram_gb']} GB RAM, "
        f"{machine['gpu']} {machine['vram_gb']} GB VRAM, python {machine['python']}"
        f"{' (frozen)' if machine['frozen'] else ''}",
        "",
    ]
    for s in stages:
        lines.append(f"{'ok  ' if s.ok else 'FAIL'} {s.seconds:6.1f} s  {s.name}: {s.detail}")
        if s.verdict:
            lines.append(f"              -> {s.verdict}")
    lines += ["", f"summary: {summary}"]
    return "\n".join(lines)


async def run(engine: Engine) -> dict[str, Any]:
    """Time every stage and say which one is the problem."""
    import asyncio

    machine = _machine()
    stages = [
        await _model_placement(engine),
        _gpu_users(),
        await _warm(engine),
        await _reply(engine),
        await _speech_rewrite(engine),
        await asyncio.to_thread(_transcribe, engine),
        await asyncio.to_thread(_render, engine),
        _keys(),
    ]
    summary = _slowest(stages)
    return {
        "machine": machine,
        "stages": [s.as_dict() for s in stages],
        "summary": summary,
        "report": _report(machine, stages, summary),
    }
