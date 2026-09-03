"""Ollama backend: talks to a local `ollama serve` running a quantized Llama 3 8B tag."""

from __future__ import annotations

import httpx

from .base import ChatTurn, LLMBackend, LLMError, SamplingParams


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def generate(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            "options": {
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "repeat_penalty": params.repeat_penalty,
                "num_predict": params.max_tokens,
                "stop": [s for s in params.stop if s.strip()],
            },
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        data = response.json()
        return (data.get("message", {}).get("content") or "").strip()

    async def health(self) -> str:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable at {self.base_url}: {exc}") from exc
        models = [m.get("name", "") for m in response.json().get("models", [])]
        if self.model not in models:
            raise LLMError(f"Model '{self.model}' not pulled. Run: ollama pull {self.model}")
        return f"ollama ready: {self.model}"

    async def aclose(self) -> None:
        await self._client.aclose()
