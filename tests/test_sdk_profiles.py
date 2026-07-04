"""EasyRemote adapters conform to EasyNet-Cli SDK profile contracts."""

import easynet_sdk
import pytest

from easyremote._sdk_profiles import (
    _EasyRemoteAdminTransport,
    _EasyRemoteMissionTransport,
)


def test_easyremote_profile_transports_satisfy_sdk_protocols() -> None:
    assert isinstance(_EasyRemoteAdminTransport(object()), easynet_sdk.AdminTransport)
    assert isinstance(
        _EasyRemoteMissionTransport(object()), easynet_sdk.MissionTransport
    )


@pytest.mark.parametrize(
    "method_name",
    [
        "build_agent_list_invocation",
        "build_agent_start_invocation",
        "build_agent_stop_invocation",
        "build_agent_refresh_invocation",
        "build_session_list_invocation",
        "gateway_status",
        "agent_stop",
        "list_device_sessions",
        "join_hub",
        "leave_hub",
        "pairing_preflight",
        "validate_pairing",
        "verify_device_credential",
        "create_pairing",
        "revoke_device",
        "create_device_session",
        "delete_device_session",
    ],
)
def test_easyremote_admin_transport_rejects_unsupported_profile_methods(
    method_name: str,
) -> None:
    transport = _EasyRemoteAdminTransport(object())

    with pytest.raises(easynet_sdk.SDKError) as exc_info:
        getattr(transport, method_name)(b"{}")

    error = exc_info.value
    assert error.code is easynet_sdk.ErrorCode.NOT_IMPLEMENTED
    assert error.stage == "easyremote_admin_profile"
    assert error.retry is easynet_sdk.RetryHint.NEVER
    assert error.details["profile_method"] == method_name


@pytest.mark.parametrize(
    "method_name",
    [
        "build_run_eal_invocation",
        "build_run_file_invocation",
        "build_track_invocation",
        "build_cancel_invocation",
        "run_file",
    ],
)
def test_easyremote_mission_transport_rejects_unsupported_profile_methods(
    method_name: str,
) -> None:
    transport = _EasyRemoteMissionTransport(object())

    with pytest.raises(easynet_sdk.SDKError) as exc_info:
        getattr(transport, method_name)(b"{}")

    error = exc_info.value
    assert error.code is easynet_sdk.ErrorCode.NOT_IMPLEMENTED
    assert error.stage == "easyremote_mission_profile"
    assert error.retry is easynet_sdk.RetryHint.NEVER
    assert error.details["profile_method"] == method_name


def test_easyremote_mission_transport_events_requires_run_id() -> None:
    transport = _EasyRemoteMissionTransport(object())

    with pytest.raises(easynet_sdk.SDKError) as exc_info:
        transport.events(b"{}")

    error = exc_info.value
    assert error.code is easynet_sdk.ErrorCode.INVALID_ARGUMENT
    assert error.stage == "easyremote_mission_profile"
