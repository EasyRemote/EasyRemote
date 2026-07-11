"""Configuration and daemon discovery (SPEC §5.10).

The zero-config chain: ``Client()`` → ``control.json`` → ``daemon.sock``;
identity → ``credentials.json``. This module owns only path resolution
and raw JSON loading with actionable errors — the *meaning* of those
files (which fields exist, what they imply) belongs to the consumers
that the P0 link verification has validated against a live daemon.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import easynet_sdk

from .errors import Unavailable

__all__ = ["Settings", "agents_root", "configure", "settings"]

# The SDK owns the process-level daemon discovery default. EasyRemote keeps
# product credentials beside that discovery file, but must derive the root
# from the SDK instead of maintaining a second home-directory convention.
_EASYNET_DIR = easynet_sdk.default_control_path().parent


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
    return Settings(
        credentials_path=Path(
            os.environ.get(_ENV_CREDENTIALS, _EASYNET_DIR / "credentials.json")
        ),
        control_path=Path(os.environ.get(_ENV_CONTROL, _EASYNET_DIR / "control.json")),
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


def read_control() -> dict[str, Any]:
    """Load the daemon discovery file written at daemon boot.

    Raises:
        Unavailable: with reason ``daemon_not_running`` when the file is
            absent — the daemon writes it on startup, so absence means
            there is no daemon to talk to.
    """
    path = settings().control_path
    try:
        discovery = easynet_sdk.read_control_discovery(path)
    except easynet_sdk.SDKError as exc:
        raise _control_discovery_error(path, exc) from exc
    return _control_discovery_dict(discovery)


def read_credentials() -> dict[str, Any]:
    """Load the pairing-issued identity file.

    Raises:
        Unavailable: with reason ``not_paired`` when the file is absent —
            identity only exists after a one-time `easynet pair`.
    """
    return _read_json(
        settings().credentials_path,
        reason="not_paired",
        hint="no EasyNet identity on this machine — pair it once with `easynet pair`",
    )


def _read_json(path: Path, *, reason: str, hint: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Unavailable(f"{hint} (looked at {path})", reason=reason) from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Unavailable(
            f"{path} is not valid JSON ({exc}) — re-run `easynet start`/`easynet pair`",
            reason=f"{reason}_corrupt",
        ) from exc
    if not isinstance(data, dict):
        raise Unavailable(
            f"{path} must contain a JSON object, found {type(data).__name__}",
            reason=f"{reason}_corrupt",
        )
    return data


def _control_discovery_dict(discovery: easynet_sdk.ControlDiscovery) -> dict[str, Any]:
    return {
        "socket_path": discovery.socket_path,
        "pipe_name": discovery.pipe_name,
        "invocation_endpoint": discovery.invocation_endpoint,
        "pid": discovery.pid,
        "daemon_version": discovery.daemon_version,
        "supported_ipc_versions": {
            "min": discovery.supported_ipc_versions.min,
            "max": discovery.supported_ipc_versions.max,
        },
        "capability_flags": list(discovery.capability_flags),
        "pages_port": discovery.pages_port,
    }


def _control_discovery_error(path: Path, error: easynet_sdk.SDKError) -> Unavailable:
    if error.code == easynet_sdk.ErrorCode.DAEMON_OFFLINE:
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
