"""What this machine can actually run a model on.

Deliberately dependency-free and best-effort: a number nobody can read is worse than a blank,
so anything that cannot be worked out is left at 0 and the panel says "unknown" instead.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass

GIB = 1024**3
# CS2 itself wants a few gigabytes of video memory, so a model cannot have the whole card.
CS2_VRAM_RESERVE_GB = 2.0


@dataclass(frozen=True)
class Hardware:
    ram_gb: float = 0.0
    vram_gb: float = 0.0
    gpu: str = ""

    @property
    def vram_for_model_gb(self) -> float:
        """What is left for the model once CS2 has taken its share of the card."""
        return max(0.0, self.vram_gb - CS2_VRAM_RESERVE_GB)


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _total_ram_gb() -> float:
    if platform.system() == "Windows":
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0.0
        return round(status.ullTotalPhys / GIB, 1)
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIB, 1)
    except (ValueError, OSError, AttributeError):
        return 0.0


def _nvidia_vram() -> tuple[float, str]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return 0.0, ""
    try:
        out = subprocess.run(
            [smi, "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0, ""
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2 or not parts[0].replace(".", "", 1).isdigit():
            continue
        return round(float(parts[0]) / 1024, 1), parts[1]
    return 0.0, ""


def _windows_vram() -> tuple[float, str]:
    """AMD and Intel cards, read off the adapter Windows itself reports."""
    if platform.system() != "Windows":
        return 0.0, ""
    powershell = shutil.which("powershell")
    if not powershell:
        return 0.0, ""
    query = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -First 1 AdapterRAM,Name | ConvertTo-Csv -NoTypeInformation"
    )
    try:
        out = subprocess.run(
            [powershell, "-NoProfile", "-Command", query],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0, ""
    rows = [row for row in out.splitlines() if row.strip()]
    if len(rows) < 2:
        return 0.0, ""
    parts = [part.strip().strip('"') for part in rows[1].split(",")]
    if len(parts) < 2 or not parts[0].isdigit():
        return 0.0, ""
    # Win32_VideoController reports a 32-bit value, so anything over 4GB reads as 4095MB.
    return round(int(parts[0]) / GIB, 1), parts[1]


def probe() -> Hardware:
    """Memory this machine has, as far as it can be worked out without extra packages."""
    vram, gpu = _nvidia_vram()
    if not vram:
        vram, gpu = _windows_vram()
    return Hardware(ram_gb=_total_ram_gb(), vram_gb=vram, gpu=gpu)
