"""Talk to the update agent on the LAN server: which release is installed there, and ask it
to install the one this client came from. The agent is installer/server/agent.ps1."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import httpx

AGENT_PORT = 11435
REPO = "Oopsiez/cs2-llama-chatbot"
_RC = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")


def agent_url(ollama_url: str) -> str:
    """The agent lives on the same machine as Ollama, one port up."""
    host = urlsplit(ollama_url).hostname or "127.0.0.1"
    return f"http://{host}:{AGENT_PORT}"


def normalise(version: str) -> str:
    return version.strip().removeprefix("v")


def behind(server: str, client: str) -> bool:
    """Whether the server's release is older than the client's (unknown versions never are)."""
    a, b = _RC.match(normalise(server) or ""), _RC.match(normalise(client) or "")
    if not a or not b:
        return False

    def key(m: re.Match[str]) -> tuple[int, int, int, int]:
        major, minor, patch, rc = m.groups()
        # A final release outranks every rc of the same number.
        return int(major), int(minor), int(patch), int(rc) if rc else 10**6

    return key(a) < key(b)


async def server_version(ollama_url: str) -> dict[str, Any]:
    """`{"version", "host", "updating", "log"}` from the agent, or `{"error": ...}`."""
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(f"{agent_url(ollama_url)}/version")
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"no update agent at {agent_url(ollama_url)}: {exc}"}


async def request_update(ollama_url: str, version: str) -> dict[str, Any]:
    """Ask the agent to download and install `version`; the agent answers before it starts."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(f"{agent_url(ollama_url)}/update", json={"version": version})
            data: dict[str, Any] = response.json()
            if response.status_code >= 400:
                return {"error": data.get("error", f"agent said {response.status_code}")}
            return data
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"could not reach the update agent: {exc}"}


def parse_release(data: dict[str, Any]) -> dict[str, Any]:
    """`{"version", "url"}` out of a GitHub release record."""
    tag = normalise(str(data.get("tag_name") or ""))
    return {"version": tag, "url": str(data.get("html_url") or f"https://github.com/{REPO}/releases")}


async def latest_release() -> dict[str, Any]:
    """The newest published release on GitHub, or `{"error": ...}` when it cannot be asked."""
    try:
        async with httpx.AsyncClient(timeout=6, headers={"Accept": "application/vnd.github+json"}) as client:
            response = await client.get(f"https://api.github.com/repos/{REPO}/releases/latest")
            response.raise_for_status()
            return parse_release(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"could not ask GitHub for the latest release: {exc}"}


def update_report(client: str, server: dict[str, Any], latest: dict[str, Any]) -> dict[str, Any]:
    """One picture of who is on what, with the flags the panel shows."""
    server_version = str(server.get("version", ""))
    newest = str(latest.get("version", ""))
    return {
        "client": client,
        "server": server,
        "latest": latest,
        "server_behind": behind(server_version, client),
        "client_behind": behind(client, newest),
        "server_behind_latest": behind(server_version, newest),
        "in_sync": not server.get("error") and normalise(server_version) == normalise(client),
    }
