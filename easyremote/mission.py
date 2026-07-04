"""Mission/EAL execution facade over daemon system abilities.

This module is deliberately small: it submits already-compiled EAL to
``mission.run`` and wraps ``mission.track`` / ``mission.cancel``. The
daemon remains the only Mission/EAL runtime; Python owns no planner,
scheduler, retry engine, or receipt policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import easynet_sdk

from .errors import InternalError, InvalidArgument, RemoteError, Unavailable

if TYPE_CHECKING:
    from .client import Client

__all__ = ["MissionControl", "MissionRun"]


class MissionControl:
    """Thin facade for daemon-owned Mission/EAL system abilities."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()
        self._mission = easynet_sdk.EasyRemoteMissionAdapter.from_easyremote_client(
            self._client
        )

    def run_eal(self, source: str, *, label: str | None = None) -> MissionRun:
        """Submit an EAL source string to daemon ``mission.run``."""
        try:
            response = self._mission.run_eal(source, label=label)
        except easynet_sdk.SDKError as exc:
            raise _easyremote_mission_error(exc) from exc
        return MissionRun(self, response.raw)

    def run_file(
        self,
        path: str | Path,
        *,
        label: str | None = None,
        encoding: str = "utf-8",
    ) -> MissionRun:
        """Submit EAL source loaded from a local file."""
        eal_path = Path(path)
        try:
            source = eal_path.read_text(encoding=encoding)
        except OSError as exc:
            raise InvalidArgument(
                f"cannot read EAL file {eal_path}: {exc}",
                reason="eal_file_unreadable",
            ) from exc
        return self.run_eal(source, label=label or eal_path.stem)

    def track(self, run_id: str) -> dict[str, Any]:
        """Fetch daemon status for one mission run."""
        try:
            return dict(self._mission.track(run_id))
        except easynet_sdk.SDKError as exc:
            raise _easyremote_mission_error(exc) from exc

    def cancel(self, run_id: str) -> dict[str, Any]:
        """Request daemon cancellation for one mission run."""
        try:
            return dict(self._mission.cancel(run_id))
        except easynet_sdk.SDKError as exc:
            raise _easyremote_mission_error(exc) from exc


class MissionRun:
    """Handle for a submitted mission run."""

    def __init__(self, control: MissionControl, response: Mapping[str, Any]) -> None:
        self._control = control
        self._response = dict(response)

    @property
    def run_id(self) -> str:
        return str(self._response.get("run_id", ""))

    @property
    def run_dir(self) -> str:
        return str(self._response.get("run_dir", ""))

    @property
    def outputs(self) -> dict[str, Any]:
        return dict(self._response.get("outputs") or {})

    @property
    def raw(self) -> dict[str, Any]:
        return self._response

    def track(self) -> dict[str, Any]:
        return self._control.track(self.run_id)

    @property
    def status(self) -> dict[str, Any]:
        return self.track()

    def cancel(self) -> dict[str, Any]:
        return self._control.cancel(self.run_id)


def _easyremote_mission_error(error: easynet_sdk.SDKError) -> RemoteError:
    if isinstance(error.cause, RemoteError):
        return error.cause
    message = error.message or str(error)
    if error.code == easynet_sdk.ErrorCode.INVALID_ARGUMENT:
        reason = _mission_invalid_reason(message)
        return InvalidArgument(message, reason=reason)
    if error.code in {
        easynet_sdk.ErrorCode.ABILITY_NOT_FOUND,
        easynet_sdk.ErrorCode.NOT_FOUND,
        easynet_sdk.ErrorCode.DAEMON_OFFLINE,
        easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE,
    }:
        return Unavailable(message, reason="sdk_mission_unavailable")
    if error.retryable:
        return Unavailable(message, reason="sdk_mission_retryable")
    return InternalError(message, reason="sdk_mission_internal")


def _mission_invalid_reason(message: str) -> str:
    if "EAL source" in message:
        return "empty_eal_source" if "empty" in message else "invalid_eal_source"
    if "label" in message:
        return "empty_label"
    if "run_id" in message:
        return "empty_run_id"
    return "sdk_mission_invalid_argument"


def _new_client() -> Client:
    from .client import Client

    return Client()
