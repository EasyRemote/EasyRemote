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

    async def stream_function(self, node_id, function_name, *args, **kwargs):
        for idx, value in enumerate(args):
            yield {
                "node_id": node_id,
                "function_name": function_name,
                "index": idx,
                "value": value,
                "mode": "direct_stream",
            }

    async def stream_function_with_load_balancing(
        self, function_name, load_balancing, *args, **kwargs
    ):
        for idx, value in enumerate(args):
            yield {
                "function_name": function_name,
                "load_balancing": load_balancing,
                "index": idx,
                "value": value,
                "mode": "balanced_stream",
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


class FakeStreamingClient(FakeClient):
    def stream_with_context(self, context, *args, **kwargs):
        for index, value in enumerate(args):
            yield {
                "function_name": context.function_name,
                "strategy": context.strategy.value,
                "index": index,
                "value": value,
                "mode": "client_stream",
            }


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


def _set_fake_streaming_client() -> FakeStreamingClient:
    fake = FakeStreamingClient()
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


def test_remote_stream_returns_sync_iterator_without_running_loop():
    _set_fake_server()
    try:

        @remote(function_name="stream_numbers", stream=True)
        def stream_numbers(*values):
            return values

        chunks = list(stream_numbers(3, 5, 8))
        assert [chunk["value"] for chunk in chunks] == [3, 5, 8]
        assert all(chunk["mode"] == "direct_stream" for chunk in chunks)
    finally:
        _reset_backends()


def test_remote_stream_returns_async_iterator_inside_running_loop():
    _set_fake_server()
    try:

        @remote(function_name="stream_letters", stream=True)
        def stream_letters(*values):
            return values

        async def run_case():
            chunks = []
            stream_iter = stream_letters("a", "b")
            assert hasattr(stream_iter, "__aiter__")
            async for chunk in stream_iter:
                chunks.append(chunk["value"])
            assert chunks == ["a", "b"]

        asyncio.run(run_case())
    finally:
        _reset_backends()


def test_remote_stream_load_balancing_prefers_stream_api():
    _set_fake_server()
    try:

        @remote(function_name="stream_lb", stream=True, load_balancing="round_robin")
        def stream_lb(*values):
            return values

        chunks = list(stream_lb("x", "y"))
        assert [chunk["value"] for chunk in chunks] == ["x", "y"]
        assert all(chunk["mode"] == "balanced_stream" for chunk in chunks)
        assert all(chunk["load_balancing"] == "round_robin" for chunk in chunks)
    finally:
        _reset_backends()


def test_remote_stream_cross_loop_server_falls_back_safely():
    fake = LoopBoundFakeServer()
    RemoteFunction.server_resolver = staticmethod(lambda: fake)
    try:

        @remote(function_name="loop_bound_stream", stream=True)
        def loop_bound_stream(a, b):
            return a + b

        chunks = list(loop_bound_stream(10, 5))
        assert len(chunks) == 1
        assert chunks[0]["function_name"] == "loop_bound_stream"
        assert chunks[0]["result"] == 15
    finally:
        fake.close()
        _reset_backends()


def test_remote_stream_client_fallback_returns_single_chunk():
    _set_fake_client()
    try:

        @remote(function_name="client_stream_fallback", stream=True, load_balancing=True)
        def client_stream_fallback(value):
            return value

        chunks = list(client_stream_fallback(42))
        assert len(chunks) == 1
        assert chunks[0]["mode"] == "client"
        assert chunks[0]["function_name"] == "client_stream_fallback"
    finally:
        _reset_backends()


def test_remote_stream_client_native_stream_api_emits_incremental_chunks():
    _set_fake_streaming_client()
    try:

        @remote(function_name="client_native_stream", stream=True, load_balancing=True)
        def client_native_stream(a, b):
            return a + b

        chunks = list(client_native_stream("alpha", "beta"))
        assert [chunk["value"] for chunk in chunks] == ["alpha", "beta"]
        assert all(chunk["mode"] == "client_stream" for chunk in chunks)
    finally:
        _reset_backends()
