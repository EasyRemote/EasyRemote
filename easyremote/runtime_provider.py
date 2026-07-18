"""Canonical runtime connection acquisition for EasyRemote consumers.

EasyRemote owns product authoring policy and local function hosting. The
EasyNet-Cli SDK owns runtime discovery, connection state, and daemon process
lifecycle. This module only acquires an SDK ``RuntimeConnection`` for the
product host to use and release.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import easynet_sdk

from .config import sdk_environment
from .errors import Unavailable, error_from_sdk
from .identity import LocalIdentity

__all__ = ["LocalRuntimeProvider", "RuntimeConnectionProvider"]


class RuntimeConnectionProvider(Protocol):
    """Acquire a connection to an operator-managed canonical runtime."""

    def connect(self) -> easynet_sdk.RuntimeConnection: ...


class LocalRuntimeProvider:
    """Connect to the paired local runtime through the canonical SDK."""

    def __init__(
        self,
        *,
        environment_factory: Callable[[], easynet_sdk.SdkEnvironment] = sdk_environment,
        identity_loader: Callable[[], LocalIdentity] = LocalIdentity.load,
    ) -> None:
        self._environment_factory = environment_factory
        self._identity_loader = identity_loader

    def connect(self) -> easynet_sdk.RuntimeConnection:
        self._require_identity()
        try:
            return self._environment_factory().runtime_connection()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def _require_identity(self) -> None:
        try:
            self._identity_loader()
        except Unavailable as exc:
            if exc.reason not in {
                "not_paired",
                "not_paired_corrupt",
                "credentials_incomplete",
            }:
                raise
            raise Unavailable(
                "No EasyNet identity found for this device.\n\n"
                "To pair this device, run:\n"
                "  easynet pair\n\n"
                "Then restart this EasyRemote application.",
                reason="onboarding_required",
            ) from exc
