"""Configuration and daemon discovery (SPEC §5.10).

The zero-config chain is ``Client()`` → SDK environment → daemon runtime.
This module owns product path overrides and public error projection; the SDK
owns discovery and interpretation of daemon state, including paired identity.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import easynet_sdk

from .errors import Unavailable, is_runtime_offline_error

__all__ = ["Settings", "agents_root", "configure", "sdk_environment", "settings"]

_DESKTOP_EASYNET_DIR = Path.home() / ".easynet"


def agents_root() -> Path:
    """Where agent roots live (``~/.easynet/agents/<name>/``).

    Mirrors EasyNet-Cli ``config::agents_root()`` (new convention);
    the legacy ``workspaces/`` location is deliberately not supported.
    """
    return settings().control_path.parent / "agents"


_ENV_CREDENTIALS = "EASYNET_CREDENTIALS"
_ENV_CONTROL = "EASYNET_CONTROL_JSON"
_ENV_LIBRARY = "EASYNET_CLI_LIB"


@dataclass(frozen=True)
class Settings:
    """Resolved configuration. Immutable; replaced atomically by configure()."""

    credentials_path: Path
    control_path: Path
    library_path: Path | None


def _from_environment() -> Settings:
    library = os.environ.get(_ENV_LIBRARY)
    control = os.environ.get(_ENV_CONTROL)
    credentials = os.environ.get(_ENV_CREDENTIALS)
    root = _default_runtime_state_root()
    control_path = Path(control) if control else root / "control.json"
    return Settings(
        credentials_path=Path(credentials)
        if credentials
        else control_path.parent / "credentials.json",
        control_path=control_path,
        library_path=Path(library) if library else None,
    )


_lock = threading.Lock()
_settings: Settings | None = None


def configure(
    *,
    credentials: str | Path | None = None,
    control: str | Path | None = None,
    library_path: str | Path | None = None,
) -> None:
    """Override discovery paths for this process.

    Unspecified fields keep their current value (environment-derived on
    first use). Equivalent environment variables: ``EASYNET_CREDENTIALS``,
    ``EASYNET_CONTROL_JSON``, ``EASYNET_CLI_LIB``.
    """
    global _settings
    with _lock:
        current = _settings or _from_environment()
        if credentials is not None:
            current = replace(current, credentials_path=Path(credentials))
        if control is not None:
            current = replace(current, control_path=Path(control))
        if library_path is not None:
            current = replace(current, library_path=Path(library_path))
        _settings = current


def settings() -> Settings:
    """Current settings; built from the environment on first access."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = _from_environment()
        return _settings


def sdk_environment(
    *,
    control_path: str | Path | None = None,
) -> easynet_sdk.SdkEnvironment:
    """Create the SDK runtime environment from the EasyRemote process root.

    EasyRemote owns product path overrides; the SDK owns daemon runtime
    discovery, feature negotiation and transport construction. All consumers
    that need an SDK process root should use this entrypoint so control-path
    and library-path projection stays single-sourced.
    """

    current = settings()
    library_path = (
        str(current.library_path) if current.library_path is not None else None
    )
    return easynet_sdk.SdkEnvironment(
        library_path=library_path,
        control_path=str(control_path or current.control_path),
    )


def read_control() -> dict[str, Any]:
    """Load the daemon discovery file written at daemon boot.

    Raises:
        Unavailable: with reason ``daemon_not_running`` when the file is
            absent — the daemon writes it on startup, so absence means
            there is no daemon to talk to.
    """
    path = settings().control_path
    try:
        discovery = easynet_sdk.read_runtime_control_discovery(path)
    except easynet_sdk.SDKError as exc:
        raise _control_discovery_error(path, exc) from exc
    return _control_discovery_dict(discovery)


def read_credentials() -> dict[str, Any]:
    """Return the SDK-projected public paired identity metadata.

    Raises:
        Unavailable: with reason ``not_paired`` when the file is absent —
            identity only exists after a one-time `easynet pair`.
    """
    projection = runtime_identity_projection()
    user_id: object = None
    if projection.principal:
        principal = easynet_sdk.parse_ura(projection.principal)
        user_id = principal.components.get("user_id")
    return {
        "realm": projection.realm,
        "node_id": projection.runtime_instance_id,
        "username": projection.principal_display_name or None,
        "user_id": str(user_id) if isinstance(user_id, str) else None,
        "hub_endpoint": projection.control_plane_endpoint,
    }


def runtime_identity_projection() -> easynet_sdk.RuntimeIdentityProjection:
    current = settings()
    try:
        return sdk_environment().paired_runtime_identity_projection(
            current.credentials_path
        )
    except easynet_sdk.SDKError as exc:
        raise _runtime_identity_projection_error(
            current.credentials_path,
            exc,
        ) from exc


def _default_runtime_state_root() -> Path:
    sdk_root = Path(easynet_sdk.runtime_state_root())
    if _runtime_state_root_is_populated(_DESKTOP_EASYNET_DIR):
        return _DESKTOP_EASYNET_DIR
    return sdk_root


def _runtime_state_root_is_populated(path: Path) -> bool:
    return (path / "control.json").exists() or (path / "credentials.json").exists()


def _control_discovery_dict(
    discovery: easynet_sdk.RuntimeControlDiscovery,
) -> dict[str, Any]:
    return {
        "socket_path": discovery.socket_path,
        "pipe_name": discovery.pipe_name,
        "invocation_endpoint": discovery.invocation_endpoint,
        "pid": discovery.pid,
        "daemon_version": discovery.runtime_host_version,
        "supported_ipc_versions": {
            "min": discovery.supported_ipc_versions.min,
            "max": discovery.supported_ipc_versions.max,
        },
        "capability_flags": list(discovery.capability_flags),
    }


def _control_discovery_error(path: Path, error: easynet_sdk.SDKError) -> Unavailable:
    if is_runtime_offline_error(error):
        return Unavailable(
            f"no easynet-daemon discovery file — start the daemon with `easynet start`"
            f" (looked at {path})",
            reason="daemon_not_running",
        )
    return Unavailable(
        f"{path} is not a valid daemon control discovery file ({error.message})"
        " — re-run `easynet start`",
        reason="daemon_not_running_corrupt",
    )


def _runtime_identity_projection_error(
    path: Path,
    error: easynet_sdk.SDKError,
) -> Unavailable:
    if is_runtime_offline_error(error) or (
        error.code == easynet_sdk.ErrorCode.CALLER_IDENTITY_UNAVAILABLE
    ):
        return Unavailable(
            "no EasyNet identity on this machine — pair it once with "
            f"`easynet pair` (looked at {path})",
            reason="not_paired",
        )
    return Unavailable(
        f"{path} is not a valid runtime identity projection ({error.message})"
        " — re-run `easynet pair`",
        reason="not_paired_corrupt",
    )
