"""Private transport layer over the EasyNet-Cli SDK facade.

EasyRemote keeps its historical ``Transport``/``FrameStream``/``BidiChannel``
shape, but daemon I/O now enters through ``easynet_sdk``. Raw C ABI loading is
owned by the SDK package, not by EasyRemote.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import easynet_sdk

from ..config import settings
from ..errors import (
    Cancelled,
    DeadlineExceeded,
    InternalError,
    InvalidArgument,
    PermissionDenied,
    RemoteError,
    Unavailable,
)

__all__ = ["BidiChannel", "DaemonProcess", "FrameStream", "Transport"]


class Transport:
    """EasyRemote transport wrapper over ``easynet_sdk`` Invocation transport."""

    def __init__(self, adapter: easynet_sdk.EasyRemoteTransportAdapter) -> None:
        self._adapter = adapter

    @classmethod
    def connect(cls, control_path: str | None = None) -> Transport:
        try:
            return cls(
                easynet_sdk.EasyRemoteTransportAdapter.connect(
                    control_path=control_path or str(settings().control_path),
                    library_path=_library_path(),
                )
            )
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def invoke(self, invocation: Mapping[str, object]) -> dict[str, Any]:
        try:
            return dict(self._adapter.invoke(invocation))
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def stream(self, invocation: Mapping[str, object]) -> FrameStream:
        try:
            return FrameStream(self._adapter.stream(invocation))
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def bidi(self, invocation: Mapping[str, object]) -> BidiChannel:
        try:
            return BidiChannel(self._adapter.bidi(invocation))
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def close(self) -> None:
        try:
            self._adapter.close()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass
class FrameStream:
    """Server-stream wrapper that preserves EasyRemote's frame API."""

    _stream: easynet_sdk.DaemonFrameStream

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return dict(self._stream.recv(timeout=timeout))
        except StopIteration:
            return None
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def close(self) -> None:
        try:
            self._stream.close()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while True:
            frame = self.recv()
            if frame is None:
                return
            yield frame
            if frame.get("terminal") is True:
                return

    def __enter__(self) -> FrameStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass
class BidiChannel:
    """Bidirectional session wrapper that preserves EasyRemote's channel API."""

    _channel: easynet_sdk.DaemonBidiChannel

    def send(self, frame: Mapping[str, object]) -> None:
        try:
            self._channel.send(frame)
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return dict(self._channel.recv(timeout=timeout))
        except StopIteration:
            return None
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def close(self) -> None:
        try:
            self._channel.close()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def cancel(self) -> None:
        try:
            self._channel.cancel()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def __enter__(self) -> BidiChannel:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class DaemonProcess:
    """Lifecycle handle wrapper over the SDK daemon facade."""

    def __init__(self, handle: easynet_sdk.DaemonHandle) -> None:
        self._handle = handle

    @classmethod
    def start(cls, config: Mapping[str, object]) -> DaemonProcess:
        try:
            return cls(_environment().daemon_control().start(_start_config(config)))
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def status(self) -> dict[str, Any]:
        try:
            status = self._handle.status()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc
        return {
            "state": status.state.value,
            "handle_id": status.handle_id,
            "mode": status.mode.value if status.mode is not None else "",
            "pid": status.pid,
            "version": status.version,
            "message": status.message,
            "endpoints": {
                "control_endpoint": status.endpoints.control_endpoint,
                "invocation_endpoint": status.endpoints.invocation_endpoint,
                "public_endpoint": status.endpoints.public_endpoint,
            },
            "diagnostics": list(status.diagnostics),
        }

    def invocation_endpoint(self) -> str:
        try:
            return self._handle.invocation_endpoint()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def open_client(self) -> Transport:
        try:
            return Transport(
                easynet_sdk.EasyRemoteTransportAdapter.from_runtime_client(
                    self._handle.open_runtime()
                )
            )
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def stop(self) -> None:
        try:
            self._handle.stop()
        except easynet_sdk.SDKError as exc:
            raise _remote_error(exc) from exc

    def __enter__(self) -> DaemonProcess:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def _environment() -> easynet_sdk.SdkEnvironment:
    return easynet_sdk.SdkEnvironment(
        library_path=_library_path(),
        control_path=str(settings().control_path),
    )


def _library_path() -> str | None:
    path = settings().library_path
    return str(path) if path is not None else None


def _start_config(config: Mapping[str, object]) -> easynet_sdk.StartConfig:
    mode = easynet_sdk.DaemonMode(str(config.get("mode") or ""))
    env_value = config.get("env")
    env = {
        str(key): str(value)
        for key, value in env_value.items()
    } if isinstance(env_value, Mapping) else {}
    return easynet_sdk.StartConfig(
        mode=mode,
        realm=str(config.get("realm") or ""),
        device_id=str(config.get("node_id") or ""),
        log_path=str(config.get("log_path") or ""),
        detached=bool(config.get("detach")),
        env=env,
    )


def _remote_error(exc: easynet_sdk.SDKError) -> RemoteError:
    cls, reason = _ERROR_MAP.get(exc.code, (InternalError, exc.code.value.lower()))
    return cls(exc.message or str(exc), reason=reason)


_ERROR_MAP: dict[easynet_sdk.ErrorCode, tuple[type[RemoteError], str]] = {
    easynet_sdk.ErrorCode.INVALID_ARGUMENT: (InvalidArgument, "invalid_argument"),
    easynet_sdk.ErrorCode.INVALID_UTF8: (InvalidArgument, "invalid_utf8"),
    easynet_sdk.ErrorCode.NOT_FOUND: (InvalidArgument, "not_found"),
    easynet_sdk.ErrorCode.ABILITY_NOT_FOUND: (InvalidArgument, "ability_not_found"),
    easynet_sdk.ErrorCode.PERMISSION_DENIED: (PermissionDenied, "permission_denied"),
    easynet_sdk.ErrorCode.ADMISSION_DENIED: (PermissionDenied, "admission_denied"),
    easynet_sdk.ErrorCode.TIMEOUT: (DeadlineExceeded, "timeout"),
    easynet_sdk.ErrorCode.CANCELLED: (Cancelled, "cancelled"),
    easynet_sdk.ErrorCode.DAEMON_OFFLINE: (Unavailable, "daemon_down"),
    easynet_sdk.ErrorCode.NOT_INITIALIZED: (Unavailable, "not_initialized"),
    easynet_sdk.ErrorCode.VERSION_MISMATCH: (Unavailable, "version_mismatch"),
    easynet_sdk.ErrorCode.VERSION_INCOMPATIBLE: (Unavailable, "version_incompatible"),
    easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE: (Unavailable, "route_unavailable"),
    easynet_sdk.ErrorCode.CONTROL_ONLY: (Unavailable, "control_only"),
    easynet_sdk.ErrorCode.TRANSPORT: (Unavailable, "transport"),
}
