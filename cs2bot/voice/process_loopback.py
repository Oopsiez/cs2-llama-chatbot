"""Hearing one program's audio, not the whole PC's.

Windows 10 2004 added *process loopback*: ask WASAPI for the virtual device
`VAD\\Process_Loopback` with an `AUDIOCLIENT_ACTIVATION_PARAMS` naming a process, and the
capture stream carries only what that process (and its children) plays. That is how the bot can
hear CS2's voice comms while ignoring Discord, a browser or music. None of the Python audio
packages expose it, so the little COM that is needed is spelled out here with ctypes.

Everything here is Windows-only and is reached through `blocks()`; off Windows, or on an older
Windows, `unavailable()` says why and the caller falls back to listening to the speakers.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable, Iterator
from ctypes import POINTER, Structure, byref, c_void_p, cast
from ctypes import wintypes as wt
from typing import Any

from .audio import SAMPLE_RATE, com_apartment

CS2_PROCESS = "cs2.exe"

VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_IEEE_FLOAT = 3
VT_BLOB = 65
CHANNELS = 2
REFTIMES_PER_SEC = 10_000_000
TH32CS_SNAPPROCESS = 0x2
INFINITE = 0xFFFFFFFF


class GUID(Structure):
    _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", wt.BYTE * 8)]

    @classmethod
    def of(cls, text: str) -> GUID:
        parts = text.strip("{}").split("-")
        tail = parts[3] + parts[4]
        return cls(
            int(parts[0], 16),
            int(parts[1], 16),
            int(parts[2], 16),
            (wt.BYTE * 8)(*(int(tail[i : i + 2], 16) for i in range(0, 16, 2))),
        )


IID_IUnknown = GUID.of("00000000-0000-0000-C000-000000000046")
IID_IAudioClient = GUID.of("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID.of("C8ADBD64-E71E-48a0-A4DE-185C395CD317")
IID_IActivateAudioInterfaceCompletionHandler = GUID.of("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAgileObject = GUID.of("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")


class _ProcessLoopbackParams(Structure):
    _fields_ = [("TargetProcessId", wt.DWORD), ("ProcessLoopbackMode", ctypes.c_int)]


class _ActivationParams(Structure):
    _fields_ = [("ActivationType", ctypes.c_int), ("ProcessLoopbackParams", _ProcessLoopbackParams)]


class _Blob(Structure):
    _fields_ = [("cbSize", wt.ULONG), ("pBlobData", c_void_p)]


class _PropVariant(Structure):
    _fields_ = [
        ("vt", wt.USHORT),
        ("r1", wt.WORD),
        ("r2", wt.WORD),
        ("r3", wt.WORD),
        ("blob", _Blob),
    ]


class _WaveFormatEx(Structure):
    _pack_ = 1
    _fields_ = [
        ("wFormatTag", wt.WORD),
        ("nChannels", wt.WORD),
        ("nSamplesPerSec", wt.DWORD),
        ("nAvgBytesPerSec", wt.DWORD),
        ("nBlockAlign", wt.WORD),
        ("wBitsPerSample", wt.WORD),
        ("cbSize", wt.WORD),
    ]


class _ProcessEntry(Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", wt.LONG),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def unavailable() -> str:
    """Empty when this Windows can capture a single process, otherwise why it cannot."""
    if sys.platform != "win32":
        return "capturing one program's audio only works on Windows"
    try:
        activate = ctypes.WinDLL("Mmdevapi").ActivateAudioInterfaceAsync  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return "this Windows cannot capture one program's audio (needs Windows 10 2004 or newer)"
    if activate is None or sys.getwindowsversion().build < 19041:  # type: ignore[attr-defined]
        return "this Windows cannot capture one program's audio (needs Windows 10 2004 or newer)"
    return ""


def find_process(name: str = CS2_PROCESS) -> int:
    """The pid of a running program by exe name, or 0 if it is not running."""
    if sys.platform != "win32":
        return 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wt.HANDLE(-1).value:
        return 0
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        ok = kernel32.Process32FirstW(snapshot, byref(entry))
        while ok:
            if entry.szExeFile.casefold() == name.casefold():
                return int(entry.th32ProcessID)
            ok = kernel32.Process32NextW(snapshot, byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return 0


# ---- the COM plumbing ------------------------------------------------------------------

_VTABLE = c_void_p * 1


def _method(obj: c_void_p, index: int, restype: object, *argtypes: object) -> Callable[..., Any]:
    """Method `index` of a COM interface pointer, as a callable."""
    vtable = cast(cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)  # type: ignore[attr-defined]
    return proto(vtable[index])


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise RuntimeError(f"{what} failed (0x{hr & 0xFFFFFFFF:08x})")


def _release(obj: c_void_p) -> None:
    if obj:
        _method(obj, 2, wt.ULONG)(obj)


class _CompletionHandler:
    """A minimal IActivateAudioInterfaceCompletionHandler that sets an event when activation lands."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.operation = c_void_p()
        qi = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))  # type: ignore[attr-defined]
        ref = ctypes.WINFUNCTYPE(wt.ULONG, c_void_p)  # type: ignore[attr-defined]
        completed = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)  # type: ignore[attr-defined]
        self._callbacks = [qi(self._query), ref(self._addref), ref(self._release), completed(self._completed)]
        self._vtable = (c_void_p * 4)(*(cast(cb, c_void_p) for cb in self._callbacks))
        self._object = (c_void_p * 1)(cast(self._vtable, c_void_p))
        self.pointer = cast(self._object, c_void_p)

    def _query(self, this: int, riid: Any, out: Any) -> int:
        iid = cast(riid, POINTER(GUID))[0]
        wanted = (IID_IUnknown, IID_IActivateAudioInterfaceCompletionHandler, IID_IAgileObject)
        if any(bytes(iid) == bytes(known) for known in wanted):
            cast(out, POINTER(c_void_p))[0] = this
            return 0
        return -2147467262  # E_NOINTERFACE

    def _addref(self, this: int) -> int:
        return 2

    def _release(self, this: int) -> int:
        return 1

    def _completed(self, this: int, operation: int) -> int:
        self.operation = c_void_p(operation)
        self.done.set()
        return 0


def _activate(pid: int) -> c_void_p:
    """An IAudioClient over `pid`'s audio, via ActivateAudioInterfaceAsync."""
    mmdevapi = ctypes.WinDLL("Mmdevapi")  # type: ignore[attr-defined]
    params = _ActivationParams(
        AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        _ProcessLoopbackParams(pid, PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE),
    )
    prop = _PropVariant()
    prop.vt = VT_BLOB
    prop.blob = _Blob(ctypes.sizeof(params), cast(byref(params), c_void_p))
    handler = _CompletionHandler()
    operation = c_void_p()
    _check(
        mmdevapi.ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            byref(IID_IAudioClient),
            byref(prop),
            handler.pointer,
            byref(operation),
        ),
        "ActivateAudioInterfaceAsync",
    )
    if not handler.done.wait(5.0):
        raise RuntimeError("Windows did not answer the process-loopback request")
    result = ctypes.c_long()
    client = c_void_p()
    # IActivateAudioInterfaceAsyncOperation::GetActivateResult is slot 3
    _check(
        _method(handler.operation, 3, ctypes.c_long, POINTER(ctypes.c_long), POINTER(c_void_p))(
            handler.operation, byref(result), byref(client)
        ),
        "GetActivateResult",
    )
    _release(operation)
    _check(result.value, "activating the process-loopback client")
    if not client:
        raise RuntimeError("process loopback returned no audio client")
    return client


def _format() -> _WaveFormatEx:
    block = CHANNELS * 4
    return _WaveFormatEx(WAVE_FORMAT_IEEE_FLOAT, CHANNELS, SAMPLE_RATE, SAMPLE_RATE * block, block, 32, 0)


def blocks(process: str = CS2_PROCESS, block_seconds: float = 0.05) -> Iterator[list[float]]:
    """Yield mono blocks of what `process` is playing, forever; raises if it cannot."""
    missing = unavailable()
    if missing:
        raise RuntimeError(missing)
    pid = find_process(process)
    if not pid:
        raise RuntimeError(f"{process} is not running")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    frames_per_block = max(1, int(SAMPLE_RATE * block_seconds))
    with com_apartment():
        client = _activate(pid)
        capture = c_void_p()
        event = kernel32.CreateEventW(None, False, False, None)
        try:
            flags = (
                AUDCLNT_STREAMFLAGS_LOOPBACK
                | AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
                | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
            )
            fmt = _format()
            # IAudioClient: Initialize=3, Start=10, Stop=11, SetEventHandle=13, GetService=14
            _check(
                _method(
                    client,
                    3,
                    ctypes.c_long,
                    wt.DWORD,
                    wt.DWORD,
                    ctypes.c_longlong,
                    ctypes.c_longlong,
                    POINTER(_WaveFormatEx),
                    POINTER(GUID),
                )(client, AUDCLNT_SHAREMODE_SHARED, flags, REFTIMES_PER_SEC // 5, 0, byref(fmt), None),
                "IAudioClient.Initialize",
            )
            _check(_method(client, 13, ctypes.c_long, wt.HANDLE)(client, event), "SetEventHandle")
            _check(
                _method(client, 14, ctypes.c_long, POINTER(GUID), POINTER(c_void_p))(
                    client, byref(IID_IAudioCaptureClient), byref(capture)
                ),
                "GetService(IAudioCaptureClient)",
            )
            _check(_method(client, 10, ctypes.c_long)(client), "IAudioClient.Start")
            # IAudioCaptureClient: GetBuffer=3, ReleaseBuffer=4
            get_buffer = _method(
                capture,
                3,
                ctypes.c_long,
                POINTER(c_void_p),
                POINTER(wt.UINT),
                POINTER(wt.DWORD),
                POINTER(ctypes.c_ulonglong),
                POINTER(ctypes.c_ulonglong),
            )
            release_buffer = _method(capture, 4, ctypes.c_long, wt.UINT)
            pending: list[float] = []
            while True:
                kernel32.WaitForSingleObject(event, 200)
                while True:
                    data = c_void_p()
                    frames = wt.UINT()
                    bflags = wt.DWORD()
                    hr = get_buffer(capture, byref(data), byref(frames), byref(bflags), None, None)
                    if hr == 0x08890001 or frames.value == 0:  # AUDCLNT_S_BUFFER_EMPTY
                        break
                    _check(hr, "GetBuffer")
                    count = frames.value * CHANNELS
                    if bflags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data:
                        samples = [0.0] * count
                    else:
                        samples = cast(data, POINTER(ctypes.c_float * count))[0][:]
                    release_buffer(capture, frames.value)
                    pending.extend((samples[i] + samples[i + 1]) / 2 for i in range(0, count, CHANNELS))
                while len(pending) >= frames_per_block:
                    yield pending[:frames_per_block]
                    del pending[:frames_per_block]
        finally:
            if capture:
                _release(capture)
            _method(client, 11, ctypes.c_long)(client)
            _release(client)
            kernel32.CloseHandle(event)
