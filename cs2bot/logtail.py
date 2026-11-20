"""Incremental follower for `console.log`.

Keeps a byte offset, not a file handle: every poll opens the log, reads what was appended and
closes it again, so CS2 is never writing to a file the bot has open between polls. On Windows the
file is opened with delete sharing too, so CS2 can truncate, replace or delete it mid-read.
Handles the two things CS2 does to the log: appending while we read (partial last line) and
truncating/recreating it on launch with `-conclearlog`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO


def open_shared(path: Path) -> BinaryIO:
    """Open `path` for reading without stopping anyone else writing, renaming or deleting it."""
    if sys.platform != "win32":
        return path.open("rb")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    create = kernel32.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    generic_read, share_all, open_existing, normal = 0x80000000, 0x7, 3, 0x80
    handle = create(str(path), generic_read, share_all, None, open_existing, normal, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        if ctypes.get_last_error() in (2, 3):  # file / path not found
            raise FileNotFoundError(str(path))
        return path.open("rb")  # still readable, just without delete sharing
    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    return os.fdopen(fd, "rb")


class LogTailer:
    def __init__(self, path: str | os.PathLike[str], from_start: bool = False) -> None:
        self.path = Path(path)
        self._from_start = from_start
        self._file: tuple[int, int] | None = None
        self._offset: int | None = None
        self._buffer = b""

    @property
    def is_open(self) -> bool:
        """True while the log exists and is being followed (no handle is held between polls)."""
        return self._file is not None

    def close(self) -> None:
        self._file = None
        self._offset = None
        self._buffer = b""

    def _stat(self) -> tuple[tuple[int, int], int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_dev, stat.st_ino), stat.st_size

    def read_lines(self) -> Iterator[str]:
        """Yield complete lines appended since the previous call."""
        current = self._stat()
        if current is None:
            self._file = None
            return
        file_id, size = current
        if self._offset is None:
            self._offset = 0 if self._from_start else size
            self._buffer = b""
        elif file_id != self._file or size < self._offset:
            # A replaced or shrunk log is a fresh game session, so read it from the top.
            self._offset = 0
            self._buffer = b""
        self._file = file_id
        if size == self._offset:
            return
        try:
            with open_shared(self.path) as handle:
                handle.seek(self._offset)
                chunk = handle.read(size - self._offset)
        except OSError:
            return
        self._offset += len(chunk)
        *lines, self._buffer = (self._buffer + chunk).split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", errors="replace").rstrip("\r")
            if line:
                yield line
