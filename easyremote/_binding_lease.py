"""One bounded provider-side scheduler for Runtime-owned binding leases.

The Runtime validates activation identity and expiry. This module only schedules
an atomic renewal of acknowledged bindings; it never installs or retries them.
A timed-out control call is execution-unknown, not cancelled by this worker.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from enum import StrEnum

import easynet_sdk

from .errors import InvalidArgument, Unavailable

MAX_BINDINGS = 256


class LeaseState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class BindingLeaseWorker:
    """Dynamic bounded membership; network calls never hold the membership lock."""

    def __init__(
        self,
        renew: Callable[[tuple[easynet_sdk.BindingLeaseRef, ...], float], object],
        failed: Callable[[BaseException], None],
        *,
        interval: float,
        timeout: float,
    ) -> None:
        if not (
            math.isfinite(interval)
            and math.isfinite(timeout)
            and 0 < timeout < interval
        ):
            raise ValueError("renewal timeout must be positive and below interval")
        self._renew = renew
        self._failed = failed
        self._interval = interval
        self._timeout = timeout
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._bindings: dict[str, easynet_sdk.BindingLeaseRef] = {}
        self._thread: threading.Thread | None = None
        self._state = LeaseState.IDLE
        self._failure: BaseException | None = None

    @property
    def state(self) -> LeaseState:
        with self._lock:
            return self._state

    @property
    def failure(self) -> BaseException | None:
        with self._lock:
            return self._failure

    def add(self, binding: easynet_sdk.BindingLeaseRef) -> None:
        with self._lock:
            if self._state in (LeaseState.FAILED, LeaseState.STOPPED):
                raise Unavailable(
                    "Binding renewal is inactive; stop this provider before restarting",
                    reason="binding_lease_inactive",
                )
            if (
                binding.ability_ura not in self._bindings
                and len(self._bindings) >= MAX_BINDINGS
            ):
                raise InvalidArgument(
                    "A provider supports at most 256 live bindings",
                    reason="binding_limit_exceeded",
                )
            self._bindings[binding.ability_ura] = binding
            if self._thread is None:
                self._state = LeaseState.RUNNING
                self._thread = threading.Thread(
                    target=self._run,
                    name="easyremote-binding-lease",
                    daemon=True,
                )
                self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            self._state = LeaseState.STOPPED
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            # The SDK bounds its wait; failure notification may stop the host
            # (HostServer.stop has a five-second join). This is not cancellation
            # of an execution-unknown transport request.
            thread.join(timeout=self._timeout + 6.0)
            if thread.is_alive():
                raise Unavailable(
                    "Binding lease worker exceeded its bounded shutdown wait",
                    reason="binding_lease_shutdown_timeout",
                )

    def _run(self) -> None:
        due = time.monotonic() + self._interval
        while not self._stop.wait(max(0.0, due - time.monotonic())):
            with self._lock:
                if self._stop.is_set():
                    return
                bindings = tuple(self._bindings.values())
            began = time.monotonic()
            try:
                self._renew(bindings, self._timeout)
            except BaseException as error:
                with self._lock:
                    if self._stop.is_set():
                        return
                    self._failure = error
                    self._state = LeaseState.FAILED
                    self._stop.set()
                self._failed(error)
                return
            due = began + self._interval
