"""EasyRemote-owned Mission/EAL execution and projection model.

EasyRemote owns the product-facing Mission API and its read models. The daemon
remains the only EAL planner/executor: this module submits ordinary generic
Invocations through Client.invoke and never implements scheduling, retries, or
receipt policy.
"""

from __future__ import annotations

import json
import math
import time
from collections import deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import easynet_sdk

from ._product_abilities import MissionAbility, SystemAgentId
from .errors import (
    InternalError,
    InvalidArgument,
    RemoteError,
    Unavailable,
    error_from_sdk,
)
from .invocation_policy import runtime_root_context

if TYPE_CHECKING:
    from .client import Client
    from .identity import LocalIdentity

__all__ = [
    "MissionChildInvocation",
    "MissionControl",
    "MissionEventTailer",
    "MissionExecutionAdapter",
    "MissionRun",
    "MissionRunProjection",
    "MissionStatus",
]


class _MissionTransport(Protocol):
    def invoke_runtime_ability(
        self,
        call: easynet_sdk.RuntimeCallContext,
        ability_name: str,
        arguments: object,
    ) -> object: ...


class _MissionClient(Protocol):
    def _who(self) -> LocalIdentity: ...

    def _connected(self) -> _MissionTransport: ...


@dataclass(frozen=True)
class MissionChildInvocation:
    """One daemon-observed child Invocation fact."""

    step_id: str
    request_id: str
    trace_id: str
    ability: str
    invocation_ura: str
    caller_ura: str
    callee_ura: str
    subject_ura: str
    metadata_state: str
    ledger_state: object
    receipt: Mapping[str, object] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> MissionChildInvocation:
        receipt = _optional_mapping(value.get("receipt"), "receipt")
        if receipt is not None:
            _validate_receipt_anchor(receipt)
        ledger_state = value.get("ledger_state")
        if ledger_state is None:
            raise _invalid_status("ledger_state is required")
        return cls(
            step_id=_required_text(value, "step_id"),
            request_id=_required_text(value, "request_id"),
            trace_id=_required_text(value, "trace_id"),
            ability=_required_text(value, "ability"),
            invocation_ura=_required_text(value, "invocation_ura"),
            caller_ura=_required_text(value, "caller_ura"),
            callee_ura=_required_text(value, "callee_ura"),
            subject_ura=_required_text(value, "subject_ura"),
            metadata_state=_required_text(value, "metadata_state"),
            ledger_state=ledger_state,
            receipt=receipt,
        )


@dataclass(frozen=True)
class MissionStatus:
    """Mission status fields consumed by Pipeline conformance.

    ``raw`` retains the daemon projection without duplicating every product
    schema field as another EasyRemote DTO.
    """

    mission_id: str
    state: str
    terminal: bool
    child_invocations: tuple[MissionChildInvocation, ...]
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(
        cls,
        raw: bytes | str | Mapping[str, object],
    ) -> MissionStatus:
        decoded = _json_mapping(raw, "mission status")
        if (
            decoded.get("profile") != "mission"
            or decoded.get("kind") != "mission_status"
        ):
            raise _invalid_status("invalid mission status projection")
        child_invocations = tuple(
            MissionChildInvocation.from_mapping(value)
            for value in _mapping_sequence(decoded, "child_invocations")
        )
        step_ids = [child.step_id for child in child_invocations]
        if len(step_ids) != len(set(step_ids)):
            raise _invalid_status("child_invocations contains duplicate step_id facts")
        return cls(
            mission_id=_required_text(decoded, "mission_id"),
            state=_required_text(decoded, "state"),
            terminal=_required_bool(decoded, "terminal"),
            child_invocations=child_invocations,
            raw=decoded,
        )


@dataclass(frozen=True)
class MissionRunProjection:
    """Stable EasyRemote view of a mission.run result."""

    run_id: str
    run_dir: str
    outputs: Mapping[str, object]
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> MissionRunProjection:
        run_id_value = value.get("run_id") or value.get("mission_id")
        if not isinstance(run_id_value, str) or not run_id_value.strip():
            raise _invalid_response("mission.run result is missing run_id")
        run_dir_value = value.get("run_dir")
        if run_dir_value is None:
            run_dir = ""
        elif isinstance(run_dir_value, str):
            run_dir = run_dir_value
        else:
            raise _invalid_response("mission.run run_dir must be a string")
        outputs_value = value.get("outputs")
        if outputs_value is None:
            outputs: Mapping[str, object] = {}
        elif isinstance(outputs_value, Mapping):
            outputs = dict(outputs_value)
        else:
            raise _invalid_response("mission.run outputs must be an object")
        return cls(
            run_id=run_id_value.strip(),
            run_dir=run_dir,
            outputs=outputs,
            raw=dict(value),
        )


class MissionExecutionAdapter:
    """Product execution adapter over generic EasyRemote Invocation."""

    def __init__(self, client: _MissionClient) -> None:
        self._client = client

    def run_eal(
        self,
        source: str,
        *,
        label: str | None = None,
    ) -> MissionRunProjection:
        source_text = _validated_source(source)
        mission_label = _validated_optional_text(label, "mission label", "empty_label")
        args: dict[str, object] = {"source": source_text}
        if mission_label is not None:
            args["label"] = mission_label
        return MissionRunProjection.from_mapping(self._invoke(MissionAbility.RUN, args))

    def track(self, run_id: str) -> dict[str, object]:
        return self._invoke(
            MissionAbility.TRACK,
            {"run_id": _validated_run_id(run_id)},
        )

    def cancel(self, run_id: str) -> dict[str, object]:
        return self._invoke(
            MissionAbility.CANCEL,
            {"run_id": _validated_run_id(run_id)},
        )

    def events(
        self,
        run_id: str,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
    ) -> dict[str, object]:
        cursor = _bounded_int(cursor_sequence, "cursor_sequence")
        page_limit = _bounded_int(limit, "limit", maximum=1000)
        args: dict[str, object] = {
            "run_id": _validated_run_id(run_id),
            "cursor_sequence": cursor,
        }
        if page_limit:
            args["limit"] = page_limit
        return self._invoke(MissionAbility.EVENTS, args)

    def tail_events(
        self,
        run_id: str,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
        max_empty_pages: int = 0,
        poll_interval_seconds: float = 0.0,
    ) -> MissionEventTailer:
        return MissionEventTailer(
            self,
            _validated_run_id(run_id),
            cursor_sequence=_bounded_int(cursor_sequence, "cursor_sequence"),
            limit=_bounded_int(limit, "limit", maximum=1000),
            max_empty_pages=_bounded_int(max_empty_pages, "max_empty_pages"),
            poll_interval_seconds=_bounded_float(
                poll_interval_seconds,
                "poll_interval_seconds",
            ),
        )

    def _invoke(
        self,
        ability: MissionAbility,
        args: Mapping[str, object],
    ) -> dict[str, object]:
        try:
            identity = self._client._who()
            callee_ura = identity.system_agent_ura(str(SystemAgentId.AUTOMATION))
            result = self._client._connected().invoke_runtime_ability(
                runtime_root_context(
                    caller_ura=identity.user_ura,
                    callee_ura=callee_ura,
                    subject_ura=easynet_sdk.owner_ability_ura(
                        callee_ura,
                        str(ability),
                    ),
                ),
                str(ability),
                dict(args),
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        except RemoteError:
            raise
        except Exception as exc:
            raise Unavailable(
                f"{ability} invocation failed: {exc}",
                reason="mission_invocation_failed",
            ) from exc
        if not isinstance(result, Mapping):
            raise _invalid_response(f"{ability} result must be an object")
        return dict(result)


@dataclass(frozen=True)
class _MissionEventPage:
    cursor_sequence: int
    next_cursor_sequence: int
    has_more: bool
    dropped_count: int
    events: tuple[dict[str, object], ...]


class MissionEventTailer(Iterator[Mapping[str, object]]):
    """Bounded event-page state machine owned by EasyRemote."""

    def __init__(
        self,
        adapter: MissionExecutionAdapter,
        run_id: str,
        *,
        cursor_sequence: int,
        limit: int,
        max_empty_pages: int,
        poll_interval_seconds: float,
    ) -> None:
        self._adapter = adapter
        self._run_id = run_id
        self._cursor_sequence = cursor_sequence
        self._limit = limit
        self._max_empty_pages = max_empty_pages
        self._poll_interval_seconds = poll_interval_seconds
        self._buffer: deque[dict[str, object]] = deque()
        self._empty_pages = 0
        self._closed = False
        self._terminal_seen = False

    @property
    def cursor_sequence(self) -> int:
        return self._cursor_sequence

    def close(self) -> None:
        self._closed = True

    def __iter__(self) -> MissionEventTailer:
        return self

    def __next__(self) -> Mapping[str, object]:
        if not self._buffer:
            self._fill_buffer()
        if not self._buffer:
            raise StopIteration
        event = self._buffer.popleft()
        if event["terminal"] is True:
            self.close()
        return event

    def __enter__(self) -> MissionEventTailer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _fill_buffer(self) -> None:
        while not self._closed and not self._terminal_seen:
            previous_cursor = self._cursor_sequence
            try:
                page = _event_page(
                    self._adapter.events(
                        self._run_id,
                        cursor_sequence=previous_cursor,
                        limit=self._limit,
                    )
                )
            except RemoteError:
                self.close()
                raise
            if page.cursor_sequence != previous_cursor:
                self.close()
                raise _invalid_response(
                    "mission event page cursor does not match the requested cursor"
                )
            if page.dropped_count:
                self.close()
                raise Unavailable(
                    "mission event tail dropped daemon events",
                    reason="mission_events_dropped",
                )
            if (
                page.events or page.has_more
            ) and page.next_cursor_sequence <= previous_cursor:
                self.close()
                raise InternalError(
                    "mission event tail made no cursor progress",
                    reason="mission_event_cursor_stalled",
                )
            self._cursor_sequence = page.next_cursor_sequence
            for event in page.events:
                self._buffer.append(event)
                if event["terminal"] is True:
                    self._terminal_seen = True
                    break
            if self._buffer:
                return
            if page.has_more:
                continue
            self._empty_pages += 1
            if self._empty_pages > self._max_empty_pages:
                self.close()
                return
            if self._poll_interval_seconds:
                time.sleep(self._poll_interval_seconds)


class MissionControl:
    """Public Mission facade backed by EasyRemote product semantics."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()
        self._execution = MissionExecutionAdapter(self._client)

    def run_eal(self, source: str, *, label: str | None = None) -> MissionRun:
        return MissionRun(self, self._execution.run_eal(source, label=label))

    def run_file(
        self,
        path: str | Path,
        *,
        label: str | None = None,
        encoding: str = "utf-8",
    ) -> MissionRun:
        eal_path = Path(path)
        try:
            source = eal_path.read_text(encoding=encoding)
        except OSError as exc:
            raise InvalidArgument(
                f"cannot read EAL file {eal_path}: {exc}",
                reason="eal_file_unreadable",
            ) from exc
        return self.run_eal(source, label=label or eal_path.stem)

    def track(self, run_id: str) -> dict[str, object]:
        return self._execution.track(run_id)

    def cancel(self, run_id: str) -> dict[str, object]:
        return self._execution.cancel(run_id)

    def events(
        self,
        run_id: str,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
    ) -> dict[str, object]:
        return self._execution.events(
            run_id,
            cursor_sequence=cursor_sequence,
            limit=limit,
        )

    def tail_events(
        self,
        run_id: str,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
        max_empty_pages: int = 0,
        poll_interval_seconds: float = 0.0,
    ) -> MissionEventTailer:
        return self._execution.tail_events(
            run_id,
            cursor_sequence=cursor_sequence,
            limit=limit,
            max_empty_pages=max_empty_pages,
            poll_interval_seconds=poll_interval_seconds,
        )


class MissionRun:
    """Handle for one submitted Mission."""

    def __init__(
        self,
        control: MissionControl,
        response: MissionRunProjection | Mapping[str, object],
    ) -> None:
        self._control = control
        self._projection = (
            response
            if isinstance(response, MissionRunProjection)
            else MissionRunProjection.from_mapping(response)
        )

    @property
    def run_id(self) -> str:
        return self._projection.run_id

    @property
    def run_dir(self) -> str:
        return self._projection.run_dir

    @property
    def outputs(self) -> dict[str, object]:
        return dict(self._projection.outputs)

    @property
    def raw(self) -> dict[str, object]:
        return dict(self._projection.raw)

    def track(self) -> dict[str, object]:
        return self._control.track(self.run_id)

    @property
    def status(self) -> dict[str, object]:
        return self.track()

    def cancel(self) -> dict[str, object]:
        return self._control.cancel(self.run_id)

    def events(
        self,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
    ) -> dict[str, object]:
        return self._control.events(
            self.run_id,
            cursor_sequence=cursor_sequence,
            limit=limit,
        )

    def tail_events(
        self,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
        max_empty_pages: int = 0,
        poll_interval_seconds: float = 0.0,
    ) -> MissionEventTailer:
        return self._control.tail_events(
            self.run_id,
            cursor_sequence=cursor_sequence,
            limit=limit,
            max_empty_pages=max_empty_pages,
            poll_interval_seconds=poll_interval_seconds,
        )


def _event_page(value: Mapping[str, object]) -> _MissionEventPage:
    cursor = _required_non_negative_int(value, "cursor_sequence")
    next_cursor = _required_non_negative_int(value, "next_cursor_sequence")
    if next_cursor < cursor:
        raise _invalid_response("next_cursor_sequence must not go backwards")
    raw_events = value.get("events")
    if not isinstance(raw_events, list):
        raise _invalid_response("mission events must be an array")
    events: list[dict[str, object]] = []
    previous_sequence: int | None = None
    for raw_event in raw_events:
        if not isinstance(raw_event, Mapping):
            raise _invalid_response("mission event must be an object")
        event = dict(raw_event)
        sequence = _required_non_negative_int(event, "sequence")
        if previous_sequence is not None and sequence <= previous_sequence:
            raise _invalid_response("mission events must be strictly ordered")
        terminal = event.get("terminal")
        if not isinstance(terminal, bool):
            raise _invalid_response("mission event terminal must be boolean")
        previous_sequence = sequence
        events.append(event)
    return _MissionEventPage(
        cursor_sequence=cursor,
        next_cursor_sequence=next_cursor,
        has_more=_required_bool(value, "has_more"),
        dropped_count=_required_non_negative_int(value, "dropped_count"),
        events=tuple(events),
    )


def _json_mapping(
    raw: bytes | str | Mapping[str, object],
    label: str,
) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        decoded = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_status(f"cannot decode {label}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise _invalid_status(f"{label} must be an object")
    return decoded


def _mapping_sequence(
    value: Mapping[str, object],
    field_name: str,
) -> tuple[Mapping[str, object], ...]:
    raw = value.get(field_name)
    if not isinstance(raw, list):
        raise _invalid_status(f"{field_name} must be an array")
    if not all(isinstance(item, Mapping) for item in raw):
        raise _invalid_status(f"{field_name} must contain objects")
    return tuple(dict(item) for item in raw if isinstance(item, Mapping))


def _optional_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid_status(f"{field_name} must be an object or null")
    return dict(value)


def _validate_receipt_anchor(
    value: Mapping[str, object],
) -> easynet_sdk.ReceiptReference:
    receipt_ura = _required_text(value, "receipt_ura")
    receipt_hash = _required_text(value, "receipt_hash")
    try:
        return easynet_sdk.ReceiptReference.from_runtime_receipt(
            {
                "receipt_ura": receipt_ura,
                "self_hash_hex": receipt_hash,
            }
        )
    except easynet_sdk.SDKError as exc:
        raise _invalid_status(
            f"mission child receipt anchor is invalid: {exc}"
        ) from exc


def _required_text(value: Mapping[str, object], field_name: str) -> str:
    raw = value.get(field_name)
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid_status(f"{field_name} is required")
    return raw


def _required_bool(value: Mapping[str, object], field_name: str) -> bool:
    raw = value.get(field_name)
    if not isinstance(raw, bool):
        raise _invalid_status(f"{field_name} must be boolean")
    return raw


def _required_non_negative_int(
    value: Mapping[str, object],
    field_name: str,
) -> int:
    raw = value.get(field_name)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise _invalid_status(f"{field_name} must be a non-negative integer")
    return raw


def _validated_source(source: str) -> str:
    if not isinstance(source, str):
        raise InvalidArgument(
            f"EAL source must be a string, got {type(source).__name__}",
            reason="invalid_eal_source",
        )
    if not source.strip():
        raise InvalidArgument(
            "EAL source must not be empty",
            reason="empty_eal_source",
        )
    return source


def _validated_run_id(run_id: str) -> str:
    value = _validated_optional_text(run_id, "mission run_id", "empty_run_id") or ""
    if "/" in value or "\\" in value or "://" in value:
        raise InvalidArgument(
            "mission run_id must be an opaque identifier, not a path-like address",
            reason="invalid_run_id",
        )
    return value


def _validated_optional_text(
    value: str | None,
    label: str,
    reason: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidArgument(
            f"{label} must be a string",
            reason=reason,
        )
    trimmed = value.strip()
    if not trimmed:
        raise InvalidArgument(
            f"{label} must not be empty",
            reason=reason,
        )
    return trimmed


def _bounded_int(
    value: int,
    field_name: str,
    *,
    maximum: int | None = None,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidArgument(
            f"{field_name} must be a non-negative integer",
            reason=f"invalid_{field_name}",
        )
    if maximum is not None and value > maximum:
        raise InvalidArgument(
            f"{field_name} exceeds maximum {maximum}",
            reason=f"invalid_{field_name}",
        )
    return value


def _bounded_float(value: float, field_name: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise InvalidArgument(
            f"{field_name} must be a non-negative finite number",
            reason=f"invalid_{field_name}",
        )
    return float(value)


def _invalid_status(message: str) -> InternalError:
    return InternalError(message, reason="invalid_mission_status")


def _invalid_response(message: str) -> InternalError:
    return InternalError(message, reason="invalid_mission_response")


def _new_client() -> Client:
    from .client import Client

    return Client()
