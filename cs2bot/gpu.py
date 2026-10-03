"""Who is holding the card right now, and how to make them let go.

Ollama keeps weights loaded after use, another always-on assistant may be sitting on half the
VRAM, and CS2 needs the rest - so the panel lists what is on the GPU and offers to clear it.
Dependency-free like `hardware.py`: `nvidia-smi` for processes, Ollama's own API for models.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from .hardware import probe

# Never offered a kill button: taking these down is taking the game or the bot down.
PROTECTED = ("cs2", "steam", "cs2 chatbot", "python", "explorer", "dwm", "csrss", "wininit")


@dataclass(frozen=True)
class GpuProcess:
    pid: int
    name: str
    used_mb: int
    protected: bool


@dataclass(frozen=True)
class LoadedModel:
    name: str
    size_gb: float
    vram_gb: float
    expires_at: str


def _is_protected(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in PROTECTED)


def gpu_processes() -> list[GpuProcess]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        out = subprocess.run(
            [
                smi,
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found: list[GpuProcess] = []
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        name = os.path.basename(parts[1]) or parts[1]
        used = int(parts[2]) if parts[2].isdigit() else 0
        found.append(
            GpuProcess(pid, name, used, protected=pid == os.getpid() or _is_protected(name))
        )
    return sorted(found, key=lambda p: -p.used_mb)


def kill(pid: int) -> tuple[bool, str]:
    """End a process by id - refused for the game, the bot, and Windows itself."""
    for process in gpu_processes():
        if process.pid == pid and process.protected:
            return False, f"not killing {process.name} - the game or the bot needs it"
    if pid == os.getpid() or pid <= 0:
        return False, "not killing the bot itself"
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode:
                return False, (result.stderr or result.stdout).strip() or "taskkill refused"
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return True, f"ended process {pid}"


async def loaded_models(ollama_url: str, api_key: str = "", verify_tls: bool = True) -> list[LoadedModel]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}
    try:
        async with httpx.AsyncClient(
            base_url=ollama_url.rstrip("/"), timeout=5, headers=headers, verify=verify_tls
        ) as client:
            response = await client.get("/api/ps")
            response.raise_for_status()
            rows = response.json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return []
    return [
        LoadedModel(
            name=row.get("name", ""),
            size_gb=round(row.get("size", 0) / 1024**3, 1),
            vram_gb=round(row.get("size_vram", 0) / 1024**3, 1),
            expires_at=row.get("expires_at", ""),
        )
        for row in rows
    ]


async def unload_model(
    ollama_url: str, model: str, api_key: str = "", verify_tls: bool = True
) -> tuple[bool, str]:
    """Ask Ollama to drop a model's weights now - `keep_alive: 0` is its unload."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}
    try:
        async with httpx.AsyncClient(
            base_url=ollama_url.rstrip("/"), timeout=30, headers=headers, verify=verify_tls
        ) as client:
            response = await client.post("/api/generate", json={"model": model, "keep_alive": 0})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"Ollama would not unload {model}: {exc}"
    return True, f"unloaded {model}"


async def report(ollama_url: str, api_key: str = "", verify_tls: bool = True) -> dict[str, Any]:
    hardware = probe()
    processes = gpu_processes()
    return {
        "gpu": hardware.gpu,
        "vram_gb": hardware.vram_gb,
        "used_mb": sum(p.used_mb for p in processes),
        "processes": [asdict(p) for p in processes],
        "models": [asdict(m) for m in await loaded_models(ollama_url, api_key, verify_tls)],
        "nvidia_smi": bool(shutil.which("nvidia-smi")),
    }
