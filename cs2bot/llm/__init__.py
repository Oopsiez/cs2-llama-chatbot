"""LLM backends and the factory that builds one from config."""

from __future__ import annotations

from pathlib import Path

from ..config import LLMSettings
from ..hardware import Hardware, probe
from .base import ChatTurn, LLMBackend, LLMError, SamplingParams
from .llamacpp import LlamaCppBackend, threads_for_the_model
from .mock import MockBackend
from .ollama import OllamaBackend

BACKENDS = ("llama_cpp", "ollama", "mock")


# Weights plus the KV cache and scratch buffers, roughly, for a 4k context.
GGUF_OVERHEAD_GB = 1.0


def ollama_gpu_layers(settings: LLMSettings) -> int | None:
    """`num_gpu` for Ollama: 0 on CPU-only, the chosen count for a split, else Ollama's own choice."""
    if settings.cpu_only:
        return 0
    if not settings.gpu_auto and settings.n_gpu_layers >= 0:
        return settings.n_gpu_layers
    return None


def gpu_layers_for(settings: LLMSettings, hardware: Hardware) -> int:
    """All layers on the card when the file fits beside CS2, none when it does not."""
    if settings.cpu_only:
        return 0
    if not settings.gpu_auto:
        return settings.n_gpu_layers
    try:
        size_gb = Path(settings.model_path).stat().st_size / 1024**3
    except OSError:
        return settings.n_gpu_layers
    if not hardware.vram_gb:
        return 0
    return -1 if size_gb + GGUF_OVERHEAD_GB <= hardware.vram_for_model_gb else 0


def build_backend(settings: LLMSettings, ollama_model: str = "") -> LLMBackend:
    """The configured backend; `ollama_model` swaps in another Ollama tag (the speech model)."""
    if settings.backend == "llama_cpp":
        return LlamaCppBackend(
            model_path=settings.model_path,
            n_ctx=settings.n_ctx,
            n_gpu_layers=gpu_layers_for(settings, probe()),
            n_threads=settings.n_threads,
        )
    if settings.backend == "ollama":
        return OllamaBackend(
            base_url=settings.ollama_url,
            model=ollama_model or settings.ollama_model,
            timeout=settings.request_timeout,
            api_key=settings.ollama_api_key,
            verify_tls=settings.ollama_verify_tls,
            num_thread=settings.n_threads or threads_for_the_model(),
            num_gpu=ollama_gpu_layers(settings),
        )
    if settings.backend == "mock":
        return MockBackend()
    raise LLMError(f"Unknown LLM backend: {settings.backend}")


__all__ = [
    "BACKENDS",
    "ChatTurn",
    "LLMBackend",
    "LLMError",
    "LlamaCppBackend",
    "MockBackend",
    "OllamaBackend",
    "SamplingParams",
    "build_backend",
    "gpu_layers_for",
]
