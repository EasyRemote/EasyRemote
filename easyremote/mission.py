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

from .errors import InvalidArgument

if TYPE_CHECKING:
    from .client import Client

__all__ = ["MissionControl", "MissionRun"]


class MissionControl:
    """Thin facade for daemon-owned Mission/EAL system abilities."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()

    def run_eal(self, source: str, *, label: str | None = None) -> MissionRun:
        """Submit an EAL source string to daemon ``mission.run``."""
        source_text = _validated_source(source)
        mission_label = _validated_optional_label(label)
        args: dict[str, Any] = {"source": source_text}
        if mission_label is not None:
            args["label"] = mission_label
        response = self._client.invoke("mission.run", **args).result()
        return MissionRun(self, _dict(response))

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
        response = self._client.invoke("mission.track", run_id=_run_id(run_id)).result()
        return _dict(response)

    def cancel(self, run_id: str) -> dict[str, Any]:
        """Request daemon cancellation for one mission run."""
        response = self._client.invoke(
            "mission.cancel",
            run_id=_run_id(run_id),
        ).result()
        return _dict(response)


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


def _validated_source(source: str) -> str:
    if not isinstance(source, str):
        raise InvalidArgument(
            f"EAL source must be a string, got {type(source).__name__}",
            reason="invalid_eal_source",
        )
    if not source.strip():
        raise InvalidArgument("EAL source must not be empty", reason="empty_eal_source")
    return source


def _validated_optional_label(label: str | None) -> str | None:
    if label is None:
        return None
    trimmed = label.strip()
    if not trimmed:
        raise InvalidArgument("mission label must not be empty", reason="empty_label")
    return trimmed


def _run_id(value: str) -> str:
    run_id = value.strip()
    if not run_id:
        raise InvalidArgument("mission run_id must not be empty", reason="empty_run_id")
    return run_id


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise InvalidArgument(
        f"expected a JSON object, got {type(value).__name__}",
        reason="invalid_mission_response",
    )


def _new_client() -> Client:
    from .client import Client

    return Client()
