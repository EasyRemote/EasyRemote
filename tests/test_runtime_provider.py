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
                connect_error=_sdk_error(easynet_sdk.ErrorCode.RUNTIME_OFFLINE),
            ),
        ),
        identity_loader=lambda: _identity(events),
    )

    with pytest.raises(Unavailable) as raised:
        provider.connect()

    assert raised.value.reason == "daemon_down"
    assert events == ["identity", "connect"]


def test_provider_bootstraps_a_local_identity_on_first_run() -> None:
    """A fresh install has no identity yet; that is a state to resolve, not
    an error to report. The Runtime owns the bootstrap, so the provider
    triggers it once and re-reads."""
    events: list[str] = []
    identities = iter([Unavailable("missing", reason="not_paired"), None])

    def identity_loader() -> LocalIdentity:
        events.append("identity")
        outcome = next(identities)
        if isinstance(outcome, Exception):
            raise outcome
        return cast(LocalIdentity, object())

    def bootstrap() -> None:
        events.append("bootstrap")

    connection = FakeConnection()
    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            easynet_sdk.SdkEnvironment,
            FakeEnvironment(events, connection),
        ),
        identity_loader=identity_loader,
        bootstrap=bootstrap,
    )

    assert provider.connect() is connection
    assert events == ["identity", "bootstrap", "identity", "connect"]


def test_provider_reports_onboarding_when_bootstrap_yields_no_identity() -> None:
    """The bootstrap succeeding is not the same as an identity existing;
    claiming success without one would strand the caller."""
    def identity_loader() -> LocalIdentity:
        raise Unavailable("missing", reason="not_paired")

    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            Any,
            pytest.fail("runtime connection must not precede identity"),
        ),
        identity_loader=identity_loader,
        bootstrap=lambda: None,
    )

    with pytest.raises(Unavailable) as raised:
        provider.connect()

    assert raised.value.reason == "onboarding_required"
    assert "easynet runtime status" in str(raised.value)


def test_provider_does_not_bootstrap_over_corrupt_credentials() -> None:
    """Broken credentials are not a fresh install: re-running the bootstrap
    would not repair them and would hide the real cause."""
    def identity_loader() -> LocalIdentity:
        raise Unavailable("corrupt", reason="not_paired_corrupt")

    provider = LocalRuntimeProvider(
        environment_factory=lambda: cast(
            Any,
            pytest.fail("runtime connection must not precede identity"),
        ),
        identity_loader=identity_loader,
        bootstrap=lambda: pytest.fail("must not bootstrap over corrupt credentials"),
    )

    with pytest.raises(Unavailable) as raised:
        provider.connect()

    assert raised.value.reason == "onboarding_required"
    assert "easynet device reset" in str(raised.value)


def _sdk_error(code: easynet_sdk.ErrorCode) -> easynet_sdk.SDKError:
    return easynet_sdk.SDKError(
        code=code,
        stage="test",
        retry=easynet_sdk.RetryHint.NEVER,
        retryable=False,
        message="runtime connection failed",
    )
