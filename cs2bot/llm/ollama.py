"""Ollama backend: talks to an `ollama serve` running a quantized Llama 3 8B tag.

The server does not have to be the machine playing CS2 - point `ollama_url` at another box on the
LAN (`http://gpu-box:11434`) or at a reverse proxy on the internet. Remote setups usually put
auth in front of Ollama, which is what `api_key` is for, and self-signed TLS is common enough on
a home proxy that turning verification off has to be possible.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import ChatTurn, LLMBackend, LLMError, SamplingParams


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        api_key: str = "",
        verify_tls: bool = True,
        num_thread: int = 0,
        num_gpu: int | None = None,
    ) -> None:
        self.num_gpu = num_gpu
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_thread = num_thread
        headers = {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers, verify=verify_tls
        )

    def _why(self, exc: httpx.HTTPError) -> str:
        """httpx errors often stringify to nothing - name the failure and the host."""
        if isinstance(exc, httpx.TimeoutException):
            return f"no answer from {self.base_url} within {self._client.timeout.read}s"
        if isinstance(exc, httpx.ConnectError):
            return f"nothing is listening at {self.base_url}"
        text = str(exc).strip()
        return f"{type(exc).__name__} talking to {self.base_url}" + (f": {text}" if text else "")

    async def generate(self, turns: list[ChatTurn], params: SamplingParams) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            # Half an hour of being left alone before Ollama drops the weights, so a quiet
            # stretch of the match does not mean reloading them onto the card mid-round.
            "keep_alive": "30m",
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            "options": {
                **({"num_thread": self.num_thread} if self.num_thread else {}),
                **({"num_gpu": self.num_gpu} if self.num_gpu is not None else {}),
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
            raise LLMError(f"Ollama request failed - {self._why(exc)}") from exc
        data = response.json()
        return (data.get("message", {}).get("content") or "").strip()

    async def health(self) -> str:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable - {self._why(exc)}") from exc
        models = [m.get("name", "") for m in response.json().get("models", [])]
        if self.model not in models:
            there = ", ".join(models) if models else "nothing"
            raise LLMError(
                f"Model '{self.model}' is not on {self.base_url} (it has: {there}). "
                f"Pick one of those on the Model tab, or run there: ollama pull {self.model}"
            )
        return f"ollama ready: {self.model} at {self.base_url}"

    async def models(self) -> list[str]:
        """The tags the server has pulled; empty when it cannot be reached."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return [m.get("name", "") for m in response.json().get("models", [])]

    async def pull(self, tag: str) -> AsyncIterator[str]:
        """Download `tag` on the server, yielding Ollama's progress lines as it goes."""
        try:
            async with self._client.stream(
                "POST", "/api/pull", json={"model": tag, "stream": True}, timeout=None
            ) as response:
                response.raise_for_status()
                async for raw in response.aiter_lines():
                    if not raw.strip():
                        continue
                    chunk = json.loads(raw)
                    if chunk.get("error"):
                        raise LLMError(str(chunk["error"]))
                    status = str(chunk.get("status", ""))
                    total, done = chunk.get("total"), chunk.get("completed")
                    if total and done is not None:
                        status += f" {100 * done // total}% ({done / 1e9:.1f}/{total / 1e9:.1f} GB)"
                    yield status
        except httpx.HTTPError as exc:
            raise LLMError(f"could not pull {tag} - {self._why(exc)}") from exc

    async def warm(self) -> str:
        ready = await self.health()
        try:
            # An empty prompt makes the server load the model and answer with nothing.
            response = await self._client.post(
                "/api/generate", json={"model": self.model, "keep_alive": "30m"}, timeout=300
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama could not load {self.model} - {self._why(exc)}") from exc
        return ready

    async def aclose(self) -> None:
        await self._client.aclose()
