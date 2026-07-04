"""EasyRemote product adapters over EasyNet-Cli SDK profile clients.

The SDK must not import or understand EasyRemote's ``Client``. This module keeps
that dependency direction clean: EasyRemote adapts its product-level invocation
client into SDK Admin/Mission profile transports, then lets SDK profile DTOs
validate the projections.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import easynet_sdk

from .invocation import fresh_nonce

_ADMIN_PROFILE = "admin_gateway"
_MISSION_PROFILE = "mission"
_DESCRIPTOR_VERSION = "1.0.0"
_AGENT_START = easynet_sdk.AdminSystemAbility.AGENT_START
_AGENT_LIST = easynet_sdk.AdminSystemAbility.AGENT_LIST
_AGENT_REFRESH = easynet_sdk.AdminSystemAbility.AGENT_REFRESH
_MISSION_RUN = easynet_sdk.MissionSystemAbility.RUN
_MISSION_TRACK = easynet_sdk.MissionSystemAbility.TRACK
_MISSION_CANCEL = easynet_sdk.MissionSystemAbility.CANCEL


def admin_facade(client: object) -> EasyRemoteAdminFacade:
    return EasyRemoteAdminFacade(client)


def mission_facade(client: object) -> EasyRemoteMissionFacade:
    return EasyRemoteMissionFacade(client)


class EasyRemoteAdminFacade:
    """EasyRemote-facing agent facade backed by SDK Admin profile clients."""

    def __init__(self, client: object) -> None:
        self._client = client

    def start_agent(
        self,
        name: str,
        *,
        kind: str,
        model: str | None = None,
        label: str | None = None,
        command: str | None = None,
        args: Sequence[str] = (),
    ) -> easynet_sdk.EasyRemoteAgentStartProjection:
        return self._adapter().start_agent(
            name,
            kind=kind,
            model=model,
            label=label,
            command=command,
            args=args,
        )

    def list_agents(self) -> tuple[easynet_sdk.EasyRemoteAgentRecord, ...]:
        return self._adapter().list_agents()

    def refresh_agents(self, name: str | None = None) -> Mapping[str, object]:
        return self._adapter().refresh_agents(name)

    def _adapter(self) -> easynet_sdk.EasyRemoteAdminAdapter:
        return easynet_sdk.EasyRemoteAdminAdapter(
            easynet_sdk.AdminClient(_EasyRemoteAdminTransport(self._client)),
            _admin_base(self._client),
        )


class EasyRemoteMissionFacade:
    """EasyRemote-facing mission facade backed by SDK Mission profile clients."""

    def __init__(self, client: object) -> None:
        self._client = client

    def run_eal(
        self, source: str, *, label: str | None = None
    ) -> EasyRemoteMissionRunProjection:
        projected = self._adapter().run_eal(source, label=label)
        raw = _raw_result(projected.raw)
        return EasyRemoteMissionRunProjection(
            run_id=str(raw.get("run_id") or raw.get("mission_id") or projected.run_id),
            run_dir=str(raw.get("run_dir") or projected.run_dir),
            outputs=_mapping_or_empty(raw.get("outputs")) or dict(projected.outputs),
            raw=raw,
        )

    def track(self, run_id: str) -> Mapping[str, object]:
        return _raw_result(self._adapter().track(run_id))

    def cancel(self, run_id: str) -> Mapping[str, object]:
        return _raw_result(self._adapter().cancel(run_id))

    def _adapter(self) -> easynet_sdk.EasyRemoteMissionAdapter:
        return easynet_sdk.EasyRemoteMissionAdapter(
            easynet_sdk.MissionClient(_EasyRemoteMissionTransport(self._client)),
            _mission_base(self._client),
        )


@dataclass(frozen=True)
class EasyRemoteMissionRunProjection:
    run_id: str
    run_dir: str
    outputs: Mapping[str, object]
    raw: Mapping[str, object]


class _EasyRemoteAdminTransport:
    def __init__(self, client: object) -> None:
        self._client = client

    def list_agents(self, request_json: bytes) -> bytes:
        _json_object(request_json, "EasyRemote agent list request")
        response = self._invoke(_AGENT_LIST)
        agents = response.get("agents") or []
        if not isinstance(agents, list):
            raise _invalid_admin("agent.list response field 'agents' must be an array")
        return _json_bytes(
            {
                "profile": _ADMIN_PROFILE,
                "kind": "agent_records",
                "state": "ok",
                "items": [_agent_record(row) for row in agents],
                "next_cursor": None,
                "metadata": {
                    "profile": _ADMIN_PROFILE,
                    "source": _AGENT_LIST.value,
                    "count": len(agents),
                    "raw_result": dict(response),
                },
            }
        )

    def agent_start(self, request_json: bytes) -> bytes:
        request = _json_object(request_json, "EasyRemote agent start request")
        response = self._invoke(
            _AGENT_START,
            name=_required_string(request, "name"),
            agent_type=_required_string(request, "agent_type"),
            model=request.get("model"),
            model_present=request.get("model_present", True),
            label=request.get("label"),
            command=request.get("command"),
            command_args=list(
                _string_array(request.get("command_args", []), "command_args")
            ),
            materialize_directory=request.get("materialize_directory", True),
            update_existing_spec=request.get("update_existing_spec", False),
            project_workspace=request.get("project_workspace", True),
        )
        return _admin_result_json(_AGENT_START, response)

    def agent_refresh(self, request_json: bytes) -> bytes:
        request = _json_object(request_json, "EasyRemote agent refresh request")
        payload: dict[str, object] = {}
        if request.get("name"):
            payload["name"] = _required_string(request, "name")
        response = self._invoke(_AGENT_REFRESH, **payload)
        return _admin_result_json(_AGENT_REFRESH, response)

    def close(self) -> None:
        return None

    def _invoke(
        self, ability: easynet_sdk.AdminSystemAbility, **kwargs: object
    ) -> dict[str, object]:
        invocation = _call_method(self._client, "invoke", ability.value, **kwargs)
        return _mapping(_call_method(invocation, "result"), "admin response")


class _EasyRemoteMissionTransport:
    def __init__(self, client: object) -> None:
        self._client = client

    def run_eal(self, request_json: bytes) -> bytes:
        request = _json_object(request_json, "EasyRemote mission run request")
        payload: dict[str, object] = {"source": _required_string(request, "source")}
        if request.get("label"):
            payload["label"] = _required_string(request, "label")
        response = self._invoke(_MISSION_RUN, **payload)
        return _mission_status_json(_MISSION_RUN, response)

    def track(self, request_json: bytes) -> bytes:
        request = _json_object(request_json, "EasyRemote mission track request")
        run_id = _required_string(request, "mission_id")
        response = self._invoke(_MISSION_TRACK, run_id=run_id)
        return _mission_status_json(_MISSION_TRACK, response, mission_id=run_id)

    def cancel(self, request_json: bytes) -> bytes:
        request = _json_object(request_json, "EasyRemote mission cancel request")
        run_id = _required_string(request, "mission_id")
        response = self._invoke(_MISSION_CANCEL, run_id=run_id)
        return _mission_status_json(_MISSION_CANCEL, response, mission_id=run_id)

    def close(self) -> None:
        return None

    def _invoke(
        self, ability: easynet_sdk.MissionSystemAbility, **kwargs: object
    ) -> dict[str, object]:
        invocation = _call_method(self._client, "invoke", ability.value, **kwargs)
        return _mapping(_call_method(invocation, "result"), "mission response")


def _admin_base(client: object) -> easynet_sdk.AdminCarrierBase:
    device = _device_ura(client)
    return easynet_sdk.AdminCarrierBase(
        caller_ura=device,
        callee_ura=device,
        subject_ura=device,
        descriptor_version=_DESCRIPTOR_VERSION,
        nonce_base64=_fresh_nonce_base64(),
        causal_context={"form": "none"},
        metadata={"profile": _ADMIN_PROFILE, "source": "easyremote"},
    )


def _mission_base(client: object) -> easynet_sdk.MissionCarrierBase:
    device = _device_ura(client)
    return easynet_sdk.MissionCarrierBase(
        caller_ura=device,
        callee_ura=device,
        subject_ura=device,
        descriptor_version=_DESCRIPTOR_VERSION,
        nonce_base64=_fresh_nonce_base64(),
        causal_context={"form": "none"},
        metadata={"profile": _MISSION_PROFILE, "source": "easyremote"},
    )


def _device_ura(client: object) -> str:
    identity = _call_method(client, "_who")
    candidate = getattr(identity, "device_ura", None)
    if not isinstance(candidate, str) or not candidate.strip():
        raise _invalid_admin("EasyRemote client identity field 'device_ura' is required")
    return candidate


def _fresh_nonce_base64() -> str:
    return base64.b64encode(fresh_nonce()).decode("ascii")


def _admin_result_json(
    operation: easynet_sdk.AdminSystemAbility, response: Mapping[str, object]
) -> bytes:
    return _json_bytes(
        {
            "profile": _ADMIN_PROFILE,
            "kind": "agent_lifecycle_result",
            "operation": operation.value,
            "state": str(response.get("state") or "ok"),
            "agent_ura": _optional_string(response.get("agent_ura"), "agent_ura"),
            "ack": _optional_bool(response.get("ack"), "ack"),
            "runtime_not_ready": bool(response.get("runtime_not_ready", False)),
            "runtime_catalog_not_ready": bool(
                response.get("runtime_catalog_not_ready", False)
            ),
            "metadata": {
                "profile": _ADMIN_PROFILE,
                "source": operation.value,
                "raw_result": dict(response),
            },
        }
    )


def _agent_record(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _invalid_admin("agent.list item must be an object")
    raw = dict(value)
    name = raw.get("name")
    runtime = raw.get("runtime") or raw.get("kind")
    if not isinstance(name, str) or not name.strip():
        raise _invalid_admin("agent.list item field 'name' is required")
    if not isinstance(runtime, str) or not runtime.strip():
        raise _invalid_admin("agent.list item field 'runtime' is required")
    metadata = _mapping_or_empty(raw.get("metadata"))
    for key in ("root_path", "root_exists", "timeout_secs"):
        if key in raw and key not in metadata:
            metadata[key] = raw[key]
    metadata.setdefault("profile", _ADMIN_PROFILE)
    metadata.setdefault("source", _AGENT_LIST.value)
    return {
        "name": name,
        "agent_ura": raw.get("agent_ura"),
        "owner_ura": raw.get("owner_ura"),
        "device_ura": raw.get("device_ura"),
        "state": raw.get("state") if isinstance(raw.get("state"), str) else "registered",
        "runtime": runtime,
        "model": raw.get("model"),
        "label": raw.get("label"),
        "abilities": raw.get("abilities") if isinstance(raw.get("abilities"), list) else [],
        "metadata": metadata,
    }


def _mission_status_json(
    source: easynet_sdk.MissionSystemAbility,
    response: Mapping[str, object],
    *,
    mission_id: str | None = None,
) -> bytes:
    raw = dict(response)
    metadata: dict[str, object] = {
        "profile": _MISSION_PROFILE,
                "source": source.value,
        "raw_result": raw,
    }
    run_dir = raw.get("run_dir")
    outputs = raw.get("outputs")
    if isinstance(run_dir, str):
        metadata["run_dir"] = run_dir
    if isinstance(outputs, Mapping):
        metadata["outputs"] = dict(outputs)
    return _json_bytes(
        {
            "profile": _MISSION_PROFILE,
            "kind": "mission_status",
            "mission_id": _mission_id(source, raw, mission_id),
            "state": _mission_state(source, raw),
            "terminal": _mission_terminal(source, raw),
            "partial_failures": _partial_failures(raw),
            "cancelled": _cancelled(raw),
            "parent_invocation_id": _optional_string(
                raw.get("parent_invocation_id"), "parent_invocation_id"
            ),
            "parent_receipt_ura": _optional_string(
                raw.get("parent_receipt_ura"), "parent_receipt_ura"
            ),
            "parent_invocation": _optional_mapping(
                raw.get("parent_invocation"), "parent_invocation"
            ),
            "child_invocations": [],
            "child_receipts": [],
            "output_refs": _output_refs(raw),
            "metadata": metadata,
        }
    )


def _mission_id(
    source: easynet_sdk.MissionSystemAbility,
    raw: Mapping[str, object],
    mission_id: str | None,
) -> str:
    if mission_id:
        return mission_id
    for field_name in ("mission_id", "run_id"):
        value = raw.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    raise _invalid_mission(f"{source.value} response is missing mission run_id")


def _mission_state(
    source: easynet_sdk.MissionSystemAbility, raw: Mapping[str, object]
) -> str:
    value = raw.get("state")
    if isinstance(value, str) and value.strip():
        return value
    if _cancelled(raw):
        return "cancelled"
    if source is _MISSION_RUN:
        return "running"
    return "ok"


def _mission_terminal(
    source: easynet_sdk.MissionSystemAbility, raw: Mapping[str, object]
) -> bool:
    value = raw.get("terminal")
    if isinstance(value, bool):
        return value
    if _cancelled(raw):
        return True
    state = raw.get("state")
    if isinstance(state, str) and state.lower() in {
        "completed",
        "failed",
        "cancelled",
        "canceled",
    }:
        return True
    return source is _MISSION_CANCEL and bool(raw.get("ok", True))


def _cancelled(raw: Mapping[str, object]) -> bool:
    value = raw.get("cancelled")
    return value if isinstance(value, bool) else False


def _partial_failures(raw: Mapping[str, object]) -> int:
    value = raw.get("partial_failures")
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _invalid_mission("partial_failures must be a non-negative integer")
    return value


def _output_refs(raw: Mapping[str, object]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    run_dir = raw.get("run_dir")
    if isinstance(run_dir, str) and run_dir:
        refs.append({"kind": "run_dir", "path": run_dir, "metadata": {}})
    output_refs = raw.get("output_refs")
    if isinstance(output_refs, list):
        for item in output_refs:
            if not isinstance(item, Mapping):
                raise _invalid_mission("output_refs items must be objects")
            refs.append(
                {
                    "kind": _required_string(item, "kind"),
                    "path": _optional_string(item.get("path"), "path") or "",
                    "metadata": _optional_mapping(item.get("metadata"), "metadata")
                    or {},
                }
            )
    return refs


def _raw_result(value: Mapping[str, object]) -> dict[str, object]:
    metadata = value.get("metadata")
    if isinstance(metadata, Mapping):
        raw = metadata.get("raw_result")
        if isinstance(raw, Mapping):
            return dict(raw)
    return dict(value)


def _json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_admin(f"{label} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise _invalid_admin(f"{label} must be a JSON object")
    return dict(decoded)


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _call_method(
    target: object, method_name: str, *args: object, **kwargs: object
) -> object:
    method = getattr(target, method_name, None)
    if not callable(method):
        raise _invalid_admin(f"EasyRemote client does not expose {method_name}()")
    try:
        return method(*args, **kwargs)
    except easynet_sdk.SDKError:
        raise
    except Exception as exc:
        raise easynet_sdk.SDKError(
            code=easynet_sdk.ErrorCode.TRANSPORT,
            stage="easyremote_profile",
            retry=easynet_sdk.RetryHint.SAME_HANDLE,
            retryable=True,
            message=f"EasyRemote client {method_name}() failed: {exc}",
            cause=exc,
        ) from exc


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _invalid_admin(f"{field_name} must be an object")
    return dict(value)


def _mapping_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required_string(value: Mapping[str, object], field_name: str) -> str:
    raw = value.get(field_name)
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid_admin(f"{field_name} is required")
    return raw


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid_admin(f"{field_name} must be a string")
    return value


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _invalid_admin(f"{field_name} must be a boolean")
    return value


def _optional_mapping(value: object, field_name: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid_admin(f"{field_name} must be an object")
    return dict(value)


def _string_array(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _invalid_admin(f"{field_name} must be an array of strings")
    return tuple(value)


def _invalid_admin(message: str) -> easynet_sdk.SDKError:
    return easynet_sdk.SDKError(
        code=easynet_sdk.ErrorCode.INVALID_ARGUMENT,
        stage="easyremote_admin_profile",
        retry=easynet_sdk.RetryHint.NEVER,
        retryable=False,
        message=message,
    )


def _invalid_mission(message: str) -> easynet_sdk.SDKError:
    return easynet_sdk.SDKError(
        code=easynet_sdk.ErrorCode.INVALID_ARGUMENT,
        stage="easyremote_mission_profile",
        retry=easynet_sdk.RetryHint.NEVER,
        retryable=False,
        message=message,
    )
