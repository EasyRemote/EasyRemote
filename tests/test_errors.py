"""Error taxonomy: SDK mapping completeness and retriability contract."""

import easynet_sdk
import pytest

from easyremote.errors import (
    Cancelled,
    DeadlineExceeded,
    InternalError,
    InvalidArgument,
    PermissionDenied,
    RemoteError,
    ResourceExhausted,
    Unavailable,
    error_from_sdk,
)

# Every SDK error code and its EasyRemote-facing projection.
SDK_CASES = [
    (easynet_sdk.ErrorCode.INVALID_ARGUMENT, InvalidArgument, "invalid_argument"),
    (easynet_sdk.ErrorCode.INVALID_HANDLE, InternalError, "invalid_handle"),
    (easynet_sdk.ErrorCode.NULL_POINTER, InternalError, "null_pointer"),
    (easynet_sdk.ErrorCode.INVALID_UTF8, InvalidArgument, "invalid_utf8"),
    (easynet_sdk.ErrorCode.NOT_INITIALIZED, Unavailable, "not_initialized"),
    (easynet_sdk.ErrorCode.ALREADY_INIT, InternalError, "already_initialized"),
    (easynet_sdk.ErrorCode.DAEMON_OFFLINE, Unavailable, "daemon_down"),
    (easynet_sdk.ErrorCode.PERMISSION_DENIED, PermissionDenied, "permission_denied"),
    (easynet_sdk.ErrorCode.ADMISSION_DENIED, PermissionDenied, "admission_denied"),
    (easynet_sdk.ErrorCode.ABILITY_NOT_FOUND, InvalidArgument, "ability_not_found"),
    (easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE, Unavailable, "route_unavailable"),
    (easynet_sdk.ErrorCode.TIMEOUT, DeadlineExceeded, "timeout"),
    (easynet_sdk.ErrorCode.CANCELLED, Cancelled, "cancelled"),
    (easynet_sdk.ErrorCode.INVALID_INVOCATION, InvalidArgument, "invalid_invocation"),
    (easynet_sdk.ErrorCode.PROTOCOL_MISMATCH, InternalError, "protocol_mismatch"),
    (easynet_sdk.ErrorCode.VERSION_MISMATCH, Unavailable, "version_mismatch"),
    (
        easynet_sdk.ErrorCode.VERSION_INCOMPATIBLE,
        Unavailable,
        "version_incompatible",
    ),
    (easynet_sdk.ErrorCode.CONTROL_ONLY, Unavailable, "control_only"),
    (easynet_sdk.ErrorCode.TRANSPORT, Unavailable, "transport"),
    (easynet_sdk.ErrorCode.PROTOCOL, InternalError, "protocol"),
    (easynet_sdk.ErrorCode.NOT_FOUND, InvalidArgument, "not_found"),
    (easynet_sdk.ErrorCode.ABILITY_FAILED, InternalError, "ability_failed"),
    (easynet_sdk.ErrorCode.NOT_IMPLEMENTED, InternalError, "not_implemented"),
    (easynet_sdk.ErrorCode.GENERIC, InternalError, "generic"),
]


@pytest.mark.parametrize(("code", "cls", "reason"), SDK_CASES)
def test_every_sdk_code_maps(code, cls, reason):
    err = error_from_sdk(_sdk_error(code, "boom"))
    assert type(err) is cls
    assert err.reason == reason
    assert str(err) == "boom"


def test_sdk_mapping_covers_every_error_code():
    assert {code for code, _, _ in SDK_CASES} == set(easynet_sdk.ErrorCode)


def test_daemon_down_without_message_is_actionable():
    err = error_from_sdk(_sdk_error(easynet_sdk.ErrorCode.DAEMON_OFFLINE))
    assert "easynet start" in str(err)


def test_sdk_retry_after_is_preserved():
    err = error_from_sdk(
        _sdk_error(
            easynet_sdk.ErrorCode.TRANSPORT,
            details={"retry_after": 1.5},
        )
    )
    assert type(err) is Unavailable
    assert err.retry_after == 1.5


def test_sdk_error_cause_passthrough():
    cause = InvalidArgument("bad", reason="product_reason")
    err = error_from_sdk(
        _sdk_error(easynet_sdk.ErrorCode.INVALID_ARGUMENT, cause=cause)
    )
    assert err is cause


def test_kind_matches_class():
    assert Unavailable("x").kind == "UNAVAILABLE"
    assert Cancelled("x").kind == "CANCELLED"


def test_retriable_contract():
    assert Unavailable("x").retriable
    assert ResourceExhausted("x", retry_after=1.5).retriable
    assert not ResourceExhausted("x").retriable
    assert not InternalError("x").retriable
    assert not DeadlineExceeded("x").retriable


def test_all_runtime_errors_are_remote_errors():
    for _, cls, _ in SDK_CASES:
        assert issubclass(cls, RemoteError)


def _sdk_error(
    code: easynet_sdk.ErrorCode,
    message: str = "",
    *,
    details: dict[str, object] | None = None,
    cause: BaseException | None = None,
) -> easynet_sdk.SDKError:
    return easynet_sdk.SDKError(
        code=code,
        stage="test",
        retry=easynet_sdk.RetryHint.NEVER,
        retryable=False,
        message=message,
        details=details or {},
        cause=cause,
    )
