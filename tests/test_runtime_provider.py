"""Runtime provider: connect through the SDK without process ownership."""

from __future__ import annotations

from typing import Any, cast

import easynet_sdk
import pytest

from easyremote.errors import Unavailable
from easyremote.identity import LocalIdentity
from easyremote.runtime_provider import LocalRuntimeProvider


class FakeConnection:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeEnvironment:
    def __init__(
        self,
        events: list[str],
        connection: FakeConnection | None = None,
        *,
        connect_error: easynet_sdk.SDKError | None = None,
    ) -> None:
        self.events = events
        self.connection = connection
        self.connect_error = connect_error

    def runtime_connection(self) -> easynet_sdk.RuntimeConnection:
        self.events.append("connect")
        if self.connect_error is not None:
            raise self.connect_error
        assert self.connection is not None
        return cast(easynet_sdk.RuntimeConnection, self.connection)


def _identity(events: list[str]) -> LocalIdentity:
    events.append("identity")
    return LocalIdentity(
        realm="acme",
        node_id="dev-a",
        username=None,
        hub_endpoint="hub:443",
    )


def test_provider_acquires_sdk_runtime_connection_after_pairing() -> None:
    events: list[str] = []
    connection = FakeConnection()
    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            easynet_sdk.SdkEnvironment,
            FakeEnvironment(events, connection),
        ),
        identity_loader=lambda: _identity(events),
    )

    runtime = provider.connect()
    runtime.close()

    assert events == ["identity", "connect"]
    assert connection.close_calls == 1


def test_provider_maps_sdk_connection_failure_without_starting_a_process() -> None:
    events: list[str] = []
    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            easynet_sdk.SdkEnvironment,
            FakeEnvironment(
                events,
                connect_error=_sdk_error(easynet_sdk.ErrorCode.DAEMON_OFFLINE),
            ),
        ),
        identity_loader=lambda: _identity(events),
    )

    with pytest.raises(Unavailable) as raised:
        provider.connect()

    assert raised.value.reason == "daemon_down"
    assert events == ["identity", "connect"]


def test_provider_requires_operator_pairing_before_runtime_connection() -> None:
    events: list[str] = []

    def missing_identity() -> LocalIdentity:
        events.append("identity")
        raise Unavailable("missing", reason="not_paired")

    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            Any,
            pytest.fail("runtime connection must not precede pairing"),
        ),
        identity_loader=missing_identity,
    )

    with pytest.raises(Unavailable) as raised:
        provider.connect()

    assert raised.value.reason == "onboarding_required"
    assert "easynet pair" in str(raised.value)
    assert events == ["identity"]


def _sdk_error(code: easynet_sdk.ErrorCode) -> easynet_sdk.SDKError:
    return easynet_sdk.SDKError(
        code=code,
        stage="test",
        retry=easynet_sdk.RetryHint.NEVER,
        retryable=False,
        message="runtime connection failed",
    )
