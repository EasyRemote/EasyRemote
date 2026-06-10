"""Error taxonomy: ABI mapping completeness and retriability contract."""

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
    error_from_abi,
)

# Every code from include/easynet_cli.h (ABI v3) and its expected class.
ABI_CASES = [
    (1, InternalError, "generic"),
    (2, InternalError, "null_pointer"),
    (3, InvalidArgument, "invalid_utf8"),
    (4, InternalError, "invalid_handle"),
    (5, Unavailable, "not_initialized"),
    (6, InternalError, "already_initialized"),
    (7, Unavailable, "daemon_down"),
    (8, Unavailable, "version_incompatible"),
    (9, InternalError, "ability_failed"),
    (10, InternalError, "not_implemented"),
    (11, InvalidArgument, "invalid_argument"),
    (12, PermissionDenied, "permission_denied"),
    (13, InvalidArgument, "not_found"),
    (14, Cancelled, "cancelled"),
    (15, InternalError, "protocol"),
    (16, DeadlineExceeded, "timeout"),
]


@pytest.mark.parametrize(("code", "cls", "reason"), ABI_CASES)
def test_every_abi_code_maps(code, cls, reason):
    err = error_from_abi(code, "boom")
    assert type(err) is cls
    assert err.reason == reason
    assert str(err) == "boom"


def test_unknown_abi_code_is_internal():
    err = error_from_abi(99)
    assert type(err) is InternalError
    assert err.reason == "unknown_abi_code_99"


def test_daemon_down_without_message_is_actionable():
    err = error_from_abi(7)
    assert "easynet start" in str(err)


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
    for _, cls, _ in ABI_CASES:
        assert issubclass(cls, RemoteError)
