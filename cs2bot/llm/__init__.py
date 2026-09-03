"""LLM backends and the factory that builds one from config."""

from __future__ import annotations

from ..config import LLMSettings
from .base import ChatTurn, LLMBackend, LLMError, SamplingParams
from .llamacpp import LlamaCppBackend
from .mock import MockBackend
from .ollama import OllamaBackend

BACKENDS = ("llama_cpp", "ollama", "mock")


def build_backend(settings: LLMSettings) -> LLMBackend:
    if settings.backend == "llama_cpp":
        return LlamaCppBackend(
            model_path=settings.model_path,
            n_ctx=settings.n_ctx,
            n_gpu_layers=settings.n_gpu_layers,
            n_threads=settings.n_threads,
        )
    if settings.backend == "ollama":
        return OllamaBackend(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            timeout=settings.request_timeout,
            api_key=settings.ollama_api_key,
            verify_tls=settings.ollama_verify_tls,
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
]
