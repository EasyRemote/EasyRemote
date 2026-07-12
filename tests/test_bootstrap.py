"""Device runtime bootstrap: one authoring path, explicit runtime states."""

from __future__ import annotations

import pytest

from easyremote.bootstrap import DeviceRuntimeBootstrap, RuntimeBootstrapState
from easyremote.errors import Unavailable
from easyremote.identity import LocalIdentity


class FakeEnvironment:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def feature_set(self) -> object:
        self._events.append("sdk")
        return object()


class FakeDaemon:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True
        self._events.append("stop")


def _identity(events: list[str]) -> LocalIdentity:
    events.append("identity")
    return LocalIdentity(
        realm="acme",
        node_id="dev-a",
        username=None,
        hub_endpoint="hub:443",
    )


def test_bootstrap_reuses_live_daemon_after_sdk_and_identity_checks():
    events: list[str] = []
    bootstrap = DeviceRuntimeBootstrap(
        environment_factory=lambda: FakeEnvironment(events),  # type: ignore[arg-type]
        identity_loader=lambda: _identity(events),
        daemon_available=lambda: events.append("probe") is None or True,
        daemon_starter=lambda _: pytest.fail("must not start a live daemon"),
    )

    lease = bootstrap.ensure()

    assert events == ["sdk", "identity", "probe"]
    assert lease.state is RuntimeBootstrapState.DAEMON_REUSED
    assert not lease.started_daemon


def test_bootstrap_starts_and_owns_only_a_missing_daemon():
    events: list[str] = []
    daemon = FakeDaemon(events)
    bootstrap = DeviceRuntimeBootstrap(
        environment_factory=lambda: FakeEnvironment(events),  # type: ignore[arg-type]
        identity_loader=lambda: _identity(events),
        daemon_available=lambda: (events.append("probe"), False)[1],
        daemon_starter=lambda node_id: events.append(f"start:{node_id}") or daemon,  # type: ignore[return-value]
    )

    lease = bootstrap.ensure()
    lease.close()
    lease.close()

    assert events == ["sdk", "identity", "probe", "start:dev-a", "stop"]
    assert lease.state is RuntimeBootstrapState.DAEMON_STARTED
    assert daemon.stopped


def test_bootstrap_requires_explicit_pairing_instead_of_creating_identity():
    events: list[str] = []

    def missing_identity() -> LocalIdentity:
        events.append("identity")
        raise Unavailable("missing", reason="not_paired")

    bootstrap = DeviceRuntimeBootstrap(
        environment_factory=lambda: FakeEnvironment(events),  # type: ignore[arg-type]
        identity_loader=missing_identity,
        daemon_available=lambda: pytest.fail("must not probe before pairing"),
    )

    with pytest.raises(Unavailable) as raised:
        bootstrap.ensure()

    assert events == ["sdk", "identity"]
    assert raised.value.reason == "onboarding_required"
    assert "easynet pair" in str(raised.value)
