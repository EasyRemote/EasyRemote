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
        bootstrap: Callable[[], None] = easynet_sdk.bootstrap_local_runtime_host,
    ) -> None:
        self._environment_factory = environment_factory
        self._identity_loader = identity_loader
        self._bootstrap = bootstrap

    def connect(self) -> easynet_sdk.RuntimeConnection:
        self._require_identity()
        try:
            return self._environment_factory().runtime_connection()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def _require_identity(self) -> None:
        """Load this device's identity, bootstrapping a local one on first run.

        A machine with no identity has not necessarily opted out of EasyNet —
        on a fresh install it simply has not run anything yet. The Runtime owns
        the local bootstrap (`localhost` realm, Device identity, daemon), so
        this triggers it once and re-reads. Identity is never minted here.
        """
        try:
            self._identity_loader()
            return
        except Unavailable as exc:
            if exc.reason not in {
                "not_paired",
                "not_paired_corrupt",
                "credentials_incomplete",
            }:
                raise
            first_failure = exc

        # Corrupt or half-written credentials are a different problem from a
        # fresh install: re-running the bootstrap would not repair them, and
        # could obscure the real cause.
        if first_failure.reason != "not_paired":
            raise Unavailable(
                "This device's EasyNet identity is present but unusable "
                f"({first_failure.reason}).\n\n"
                "To discard it and create a new local identity, run:\n"
                "  easynet device reset\n"
                "  easynet runtime start\n",
                reason="onboarding_required",
            ) from first_failure

        # The SDK owns runtime-host lifecycle, including the first-run local
        # bootstrap. Its failures arrive in the SDK taxonomy and are projected
        # into the product one here, like every other SDK call in this class.
        try:
            self._bootstrap()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

        try:
            self._identity_loader()
        except Unavailable as exc:
            raise Unavailable(
                "The EasyNet Runtime started but this device still has no "
                "identity.\n\n"
                "Run this to inspect the local realm:\n"
                "  easynet runtime status\n",
                reason="onboarding_required",
            ) from exc
