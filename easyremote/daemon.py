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

from ._sdk_transport import DaemonProcess, Transport
from .errors import InvalidArgument

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
        if not realm:
            raise InvalidArgument("hub realm must not be empty", reason="empty_realm")
        return cls(
            mode="hub",
            realm=realm,
            env=env,
            log_path=Path(log_path) if log_path is not None else None,
            detached=detached,
        )

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
        if self.mode not in ("device", "hub"):
            raise InvalidArgument(
                f"unsupported daemon mode {self.mode!r}", reason="invalid_daemon_mode"
            )
        if self.mode == "device" and not self.node_id:
            raise InvalidArgument(
                "device daemon start requires a node_id",
                reason="missing_node_id",
            )
        wire: dict[str, Any] = {"mode": self.mode}
        if self.realm is not None:
            wire["realm"] = self.realm
        if self.node_id is not None:
            wire["node_id"] = self.node_id
        if self.env:
            wire["env"] = dict(self.env)
        if self.log_path is not None:
            wire["log_path"] = str(self.log_path)
        if self.detached is not None:
            wire["detach"] = self.detached
        return wire


class DaemonHandle:
    """A running daemon process started by this Python process."""

    def __init__(self, process: DaemonProcess) -> None:
        self._process = process

    @classmethod
    def start(cls, config: DaemonStartConfig) -> DaemonHandle:
        return cls(DaemonProcess.start(config.to_wire()))

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
