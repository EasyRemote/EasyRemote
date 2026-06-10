"""ctypes binding for libeasynet_cli, C ABI v3.

Source of truth: ``EasyNet-Cli/include/easynet_cli.h``. Ownership rules
encoded here:

- ``char **`` out-strings are daemon-allocated and must be released via
  ``easynet_string_free`` (done in :meth:`Library._read_out_string`).
- ``easynet_last_error()`` returns a borrowed ``const char *`` — never
  freed.
- Stream/bidi callbacks arrive on library-owned background threads and
  borrow their argument only for the duration of the call; callers of
  :meth:`Library.stream_open`/:meth:`Library.bidi_open` must keep the
  callback object alive until after the terminal action.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import platform
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..config import settings
from ..errors import Unavailable, error_from_abi

__all__ = ["ABI_VERSION", "Library", "library"]

ABI_VERSION = 3

# typedef void (*Callback)(void *user_data, const char *json);
RawCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p)

_Handle = ctypes.c_uint64


class Library:
    """A loaded libeasynet_cli with typed prototypes and error checking.

    Thin and stateless beyond the ``CDLL``: handles are plain integers
    owned by the session layer.
    """

    def __init__(self, cdll: ctypes.CDLL) -> None:
        self._lib = cdll
        # Handshake before declaring the full surface: a stale library
        # then fails with a version story, not a raw dlsym error.
        self._declare_util_prototypes()
        version = self._lib.easynet_abi_version()
        if version != ABI_VERSION:
            raise Unavailable(
                f"libeasynet_cli speaks ABI v{version}, this package requires"
                f" v{ABI_VERSION} — rebuild the EasyNet CLI"
                " (`cargo build --release --lib`) or point EASYNET_CLI_LIB at"
                " a current library",
                reason="abi_mismatch",
            )
        try:
            self._declare_prototypes()
        except AttributeError as exc:
            raise Unavailable(
                f"libeasynet_cli reports ABI v{version} but lacks a v{ABI_VERSION}"
                f" symbol ({exc}) — the library and its header are out of sync;"
                " rebuild the EasyNet CLI",
                reason="abi_symbol_missing",
            ) from None

    # -- lifecycle ---------------------------------------------------------

    def init(self, control_json_path: Path) -> int:
        handle = _Handle()
        self._check(
            self._lib.easynet_init(
                _encode(str(control_json_path)), ctypes.byref(handle)
            )
        )
        return handle.value

    def shutdown(self, handle: int) -> None:
        self._check(self._lib.easynet_shutdown(handle))

    def daemon_start(self, config_json: str) -> int:
        handle = _Handle()
        self._check(
            self._lib.easynet_daemon_start(_encode(config_json), ctypes.byref(handle))
        )
        return handle.value

    def daemon_stop(self, daemon_handle: int) -> None:
        self._check(self._lib.easynet_daemon_stop(daemon_handle))

    def daemon_status(self, daemon_handle: int) -> str:
        out = ctypes.c_char_p()
        self._check(self._lib.easynet_daemon_status(daemon_handle, ctypes.byref(out)))
        return self._read_out_string(out)

    def daemon_invocation_endpoint(self, daemon_handle: int) -> str:
        out = ctypes.c_char_p()
        self._check(
            self._lib.easynet_daemon_invocation_endpoint(
                daemon_handle, ctypes.byref(out)
            )
        )
        return self._read_out_string(out)

    def daemon_open_client(self, daemon_handle: int) -> int:
        handle = _Handle()
        self._check(
            self._lib.easynet_daemon_open_client(daemon_handle, ctypes.byref(handle))
        )
        return handle.value

    # -- invocation --------------------------------------------------------

    def invoke(self, handle: int, invocation_json: str) -> str:
        out = ctypes.c_char_p()
        self._check(
            self._lib.easynet_invocation_invoke(
                handle, _encode(invocation_json), ctypes.byref(out)
            )
        )
        return self._read_out_string(out)

    def stream_open(self, handle: int, invocation_json: str, callback: Any) -> int:
        stream_id = _Handle()
        self._check(
            self._lib.easynet_invocation_stream_open(
                handle,
                _encode(invocation_json),
                callback,
                None,
                ctypes.byref(stream_id),
            )
        )
        return stream_id.value

    def stream_cancel(self, handle: int, stream_id: int) -> None:
        self._check(self._lib.easynet_invocation_stream_cancel(handle, stream_id))

    def bidi_open(self, handle: int, invocation_json: str, callback: Any) -> int:
        bidi_id = _Handle()
        self._check(
            self._lib.easynet_invocation_bidi_open(
                handle, _encode(invocation_json), callback, None, ctypes.byref(bidi_id)
            )
        )
        return bidi_id.value

    def bidi_send(self, handle: int, bidi_id: int, frame_json: str) -> None:
        self._check(
            self._lib.easynet_invocation_bidi_send(handle, bidi_id, _encode(frame_json))
        )

    def bidi_close(self, handle: int, bidi_id: int) -> None:
        self._check(self._lib.easynet_invocation_bidi_close(handle, bidi_id))

    def bidi_cancel(self, handle: int, bidi_id: int) -> None:
        self._check(self._lib.easynet_invocation_bidi_cancel(handle, bidi_id))

    # -- internals ---------------------------------------------------------

    def _check(self, code: int) -> None:
        if code != 0:
            raise error_from_abi(code, self._last_error())

    def _last_error(self) -> str:
        raw = self._lib.easynet_last_error()  # borrowed const char*, never freed
        return raw.decode("utf-8", errors="replace") if raw else ""

    def _read_out_string(self, out: ctypes.c_char_p) -> str:
        if not out.value:
            return ""
        try:
            return out.value.decode("utf-8")
        finally:
            self._lib.easynet_string_free(out)

    def _declare_util_prototypes(self) -> None:
        lib = self._lib
        lib.easynet_abi_version.restype = ctypes.c_uint32
        lib.easynet_abi_version.argtypes = []
        lib.easynet_last_error.restype = ctypes.c_char_p
        lib.easynet_last_error.argtypes = []
        lib.easynet_string_free.restype = None
        lib.easynet_string_free.argtypes = [ctypes.c_char_p]

    def _declare_prototypes(self) -> None:
        lib = self._lib
        i32 = ctypes.c_int32
        char_p = ctypes.c_char_p
        out_str = ctypes.POINTER(ctypes.c_char_p)
        out_handle = ctypes.POINTER(_Handle)

        signatures: dict[str, list[object]] = {
            "easynet_init": [char_p, out_handle],
            "easynet_shutdown": [_Handle],
            "easynet_daemon_start": [char_p, out_handle],
            "easynet_daemon_stop": [_Handle],
            "easynet_daemon_status": [_Handle, out_str],
            "easynet_daemon_invocation_endpoint": [_Handle, out_str],
            "easynet_daemon_open_client": [_Handle, out_handle],
            "easynet_invocation_invoke": [_Handle, char_p, out_str],
            "easynet_invocation_stream_open": [
                _Handle,
                char_p,
                RawCallback,
                ctypes.c_void_p,
                out_handle,
            ],
            "easynet_invocation_stream_cancel": [_Handle, _Handle],
            "easynet_invocation_bidi_open": [
                _Handle,
                char_p,
                RawCallback,
                ctypes.c_void_p,
                out_handle,
            ],
            "easynet_invocation_bidi_send": [_Handle, _Handle, char_p],
            "easynet_invocation_bidi_close": [_Handle, _Handle],
            "easynet_invocation_bidi_cancel": [_Handle, _Handle],
        }
        for name, argtypes in signatures.items():
            fn = getattr(lib, name)
            fn.restype = i32
            fn.argtypes = argtypes


def _encode(text: str) -> bytes:
    return text.encode("utf-8")


def _platform_library_name() -> str:
    if sys.platform == "darwin":
        return "libeasynet_cli.dylib"
    if sys.platform == "win32":
        return "easynet_cli.dll"
    return "libeasynet_cli.so"


def candidate_paths(explicit: Path | None) -> Iterator[Path | str]:
    """Library resolution order (SPEC §4.2): explicit/env → wheel → system."""
    if explicit is not None:
        yield explicit
        return  # an explicit path is a contract, not a hint — no fallback
    bundled_dir = (
        Path(__file__).parent / "_lib" / f"{sys.platform}-{platform.machine()}"
    )
    yield bundled_dir / _platform_library_name()
    found = ctypes.util.find_library("easynet_cli")
    if found:
        yield found
    yield _platform_library_name()  # last resort: dlopen search path


_lock = threading.Lock()
_cached: Library | None = None


def library() -> Library:
    """The process-wide :class:`Library`, loaded on first use.

    Honors ``configure(library_path=...)`` / ``EASYNET_CLI_LIB`` at first
    load; subsequent calls return the cached instance.
    """
    global _cached
    with _lock:
        if _cached is None:
            _cached = _load(settings().library_path)
        return _cached


def _load(explicit: Path | None) -> Library:
    attempts: list[str] = []
    for candidate in candidate_paths(explicit):
        try:
            return Library(ctypes.CDLL(str(candidate)))
        except OSError as exc:
            attempts.append(f"{candidate}: {exc}")
    raise Unavailable(
        "libeasynet_cli not found — install the EasyNet CLI or point"
        " EASYNET_CLI_LIB at the library. Tried:\n  " + "\n  ".join(attempts),
        reason="library_not_found",
    )


def _reset_for_tests() -> None:
    global _cached
    with _lock:
        _cached = None
