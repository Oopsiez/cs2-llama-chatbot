"""Ollama backend: talks to an `ollama serve` running a quantized Llama 3 8B tag.

The server does not have to be the machine playing CS2 - point `ollama_url` at another box on the
LAN (`http://gpu-box:11434`) or at a reverse proxy on the internet. Remote setups usually put
auth in front of Ollama, which is what `api_key` is for, and self-signed TLS is common enough on
a home proxy that turning verification off has to be possible.
"""

from __future__ import annotations

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers, verify=verify_tls
        )

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
            raise LLMError(
                f"Model '{self.model}' is not on {self.base_url}. "
                f"Run there: ollama pull {self.model}"
            )
        return f"ollama ready: {self.model} at {self.base_url}"

    async def aclose(self) -> None:
        await self._client.aclose()
