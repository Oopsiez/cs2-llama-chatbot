"""llama.cpp backend: runs a quantized Llama 3 8B Instruct GGUF locally."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .base import ChatTurn, LLMBackend, LLMError, SamplingParams


class LlamaCppBackend(LLMBackend):
    name = "llama_cpp"

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        n_threads: int = 0,
    ) -> None:
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.n_threads = n_threads or (os.cpu_count() or 4)
        self._llama: Any | None = None
        self._lock = asyncio.Lock()

    def _load(self) -> Any:
        if self._llama is not None:
            return self._llama
        if not self.model_path or not Path(self.model_path).is_file():
            raise LLMError(f"GGUF model not found: {self.model_path or '<unset>'}")
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LLMError("llama-cpp-python is not installed (pip install 'cs2bot[llama]')") from exc

        self._llama = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            n_threads=self.n_threads,
            chat_format="llama-3",
            verbose=False,
        )
        return self._llama

    def _complete(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        llama = self._load()
        result = llama.create_chat_completion(
            messages=[{"role": t.role, "content": t.content} for t in turns],
            temperature=params.temperature,
            top_p=params.top_p,
            top_k=params.top_k,
            repeat_penalty=params.repeat_penalty,
            max_tokens=params.max_tokens,
            stop=params.stop,
        )
        return (result["choices"][0]["message"]["content"] or "").strip()

    async def generate(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        # llama.cpp contexts are not re-entrant, so serialise calls and keep the event loop free.
        async with self._lock:
            return await asyncio.to_thread(self._complete, turns, params)

    async def health(self) -> str:
        async with self._lock:
            await asyncio.to_thread(self._load)
        return (
            f"llama.cpp loaded: {Path(self.model_path).name} "
            f"(ctx={self.n_ctx}, gpu_layers={self.n_gpu_layers})"
        )

    async def aclose(self) -> None:
        self._llama = None
