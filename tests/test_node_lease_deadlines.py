"""Slow-startup and steady-state lease regressions using the real worker."""

import threading
from types import SimpleNamespace

import easynet_sdk
import pytest

from easyremote._binding_lease import BindingLeaseWorker, LeaseState
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.node import _BINDING_LEASE_MS, ComputeNode


def ref(index):
    return easynet_sdk.BindingLeaseRef(
        f"easynet:///r/test/ability/system-agent.test.manager.fn{index}",
        f"install-{index}",
        f"activation-{index}",
    )


class StartupControl:
    def __init__(self):
        self.count = 0
        self.second_install = threading.Event()
        self.release_install = threading.Event()
        self.renewed_first = threading.Event()
        self.renewed_all = threading.Event()
        self.renewals = []
        self.uninstalls = []

    def install(self, path, *, node, binding_lease_ms):
        self.count += 1
        index = self.count
        if index == 2:
            self.second_install.set()
            assert self.release_install.wait(2), "test did not release slow install"
        return SimpleNamespace(**ref(index).to_json_dict())

    def renew_bindings(self, bindings, *, node, timeout):
        self.renewals.append(bindings)
        if len(bindings) == 1:
            self.renewed_first.set()
        if len(bindings) == self.count and self.count > 1:
            self.renewed_all.set()

    def uninstall(self, ability_ura, *, install_id, activation_id, node, timeout):
        self.uninstalls.append((ability_ura, install_id, activation_id))


def make_node(tmp, monkeypatch, count=8):
    import easyremote.node as module

    monkeypatch.setattr(module, "_BINDING_RENEW_INTERVAL_SECONDS", 0.03)
    monkeypatch.setattr(module, "_BINDING_CONTROL_TIMEOUT_SECONDS", 0.01)
    control = StartupControl()
    connection = SimpleNamespace(close=lambda: None)
    node = ComputeNode(
        abilities_dir=tmp / "abilities",
        ability_control=control,
        runtime_provider=SimpleNamespace(connect=lambda: connection),
    )

    def identity(value: int) -> int:
        return value

    for index in range(count):
        node.register(identity, name=f"fn{index}")
    return node, control


def start_async(node):
    errors = []

    def start():
        try:
            node.start()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=start)
    thread.start()
    return thread, errors


@pytest.mark.parametrize("count", [2, 8])
def test_first_binding_is_renewed_before_slow_startup_finishes(
    short_tmp, monkeypatch, count
):
    node, control = make_node(short_tmp, monkeypatch, count)
    thread, errors = start_async(node)
    try:
        assert control.second_install.wait(1)
        assert not node._started
        assert control.renewed_first.wait(1), "renewal waits for all deployments"
        assert control.count == 2
        worker = node._lease_worker
        control.release_install.set()
        thread.join(1)
        assert not thread.is_alive()
        assert not errors
        assert control.renewed_all.wait(1)
        assert node._lease_worker is worker
        assert len(control.renewals[-1]) == count
        assert control.count == count, "renewal must not redeploy"
    finally:
        control.release_install.set()
        thread.join(2)
        node.stop()
    assert len(control.uninstalls) == count


def test_stop_fences_late_deploy_completion(short_tmp, monkeypatch):
    node, control = make_node(short_tmp, monkeypatch)
    thread, errors = start_async(node)
    try:
        assert control.second_install.wait(1)
        assert control.renewed_first.wait(1)
        node.stop()
        after_stop = len(control.renewals)
        control.release_install.set()
        thread.join(1)
        assert not thread.is_alive()
        assert errors[0].reason == "provider_start_cancelled"
        assert node._lease_worker is None
        assert not node._started
        assert not node.host_socket.exists()
        assert len(control.renewals) == after_stop
        assert len(control.uninstalls) == 1
    finally:
        control.release_install.set()
        thread.join(2)
        node.stop()


def test_old_start_cannot_stop_or_renew_replacement_generation(short_tmp, monkeypatch):
    node, control = make_node(short_tmp, monkeypatch, 2)
    thread, errors = start_async(node)
    try:
        assert control.second_install.wait(1)
        node.stop()
        node.start()
        replacement = node._lease_worker
        replacement_ids = {info.activation_id for info in node.abilities}
        control.release_install.set()
        thread.join(1)
        assert errors[0].reason == "provider_start_cancelled"
        assert node._started
        assert node.host_socket.exists()
        assert node._lease_worker is replacement
        assert {info.activation_id for info in node.abilities} == replacement_ids
        assert "activation-2" not in replacement_ids
    finally:
        control.release_install.set()
        thread.join(2)
        node.stop()


class BindingClock:
    def __init__(self, count):
        self.now = 0.0
        self.deadlines = {ref(i).ability_ura: 9.0 for i in range(count)}
        self.expired = []

    def advance(self, duration):
        self.now += duration
        for name, deadline in self.deadlines.items():
            if self.now >= deadline:
                self.expired.append((name, deadline, self.now))


class LogicalStop:
    def __init__(self, clock):
        self.clock, self.rounds, self.stopped = clock, 0, False

    def wait(self, duration):
        self.rounds += 1
        if self.rounds > 4:
            return True
        self.clock.advance(duration)
        return self.stopped

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True


@pytest.mark.parametrize("count,cost", [(8, 1.0), (8, 0.01), (1, 1.0)])
def test_live_bindings_do_not_expire_during_slow_atomic_renewal(
    count, cost, monkeypatch
):
    import easyremote._binding_lease as module

    clock = BindingClock(count)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock.now)
    calls = []

    def renew(bindings, timeout):
        assert timeout == 2.0
        clock.advance(cost)
        calls.append(bindings)
        for binding in bindings:
            clock.deadlines[binding.ability_ura] = clock.now + _BINDING_LEASE_MS / 1000

    worker = BindingLeaseWorker(renew, lambda _: None, interval=3.0, timeout=2.0)
    worker._bindings = {ref(i).ability_ura: ref(i) for i in range(count)}
    worker._stop = LogicalStop(clock)
    worker._run()
    assert not clock.expired, f"live bindings missed deadlines: {clock.expired}"
    assert len(calls) == 4
    assert all(len(batch) == count for batch in calls)


def test_membership_is_not_locked_during_network_and_stop_sends_no_followup():
    entered, release, added = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def renew(bindings, timeout):
        calls.append(bindings)
        entered.set()
        assert release.wait(1)

    worker = BindingLeaseWorker(renew, lambda _: None, interval=0.03, timeout=0.01)
    worker.add(ref(1))
    assert entered.wait(1)
    membership = threading.Thread(target=lambda: (worker.add(ref(2)), added.set()))
    membership.start()
    stopper = threading.Thread(target=worker.stop)
    try:
        assert added.wait(0.5), "network invocation held membership lock"
        stopper.start()
        assert worker._stop.wait(0.5)
    finally:
        release.set()
        membership.join(1)
        if stopper.ident is not None:
            stopper.join(1)
        worker.stop()
    assert len(calls) == 1
    assert worker.state is LeaseState.STOPPED
    assert not worker._thread.is_alive()


def test_renewal_failure_is_terminal_without_retry():
    notified = threading.Event()
    calls = []
    failure = RuntimeError("activation replaced")

    def renew(bindings, timeout):
        calls.append(bindings)
        raise failure

    worker = BindingLeaseWorker(
        renew, lambda _: notified.set(), interval=0.03, timeout=0.01
    )
    worker.add(ref(1))
    assert notified.wait(1)
    worker._thread.join(1)
    assert not worker._thread.is_alive()
    assert worker.state is LeaseState.FAILED
    assert worker.failure is failure
    assert len(calls) == 1
    with pytest.raises(Unavailable, match="renewal is inactive"):
        worker.add(ref(2))
    worker.stop()


def test_worker_cardinality_and_finite_timing_bounds():
    worker = BindingLeaseWorker(lambda *_: None, lambda _: None, interval=3, timeout=2)
    worker._bindings = {ref(i).ability_ura: ref(i) for i in range(256)}
    with pytest.raises(InvalidArgument, match="at most 256"):
        worker.add(ref(256))
    assert len(worker._bindings) == 256
    assert worker._thread is None
    for interval, timeout in [(float("inf"), 2), (3, float("nan")), (3, 3), (3, 0)]:
        with pytest.raises(ValueError):
            BindingLeaseWorker(
                lambda *_: None, lambda _: None, interval=interval, timeout=timeout
            )


def test_renewal_failure_closes_host_and_refuses_silent_restart(short_tmp, monkeypatch):
    node, control = make_node(short_tmp, monkeypatch, 1)
    failed = threading.Event()

    def reject(*_, **__):
        failed.set()
        raise RuntimeError("activation replaced")

    control.renew_bindings = reject
    node.start()
    try:
        assert failed.wait(1)
        node._lease_worker._thread.join(6)
        assert not node.host_socket.exists()
        assert node.publication_state.value == "LEASE_FAILED"
        assert str(node.lease_failure) == "activation replaced"
        with pytest.raises(Unavailable, match="binding renewal failed"):
            node.start()
        assert control.count == 1
    finally:
        node.stop()


def test_missing_activation_fails_closed_and_keeps_host_stopped(short_tmp, monkeypatch):
    node, control = make_node(short_tmp, monkeypatch, 1)
    control.install = lambda *_, **__: SimpleNamespace(
        ability_ura="ability", install_id="i"
    )
    with pytest.raises(Unavailable) as error:
        node.start()
    assert error.value.reason == "binding_activation_missing"
    assert not node.host_socket.exists()
    assert node._lease_worker is None


def test_registration_preserves_original_failure_when_cleanup_also_fails(
    short_tmp, monkeypatch
):
    node, control = make_node(short_tmp, monkeypatch, 1)
    control.release_install.set()
    node.start()

    def fail_track(_):
        raise RuntimeError("track failed")

    def fail_cleanup(*_, **__):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(node, "_track_binding", fail_track)
    original = control.uninstall
    control.uninstall = fail_cleanup
    try:

        def identity(value: int) -> int:
            return value

        with pytest.raises(RuntimeError, match="track failed") as error:
            node.register(identity, name="late")
        assert error.value.__notes__ == ["registration rollback failed: cleanup failed"]
    finally:
        control.uninstall = original
        node.stop()


def test_delayed_start_rollback_atomically_checks_generation(short_tmp, monkeypatch):
    node, control = make_node(short_tmp, monkeypatch, 1)
    original_install = control.install
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("initial deploy failed")
        return original_install(*args, **kwargs)

    control.install = fail_once
    rollback_ready, release = threading.Event(), threading.Event()
    original_shutdown = node._shutdown

    def delayed_shutdown(*, expected_generation=None):
        if threading.current_thread().name == "old-start":
            rollback_ready.set()
            assert release.wait(2)
        original_shutdown(expected_generation=expected_generation)

    monkeypatch.setattr(node, "_shutdown", delayed_shutdown)
    errors = []

    def old_start():
        try:
            node.start()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=old_start, name="old-start")
    thread.start()
    try:
        assert rollback_ready.wait(1)
        node.stop()
        node.start()
        replacement = node._lease_worker
        activations = [info.activation_id for info in node.abilities]
        release.set()
        thread.join(1)
        assert not thread.is_alive()
        assert str(errors[0]) == "initial deploy failed"
        assert node._started
        assert node.host_socket.exists()
        assert node._lease_worker is replacement
        assert [info.activation_id for info in node.abilities] == activations
    finally:
        release.set()
        thread.join(2)
        node.stop()


def test_registration_rollback_mutation_is_atomic_and_revoke_uses_old_ref(
    short_tmp, monkeypatch
):
    node, control = make_node(short_tmp, monkeypatch, 1)
    control.release_install.set()
    node.start()
    pop_ready, release_pop = threading.Event(), threading.Event()
    revoke_ready, release_revoke = threading.Event(), threading.Event()

    class PausedPop(dict):
        def pop(self, key, default=None):
            if key == "late":
                pop_ready.set()
                assert release_pop.wait(2)
            return super().pop(key, default)

    node._abilities = PausedPop(node._abilities)
    original_track = node._track_binding
    original_revoke = control.uninstall

    def fail_late(info):
        if info.name == "late":
            raise RuntimeError("late tracking failed")
        original_track(info)

    def delay_old_revoke(ability, *, install_id, activation_id, **kwargs):
        if activation_id == "activation-2":
            revoke_ready.set()
            assert release_revoke.wait(2)
        return original_revoke(
            ability, install_id=install_id, activation_id=activation_id, **kwargs
        )

    monkeypatch.setattr(node, "_track_binding", fail_late)
    control.uninstall = delay_old_revoke
    errors = []

    def identity(value: int) -> int:
        return value

    def register():
        try:
            node.register(identity, name="late")
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=register)
    thread.start()
    try:
        assert pop_ready.wait(1)
        acquired = node._lifecycle_lock.acquire(blocking=False)
        if acquired:
            node._lifecycle_lock.release()
        assert not acquired, "generation check and rollback pop must hold one lock"
        release_pop.set()
        assert revoke_ready.wait(1)
        # The old activation's network cleanup must not hold the lifecycle lock.
        node.stop()
        monkeypatch.setattr(node, "_track_binding", original_track)
        node.register(identity, name="late")
        node.start()
        replacement = node._abilities["late"]
        release_revoke.set()
        thread.join(1)
        assert str(errors[0]) == "late tracking failed"
        assert node._abilities["late"] is replacement
        assert node.host_socket.exists()
        assert replacement.activation_id != "activation-2"
        assert any(row[2] == "activation-2" for row in control.uninstalls)
    finally:
        release_pop.set()
        release_revoke.set()
        thread.join(2)
        node.stop()
