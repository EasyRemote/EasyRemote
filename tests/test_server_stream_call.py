#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for gateway bidirectional StreamCall RPC handler.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio

from easyremote.core.nodes.server import Server
from easyremote.core.protos import service_pb2


def test_stream_call_start_yields_chunk_frames_and_done():
    server = Server(port=18080)

    async def fake_stream_function(node_id, function_name, *args, **kwargs):
        assert function_name == "stream_values"
        assert args == ("payload",)
        yield "a"
        yield "b"

    server.stream_function = fake_stream_function  # type: ignore[method-assign]

    async def request_iter():
        frame = service_pb2.StreamCallFrame()
        frame.start.call_id = "call-1"
        frame.start.function_name = "stream_values"
        frame.start.use_load_balancing = False
        args_bytes, kwargs_bytes = server._serializer.serialize_args("payload")
        frame.start.args = args_bytes
        frame.start.kwargs = kwargs_bytes
        yield frame

    async def run_case():
        responses = []
        async for response in server.StreamCall(request_iter(), context=None):
            responses.append(response)

        assert len(responses) == 3
        assert all(resp.HasField("exec_res") for resp in responses)
        assert responses[-1].exec_res.is_done is True
        chunks = [
            server._serializer.deserialize_result(resp.exec_res.chunk)
            for resp in responses[:-1]
        ]
        assert chunks == ["a", "b"]

    asyncio.run(run_case())


def test_stream_call_reports_error_frame_on_stream_failure():
    server = Server(port=18081)

    async def failing_stream_function(node_id, function_name, *args, **kwargs):
        raise RuntimeError("stream exploded")
        yield "never"

    server.stream_function = failing_stream_function  # type: ignore[method-assign]

    async def request_iter():
        frame = service_pb2.StreamCallFrame()
        frame.start.call_id = "call-2"
        frame.start.function_name = "stream_values"
        frame.start.use_load_balancing = False
        args_bytes, kwargs_bytes = server._serializer.serialize_args("payload")
        frame.start.args = args_bytes
        frame.start.kwargs = kwargs_bytes
        yield frame

    async def run_case():
        responses = []
        async for response in server.StreamCall(request_iter(), context=None):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].HasField("error")
        assert "stream exploded" in responses[0].error.message

    asyncio.run(run_case())


def test_register_node_does_not_replace_existing_control_queue_on_reregistration():
    server = Server(port=18082)
    existing_queue = asyncio.Queue()
    server._node_communication_queues["node-1"] = existing_queue

    request = service_pb2.NodeInfo()
    request.node_id = "node-1"
    request.status = "connected"
    request.version = "1.0.0"
    func = request.functions.add()
    func.name = "foo"
    func.is_async = False
    func.is_generator = False

    async def run_case():
        response = await server.RegisterNode(request, context=None)
        assert response.success is True
        assert server._node_communication_queues["node-1"] is existing_queue

    asyncio.run(run_case())
