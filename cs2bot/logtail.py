"""Incremental follower for `console.log`.

The old bot re-read the tail of the whole file on every poll. This keeps a file handle and a
byte offset instead, and handles the two things CS2 does to the log: appending while we read
(partial last line) and truncating/recreating it on launch with `-conclearlog`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO


class LogTailer:
    def __init__(self, path: str | os.PathLike[str], from_start: bool = False) -> None:
        self.path = Path(path)
        self._from_start = from_start
        self._handle: TextIO | None = None
        self._inode: tuple[int, int] | None = None
        self._buffer = ""

    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._inode = None
        self._buffer = ""

    def _file_id(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_dev, stat.st_ino)

    def _open(self, from_start: bool) -> bool:
        try:
            handle = self.path.open("r", encoding="utf-8", errors="replace", newline="")
        except OSError:
            return False
        if not from_start:
            handle.seek(0, os.SEEK_END)
        self._handle = handle
        self._inode = self._file_id()
        self._buffer = ""
        return True

    def _rotated(self) -> bool:
        """True when the log was replaced or truncated underneath us."""
        if self._handle is None:
            return True
        current = self._file_id()
        if current is None or current != self._inode:
            return True
        try:
            return self.path.stat().st_size < self._handle.tell()
        except OSError:
            return True

    def read_lines(self) -> Iterator[str]:
        """Yield complete lines appended since the previous call."""
        if self._handle is None or self._rotated():
            # A rotated log is a fresh game session, so read it from the top.
            from_start = self._from_start if self._handle is None and self._inode is None else True
            self.close()
            if not self._open(from_start):
                return

        assert self._handle is not None
        chunk = self._handle.read()
        if not chunk:
            return
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            line = line.rstrip("\r")
            if line:
                yield line
