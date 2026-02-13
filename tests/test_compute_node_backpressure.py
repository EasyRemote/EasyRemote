#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for compute node backpressure safeguards.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio

from easyremote.core.nodes.compute_node import ComputeNode, NodeConfiguration
from easyremote.core.protos import service_pb2


def _build_test_node() -> ComputeNode:
    config = NodeConfiguration(
        gateway_address="127.0.0.1:8080",
        node_id="test-node",
        queue_size_limit=1,
        max_concurrent_executions=1,
    )
    return ComputeNode(
        gateway_address=config.gateway_address,
        node_id=config.node_id,
        config=config,
    )


def test_exec_request_queue_full_emits_overload_response():
    node = _build_test_node()

    async def run_case():
        # Fill execution queue to trigger overload path.
        await node._execution_queue.put(service_pb2.ExecutionRequest(call_id="existing"))

        control_msg = service_pb2.ControlMessage()
        control_msg.exec_req.call_id = "call-overload"
        control_msg.exec_req.function_name = "heavy_job"

        await node._handle_control_message(control_msg)

        response_control = await asyncio.wait_for(node._outgoing_messages.get(), timeout=1.0)
        assert response_control.HasField("exec_res")
        assert response_control.exec_res.call_id == "call-overload"
        assert response_control.exec_res.has_error is True
        assert "queue is full" in response_control.exec_res.error_message.lower()

    asyncio.run(run_case())
