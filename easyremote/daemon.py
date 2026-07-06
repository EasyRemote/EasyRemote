"""Daemon lifecycle facade over the EasyNet-Cli SDK.

This module is the public EasyRemote boundary for starting and holding an
``easynet-daemon`` process. It owns lifecycle shape only. Protocol
semantics, invocation routing, admission, and receipts stay below this
facade in the SDK / easynet-daemon / Axon.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import easynet_sdk

from ._sdk_transport import DaemonProcess, Transport
from .errors import InvalidArgument, RemoteError, error_from_sdk

__all__ = ["DaemonHandle", "DaemonStartConfig"]

DaemonMode = Literal["device", "hub"]


@dataclass(frozen=True)
class DaemonStartConfig:
    """Start config accepted by the daemon lifecycle ABI."""

    mode: DaemonMode
    realm: str | None = None
    node_id: str | None = None
    env: Mapping[str, str] | None = None
    log_path: Path | None = None
    detached: bool | None = None

    @classmethod
    def hub(
        cls,
        realm: str,
        *,
        env: Mapping[str, str] | None = None,
        log_path: str | Path | None = None,
        detached: bool | None = None,
    ) -> DaemonStartConfig:
        realm = realm.strip()
        config = cls(
            mode="hub",
            realm=realm,
            env=env,
            log_path=Path(log_path) if log_path is not None else None,
            detached=detached,
        )
        config._to_sdk()
        return config

    @classmethod
    def device(
        cls,
        node_id: str | None = None,
        *,
        env: Mapping[str, str] | None = None,
        log_path: str | Path | None = None,
        detached: bool | None = None,
    ) -> DaemonStartConfig:
        node = node_id.strip() if node_id is not None else None
        return cls(
            mode="device",
            node_id=node or None,
            env=env,
            log_path=Path(log_path) if log_path is not None else None,
            detached=detached,
        )

    def to_wire(self) -> dict[str, Any]:
        config = self._to_sdk()
        value: dict[str, Any] = {"mode": config.mode.value}
        if config.realm:
            value["realm"] = config.realm
        if config.device_id:
            value["node_id"] = config.device_id
        if config.env:
            value["env"] = dict(config.env)
        if config.log_path:
            value["log_path"] = config.log_path
        if config.detached is not None:
            value["detach"] = config.detached
        return value

    def to_wire_dict(self) -> dict[str, Any]:
        return self.to_wire()

    def _to_sdk(self) -> easynet_sdk.DaemonStartProjection:
        if self.mode == "device" and not (self.node_id or "").strip():
            raise InvalidArgument(
                "device daemon start requires a node_id",
                reason="missing_node_id",
            )
        try:
            return easynet_sdk.DaemonStartProjection.from_profile(
                mode=self.mode,
                realm=self.realm or "",
                device_id=self.node_id or "",
                env=self.env or {},
                log_path=str(self.log_path) if self.log_path is not None else "",
                detached=self.detached,
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc


class DaemonHandle:
    """A running daemon process started by this Python process."""

    def __init__(self, process: DaemonProcess) -> None:
        self._process = process

    @classmethod
    def start(cls, config: DaemonStartConfig) -> DaemonHandle:
        return cls(_start_process(config))

    @classmethod
    def start_hub(cls, realm: str, **kwargs: Any) -> DaemonHandle:
        return cls.start(DaemonStartConfig.hub(realm, **kwargs))

    @classmethod
    def start_device(cls, node_id: str, **kwargs: Any) -> DaemonHandle:
        return cls.start(DaemonStartConfig.device(node_id, **kwargs))

    def status(self) -> dict[str, Any]:
        return self._process.status()

    def invocation_endpoint(self) -> str:
        return self._process.invocation_endpoint()

    def open_client(self) -> Transport:
        return self._process.open_client()

    def stop(self) -> None:
        self._process.stop()

    def __enter__(self) -> DaemonHandle:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def _start_process(config: DaemonStartConfig) -> DaemonProcess:
    try:
        return DaemonProcess.start(config)
    except RemoteError:
        raise
    except easynet_sdk.SDKError as exc:
        raise error_from_sdk(exc) from exc
