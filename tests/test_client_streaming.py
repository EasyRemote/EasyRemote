#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for bidirectional client streaming APIs.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable, Iterator, Optional

from easyremote.core.nodes.client import (
    ConnectionState,
    DistributedComputingClient,
    ExecutionContext,
    ExecutionStrategy,
)
from easyremote.core.protos import service_pb2
from easyremote.core.data.serialize import serialize_result


class _FakeResponseStream:
    def __init__(self, frames: Iterable[service_pb2.StreamCallFrame]):
        self._frames = list(frames)
        self.cancel_called = False

    def __iter__(self) -> Iterator[service_pb2.StreamCallFrame]:
        return iter(self._frames)

    def cancel(self) -> None:
        self.cancel_called = True


class _FakeStreamStub:
    def __init__(self, frames: Iterable[service_pb2.StreamCallFrame]):
        self._frames = list(frames)
        self.start_frame: Optional[service_pb2.StreamCallFrame] = None
        self.cancel_frame: Optional[service_pb2.StreamCallFrame] = None
        self.response_stream = _FakeResponseStream(self._frames)

    def StreamCall(self, request_iterator, timeout=None):
        # Capture first start frame.
        self.start_frame = next(request_iterator)
        return self.response_stream


def _chunk_frame(value: Any, *, done: bool = False) -> service_pb2.StreamCallFrame:
    frame = service_pb2.StreamCallFrame()
    frame.exec_res.call_id = "call-1"
    frame.exec_res.function_name = "stream_values"
    frame.exec_res.has_error = False
    frame.exec_res.is_done = done
    if not done:
        frame.exec_res.chunk = serialize_result(value)
    return frame


def _connected_client(stub: _FakeStreamStub) -> DistributedComputingClient:
    client = DistributedComputingClient("127.0.0.1:8080")
    client._connection_state = ConnectionState.CONNECTED
    client._gateway_stub = stub
    return client


def test_stream_with_context_load_balanced_yields_chunks() -> None:
    stub = _FakeStreamStub(
        frames=[
            _chunk_frame("a"),
            _chunk_frame("b"),
            _chunk_frame(None, done=True),
        ]
    )
    client = _connected_client(stub)

    context = ExecutionContext(
        function_name="stream_values",
        strategy=ExecutionStrategy.LOAD_BALANCED,
    )
    chunks = list(client.stream_with_context(context, 1, 2))

    assert chunks == ["a", "b"]
    assert stub.start_frame is not None
    assert stub.start_frame.start.function_name == "stream_values"
    assert stub.start_frame.start.use_load_balancing is True


def test_stream_with_context_direct_target_sets_node_id() -> None:
    stub = _FakeStreamStub(
        frames=[
            _chunk_frame({"step": 1}),
            _chunk_frame(None, done=True),
        ]
    )
    client = _connected_client(stub)

    context = ExecutionContext(
        function_name="stream_values",
        strategy=ExecutionStrategy.DIRECT_TARGET,
        preferred_node_ids=["node-7"],
    )
    chunks = list(client.stream_with_context(context, "payload"))

    assert chunks == [{"step": 1}]
    assert stub.start_frame is not None
    assert stub.start_frame.start.use_load_balancing is False
    assert stub.start_frame.start.node_id == "node-7"


def test_execute_on_node_uses_direct_target_context() -> None:
    client = DistributedComputingClient("127.0.0.1:8080")
    captured: dict[str, Any] = {}

    def fake_execute_with_context(context: ExecutionContext, *args, **kwargs):
        captured["context"] = context
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(result={"ok": True})

    client.execute_with_context = fake_execute_with_context  # type: ignore[method-assign]

    result = client.execute_on_node("node-42", "take_photo", "x", quality=95)

    assert result == {"ok": True}
    assert captured["context"].strategy == ExecutionStrategy.DIRECT_TARGET
    assert captured["context"].preferred_node_ids == ["node-42"]
    assert captured["context"].enable_caching is False
    assert captured["args"] == ("x",)
    assert captured["kwargs"] == {"quality": 95}


def test_stream_on_node_sets_direct_target_in_stream_start_frame() -> None:
    stub = _FakeStreamStub(
        frames=[
            _chunk_frame("frame-1"),
            _chunk_frame(None, done=True),
        ]
    )
    client = _connected_client(stub)

    chunks = list(client.stream_on_node("node-99", "stream_video", "camera://lobby"))

    assert chunks == ["frame-1"]
    assert stub.start_frame is not None
    assert stub.start_frame.start.use_load_balancing is False
    assert stub.start_frame.start.node_id == "node-99"
    assert stub.start_frame.start.function_name == "stream_video"
