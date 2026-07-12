"""Device-runtime bootstrap for EasyRemote's one-file authoring path.

``ComputeNode`` is a product authoring surface, not a daemon lifecycle API.
This module turns the SDK-owned lifecycle primitives into one explicit,
testable state machine:

``SDK_READY -> IDENTITY_READY -> DAEMON_REUSED | DAEMON_STARTED``.

It never creates an identity or changes a realm. Pairing and authority remain
explicit operator actions; once pairing exists, starting a local device daemon
is safe, deterministic runtime bootstrap.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Protocol

import easynet_sdk

from ._sdk_transport import Transport
from .config import sdk_environment
from .daemon import DaemonHandle
from .errors import Unavailable, error_from_sdk
from .identity import LocalIdentity

__all__ = [
    "DeviceRuntimeBootstrap",
    "DeviceRuntimeLease",
    "RuntimeBootstrap",
    "RuntimeBootstrapState",
]


class RuntimeBootstrapState(StrEnum):
    """Terminal state of one device-runtime bootstrap attempt."""

    DAEMON_REUSED = "daemon_reused"
    DAEMON_STARTED = "daemon_started"


class RuntimeBootstrap(Protocol):
    """Narrow seam consumed by a product authoring surface."""

    def ensure(self) -> DeviceRuntimeLease: ...


@dataclass
class DeviceRuntimeLease:
    """A device runtime acquired for one ``ComputeNode`` lifecycle.

    A reused daemon remains process-owned. A daemon launched by this lease is
    stopped when the node's host cannot be published or when the node stops,
    which keeps bootstrap ownership explicit and prevents orphan processes.
    """

    identity: LocalIdentity
    state: RuntimeBootstrapState
    _started_daemon: DaemonHandle | None = None
    _closed: bool = False

    @property
    def started_daemon(self) -> bool:
        return self.state is RuntimeBootstrapState.DAEMON_STARTED

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started_daemon is not None:
            self._started_daemon.stop()


class DeviceRuntimeBootstrap:
    """Ensure the paired local device runtime is ready for publication.

    The SDK remains the sole implementation of ABI validation, runtime
    identity projection, daemon process start and daemon transport. This class
    only sequences those existing capabilities for EasyRemote's author flow.
    """

    _process_lock = Lock()

    def __init__(
        self,
        *,
        environment_factory: Callable[[], easynet_sdk.SdkEnvironment] = sdk_environment,
        identity_loader: Callable[[], LocalIdentity] = LocalIdentity.load,
        daemon_available: Callable[[], bool] | None = None,
        daemon_starter: Callable[[str], DaemonHandle] = DaemonHandle.start_device,
    ) -> None:
        self._environment_factory = environment_factory
        self._identity_loader = identity_loader
        self._daemon_available = daemon_available or _daemon_is_available
        self._daemon_starter = daemon_starter

    def ensure(self) -> DeviceRuntimeLease:
        """Validate SDK + pairing, then reuse or start the device daemon.

        The lock makes concurrent ``ComputeNode.start()`` calls converge on a
        single local daemon. Availability failures other than an offline daemon
        are preserved: a corrupt control file or ABI mismatch must not be
        papered over by launching another process.
        """

        self._require_sdk()
        identity = self._require_identity()
        with self._process_lock:
            if self._daemon_available():
                return DeviceRuntimeLease(
                    identity=identity,
                    state=RuntimeBootstrapState.DAEMON_REUSED,
                )
            try:
                handle = self._daemon_starter(identity.node_id)
            except easynet_sdk.SDKError as exc:
                raise error_from_sdk(exc) from exc
            return DeviceRuntimeLease(
                identity=identity,
                state=RuntimeBootstrapState.DAEMON_STARTED,
                _started_daemon=handle,
            )

    def _require_sdk(self) -> None:
        try:
            self._environment_factory().feature_set()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def _require_identity(self) -> LocalIdentity:
        try:
            return self._identity_loader()
        except Unavailable as exc:
            onboarding_errors = {
                "not_paired",
                "not_paired_corrupt",
                "credentials_incomplete",
            }
            if exc.reason not in onboarding_errors:
                raise
            raise Unavailable(
                "No EasyNet identity found for this device.\n\n"
                "To pair this device, run:\n"
                "  easynet pair\n\n"
                "Then restart this EasyRemote application.",
                reason="onboarding_required",
            ) from exc


def _daemon_is_available() -> bool:
    """Probe SDK transport instead of trusting a stale discovery file."""

    try:
        with Transport.connect():
            return True
    except Unavailable as exc:
        if exc.reason in {"daemon_down", "daemon_not_running"}:
            return False
        raise
