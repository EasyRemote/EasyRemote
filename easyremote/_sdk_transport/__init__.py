"""Private transport layer over the EasyNet-Cli SDK facade.

EasyRemote keeps its historical ``Transport``/``FrameStream`` shape, but daemon
I/O now enters through ``easynet_sdk``. Raw C ABI loading, unary wait state, and
bidi session lifecycle semantics are owned by the SDK package, not by
EasyRemote.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import easynet_sdk

from ..config import settings
from ..errors import error_from_sdk

__all__ = [
    "DaemonProcess",
    "FrameStream",
    "Transport",
    "UnaryDispatchPool",
]


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
            raise error_from_sdk(exc) from exc

    def invoke(self, invocation: Mapping[str, object]) -> dict[str, Any]:
        try:
            return dict(self._adapter.invoke(invocation))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invoke_signed(
        self,
        invocation: Mapping[str, object],
        *,
        signer: easynet_sdk.Signer | None,
    ) -> dict[str, Any]:
        try:
            return dict(self._adapter.invoke_signed(invocation, signer=signer))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def stream(self, invocation: Mapping[str, object]) -> FrameStream:
        try:
            return FrameStream(self._adapter.stream(invocation))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def bidi(self, invocation: Mapping[str, object]) -> easynet_sdk.DaemonBidiChannel:
        try:
            return self._adapter.bidi(invocation)
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._adapter.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class UnaryDispatchPool:
    """EasyRemote error-mapping wrapper over the SDK unary dispatch pool."""

    def __init__(self, pool: easynet_sdk.EasyRemoteUnaryDispatchPool) -> None:
        self._pool = pool

    @classmethod
    def connect(cls) -> UnaryDispatchPool:
        def factory() -> easynet_sdk.EasyRemoteUnaryTransport:
            return cast(easynet_sdk.EasyRemoteUnaryTransport, Transport.connect())

        return cls(easynet_sdk.EasyRemoteUnaryDispatchPool(factory))

    @classmethod
    def from_transport(cls, transport: Transport) -> UnaryDispatchPool:
        return cls(
            easynet_sdk.EasyRemoteUnaryDispatchPool.from_transport(
                cast(easynet_sdk.EasyRemoteUnaryTransport, transport)
            )
        )

    def invoke(
        self, invocation: Mapping[str, object], *, timeout: float | None = None
    ) -> dict[str, Any]:
        try:
            return dict(self._pool.invoke(invocation, timeout=timeout))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invoke_signed(
        self,
        invocation: Mapping[str, object],
        *,
        signer: easynet_sdk.Signer | None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            return dict(
                self._pool.invoke_signed(
                    invocation,
                    signer=signer,
                    timeout=timeout,
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._pool.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    @property
    def current_transport(self) -> Transport | None:
        return cast(Transport | None, self._pool.current_transport)

    def connected_transport(self) -> Transport:
        return cast(Transport, self._pool.connected_transport())


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
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._stream.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

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


class DaemonProcess:
    """Lifecycle handle wrapper over the SDK daemon facade."""

    def __init__(self, handle: easynet_sdk.EasyRemoteDaemonHandleFacade) -> None:
        self._handle = handle

    @classmethod
    def start(
        cls, config: easynet_sdk.EasyRemoteDaemonStartConfig
    ) -> DaemonProcess:
        try:
            lifecycle = easynet_sdk.EasyRemoteDaemonLifecycleFacade(
                _environment().daemon_control()
            )
            return cls(lifecycle.start(config))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def status(self) -> dict[str, Any]:
        try:
            return self._handle.status_dict()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invocation_endpoint(self) -> str:
        try:
            return self._handle.invocation_endpoint()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def open_client(self) -> Transport:
        try:
            return Transport(
                self._handle.open_transport_adapter()
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def stop(self) -> None:
        try:
            self._handle.stop()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

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
