#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for EasyRemote decorators module.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import threading
from types import SimpleNamespace

from easyremote.decorators import RemoteFunction, remote
from easyremote.core.utils.concurrency import LoopBoundAsyncLock
from easyremote.core.nodes.client import ExecutionStrategy


class FakeServer:
    async def execute_function(self, node_id, function_name, *args, **kwargs):
        return {
            "node_id": node_id,
            "function_name": function_name,
            "args": list(args),
            "kwargs": kwargs,
            "mode": "direct",
        }

    async def execute_function_with_load_balancing(
        self, function_name, load_balancing, *args, **kwargs
    ):
        return {
            "function_name": function_name,
            "load_balancing": load_balancing,
            "args": list(args),
            "kwargs": kwargs,
            "mode": "balanced",
        }


class LoopBoundFakeServer:
    """
    Fake server that simulates EasyRemote background-server event-loop ownership.
    """

    def __init__(self):
        self._event_loop = asyncio.new_event_loop()
        self._lock = LoopBoundAsyncLock(name="test-loop-bound-lock")
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        # Pre-bind lock to server loop to reproduce cross-loop behavior.
        asyncio.run_coroutine_threadsafe(self._bind_lock(), self._event_loop).result(timeout=2.0)

    def _run_loop(self):
        asyncio.set_event_loop(self._event_loop)
        self._ready.set()
        self._event_loop.run_forever()
        self._event_loop.close()

    async def _bind_lock(self):
        async with self._lock:
            return None

    async def execute_function(self, node_id, function_name, *args, **kwargs):
        async with self._lock:
            return {
                "node_id": node_id,
                "function_name": function_name,
                "args": list(args),
                "kwargs": kwargs,
                "result": sum(args) if args else None,
                "mode": "direct",
            }

    async def execute_function_with_load_balancing(
        self, function_name, load_balancing, *args, **kwargs
    ):
        async with self._lock:
            return {
                "function_name": function_name,
                "load_balancing": load_balancing,
                "args": list(args),
                "kwargs": kwargs,
                "result": sum(args) if args else None,
                "mode": "balanced",
            }

    def close(self) -> None:
        if self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)
        self._thread.join(timeout=2.0)


class FakeClient:
    def __init__(self):
        self.calls = []

    def execute_with_context(self, context, *args, **kwargs):
        self.calls.append((context, args, kwargs))
        return SimpleNamespace(
            result={
                "function_name": context.function_name,
                "strategy": context.strategy.value,
                "preferred_node_ids": context.preferred_node_ids or [],
                "args": list(args),
                "kwargs": kwargs,
                "mode": "client",
            }
        )


def _set_fake_server() -> FakeServer:
    fake = FakeServer()
    RemoteFunction.server_resolver = staticmethod(lambda: fake)
    RemoteFunction.client_resolver = staticmethod(lambda: None)
    return fake


def _set_fake_client() -> FakeClient:
    fake = FakeClient()
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: fake)
    return fake


def _reset_backends() -> None:
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: None)


def test_remote_sync_executes_async_server_call():
    _set_fake_server()
    try:

        @remote(function_name="sum_values")
        def sum_values(a, b):
            return a + b

        response = sum_values(1, 2)
        assert response["function_name"] == "sum_values"
        assert response["args"] == [1, 2]
        assert response["mode"] == "direct"
    finally:
        _reset_backends()


def test_remote_async_wrapper_uses_load_balancing():
    _set_fake_server()
    try:

        @remote(function_name="multiply", async_func=True, load_balancing="round_robin")
        async def multiply(a, b):
            return a * b

        response = asyncio.run(multiply(2, 3))
        assert response["function_name"] == "multiply"
        assert response["load_balancing"] == "round_robin"
        assert response["mode"] == "balanced"
    finally:
        _reset_backends()


def test_remote_returns_coroutine_inside_running_loop():
    _set_fake_server()
    try:

        @remote(function_name="inside_loop")
        def inside_loop(value):
            return value

        async def run_case():
            pending = inside_loop("x")
            assert asyncio.iscoroutine(pending)
            result = await pending
            assert result["function_name"] == "inside_loop"
            assert result["args"] == ["x"]

        asyncio.run(run_case())
    finally:
        _reset_backends()


def test_remote_direct_call_preserves_options():
    _set_fake_server()
    try:
        def base_func():
            return "ignored"

        wrapped = remote(base_func, function_name="custom_name", node_id="node-9")
        response = wrapped()
        assert response["function_name"] == "custom_name"
        assert response["node_id"] == "node-9"
    finally:
        _reset_backends()


def test_remote_sync_call_dispatches_to_server_event_loop():
    fake = LoopBoundFakeServer()
    RemoteFunction.server_resolver = staticmethod(lambda: fake)
    try:

        @remote(function_name="loop_bound_sum")
        def loop_bound_sum(a, b):
            return a + b

        response = loop_bound_sum(4, 5)
        assert response["function_name"] == "loop_bound_sum"
        assert response["result"] == 9
    finally:
        fake.close()
        _reset_backends()


def test_remote_async_call_dispatches_to_server_event_loop():
    fake = LoopBoundFakeServer()
    RemoteFunction.server_resolver = staticmethod(lambda: fake)
    try:

        @remote(function_name="loop_bound_async", async_func=True)
        async def loop_bound_async(a, b):
            return a + b

        response = asyncio.run(loop_bound_async(6, 7))
        assert response["function_name"] == "loop_bound_async"
        assert response["result"] == 13
    finally:
        fake.close()
        _reset_backends()


def test_remote_falls_back_to_client_direct_target():
    fake = _set_fake_client()
    try:

        @remote(function_name="client_direct", node_id="node-1")
        def client_direct(a, b):
            return a + b

        response = client_direct(1, 2)
        assert response["mode"] == "client"
        assert response["function_name"] == "client_direct"
        assert response["strategy"] == ExecutionStrategy.DIRECT_TARGET.value
        assert response["preferred_node_ids"] == ["node-1"]
        assert response["args"] == [1, 2]
        assert len(fake.calls) == 1
    finally:
        _reset_backends()


def test_remote_falls_back_to_client_load_balanced():
    fake = _set_fake_client()
    try:

        @remote(function_name="client_lb", load_balancing=True)
        def client_lb(x):
            return x

        response = client_lb(9)
        assert response["mode"] == "client"
        assert response["function_name"] == "client_lb"
        assert response["strategy"] == ExecutionStrategy.LOAD_BALANCED.value
        assert response["preferred_node_ids"] == []
        assert response["args"] == [9]
        assert len(fake.calls) == 1
    finally:
        _reset_backends()
