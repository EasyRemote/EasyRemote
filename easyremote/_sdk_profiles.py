"""EasyRemote product dispatchers for SDK-owned profile bridges."""

from __future__ import annotations

from collections.abc import Mapping

import easynet_sdk


def admin_facade(client: object) -> easynet_sdk.AgentLifecycleAdapter:
    return _bridge(client).admin_facade()


def mission_facade(client: object) -> EasyRemoteMissionFacade:
    return EasyRemoteMissionFacade(_bridge(client).mission_facade())


class EasyRemoteMissionFacade:
    """EasyRemote API compatibility wrapper over the SDK Mission adapter."""

    def __init__(self, adapter: easynet_sdk.MissionExecutionAdapter) -> None:
        self._adapter = adapter

    def run_eal(
        self, source: str, *, label: str | None = None
    ) -> easynet_sdk.MissionRunProjection:
        projected = self._adapter.run_eal(source, label=label)
        raw = _raw_result(projected.raw)
        return easynet_sdk.MissionRunProjection(
            run_id=str(raw.get("run_id") or raw.get("mission_id") or projected.run_id),
            run_dir=str(raw.get("run_dir") or projected.run_dir),
            outputs=_mapping_or_empty(raw.get("outputs")) or dict(projected.outputs),
            raw=raw,
        )

    def track(self, run_id: str) -> Mapping[str, object]:
        return _raw_result(self._adapter.track(run_id))

    def cancel(self, run_id: str) -> Mapping[str, object]:
        return _raw_result(self._adapter.cancel(run_id))

    def events(
        self,
        run_id: str,
        *,
        cursor_sequence: int = 0,
        limit: int = 0,
    ) -> Mapping[str, object]:
        return self._adapter.events(
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
    ) -> easynet_sdk.MissionEventProjectionTailer:
        return self._adapter.tail_events(
            run_id,
            cursor_sequence=cursor_sequence,
            limit=limit,
            max_empty_pages=max_empty_pages,
            poll_interval_seconds=poll_interval_seconds,
        )


def _bridge(client: object) -> easynet_sdk.DaemonProfileBridge:
    return easynet_sdk.DaemonProfileBridge(_EasyRemoteProfileDispatcher(client))


class _EasyRemoteProfileDispatcher:
    """Minimal EasyRemote adapter required by the SDK profile bridge."""

    def __init__(self, client: object) -> None:
        self._client = client

    def device_ura(self) -> str:
        identity = _call_method(self._client, "_who")
        candidate = getattr(identity, "device_ura", None)
        if not isinstance(candidate, str) or not candidate.strip():
            raise easynet_sdk.SDKError(
                code=easynet_sdk.ErrorCode.INVALID_ARGUMENT,
                stage="easyremote_profile",
                retry=easynet_sdk.RetryHint.NEVER,
                retryable=False,
                message="EasyRemote client identity field 'device_ura' is required",
            )
        return candidate

    def invoke_system_ability(
        self, ability: str, **kwargs: object
    ) -> Mapping[str, object]:
        invocation = _call_method(self._client, "invoke", ability, **kwargs)
        result = _call_method(invocation, "result")
        if not isinstance(result, Mapping):
            raise easynet_sdk.SDKError(
                code=easynet_sdk.ErrorCode.TRANSPORT,
                stage="easyremote_profile",
                retry=easynet_sdk.RetryHint.SAFE,
                retryable=True,
                message="EasyRemote system ability result must be an object",
            )
        return dict(result)


def _call_method(
    target: object, method_name: str, *args: object, **kwargs: object
) -> object:
    method = getattr(target, method_name, None)
    if not callable(method):
        raise easynet_sdk.SDKError(
            code=easynet_sdk.ErrorCode.INVALID_ARGUMENT,
            stage="easyremote_profile",
            retry=easynet_sdk.RetryHint.NEVER,
            retryable=False,
            message=f"EasyRemote client does not expose {method_name}()",
        )
    try:
        return method(*args, **kwargs)
    except easynet_sdk.SDKError:
        raise
    except Exception as exc:
        raise easynet_sdk.SDKError(
            code=easynet_sdk.ErrorCode.TRANSPORT,
            stage="easyremote_profile",
            retry=easynet_sdk.RetryHint.SAFE,
            retryable=True,
            message=f"EasyRemote client {method_name}() failed: {exc}",
            cause=exc,
        ) from exc


def _raw_result(value: Mapping[str, object]) -> dict[str, object]:
    metadata = value.get("metadata")
    if isinstance(metadata, Mapping):
        raw = metadata.get("raw_result")
        if isinstance(raw, Mapping):
            return dict(raw)
    return dict(value)


def _mapping_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}
