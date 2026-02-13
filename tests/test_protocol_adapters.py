#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for protocol gateway and built-in MCP/A2A adapters.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio

import pytest

from easyremote.core.utils.exceptions import ProtocolHandlingError
from easyremote.protocols import (
    A2AProtocolAdapter,
    FunctionDescriptor,
    FunctionInvocation,
    MCPProtocolAdapter,
    ProtocolGateway,
    ProtocolRuntime,
)


class FakeRuntime(ProtocolRuntime):
    def __init__(self):
        self.last_invocation = None

    async def list_functions(self):
        return [
            FunctionDescriptor(
                name="add_numbers",
                description="Add two numbers",
                node_ids=["node-1"],
                tags=["math"],
                metadata={"function_type": "synchronous"},
            ),
            FunctionDescriptor(
                name="echo",
                description="Echo text",
                node_ids=["node-2"],
                tags=["utility"],
                metadata={"function_type": "synchronous"},
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation):
        self.last_invocation = invocation
        if invocation.function_name == "add_numbers":
            return invocation.kwargs["a"] + invocation.kwargs["b"]
        if invocation.function_name == "echo":
            return invocation.args[0]
        return {"name": invocation.function_name}


def test_mcp_tools_list():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"},
        )
    )

    assert response["id"] == "list-1"
    assert "result" in response
    assert len(response["result"]["tools"]) == 2
    assert response["result"]["tools"][0]["name"] == "add_numbers"


def test_mcp_tools_call_with_kwargs():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "add_numbers",
                    "arguments": {"a": 2, "b": 3},
                },
            },
        )
    )

    assert response["id"] == "call-1"
    assert response["result"]["content"][0]["json"] == 5
    assert runtime.last_invocation.function_name == "add_numbers"
    assert runtime.last_invocation.kwargs == {"a": 2, "b": 3}


def test_mcp_tools_call_supports_method_alias_and_args_kwargs_envelope():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "id": "call-alias",
                "method": "mcp.tools/call",
                "params": {
                    "name": "echo",
                    "arguments": {"args": ["hello-alias"], "kwargs": {}},
                },
            },
        )
    )

    assert response["id"] == "call-alias"
    assert response["result"]["content"][0]["text"] == "hello-alias"
    assert runtime.last_invocation.args == ("hello-alias",)
    assert runtime.last_invocation.kwargs == {}


def test_a2a_task_execute():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "id": "task-1",
                "method": "task.execute",
                "params": {
                    "task": {
                        "function": "echo",
                        "input": ["hello"],
                        "load_balancing": True,
                    }
                },
            },
        )
    )

    assert response["id"] == "task-1"
    assert response["result"]["task"]["status"] == "completed"
    assert response["result"]["task"]["output"] == "hello"
    assert runtime.last_invocation.load_balancing is True


def test_a2a_task_execute_supports_method_alias():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "id": "task-alias",
                "method": "task/execute",
                "params": {
                    "task": {
                        "function": "echo",
                        "input": ["alias"],
                        "load_balancing": False,
                    }
                },
            },
        )
    )

    assert response["id"] == "task-alias"
    assert response["result"]["task"]["output"] == "alias"


def test_gateway_unknown_protocol():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime)

    with pytest.raises(ProtocolHandlingError):
        asyncio.run(gateway.handle_request("mcp", {"method": "ping"}))


def test_a2a_invalid_task_parameters_returns_invalid_params_error():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "id": "bad-task",
                "method": "task.execute",
                "params": {},
            },
        )
    )

    assert response["id"] == "bad-task"
    assert response["error"]["code"] == -32602


def test_mcp_invalid_jsonrpc_version_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "1.0",
                "id": "bad-version",
                "method": "tools/list",
            },
        )
    )

    assert response["id"] == "bad-version"
    assert response["error"]["code"] == -32600


def test_mcp_missing_jsonrpc_version_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "id": "missing-version",
                "method": "tools/list",
            },
        )
    )

    assert response["id"] == "missing-version"
    assert response["error"]["code"] == -32600
    assert response["error"]["data"]["protocol"] == "mcp"
    assert response["error"]["data"]["method"] is None
    assert response["error"]["data"]["error_type"] == "InvalidRequestError"


def test_mcp_notification_returns_none_response():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "add_numbers",
                    "arguments": {"a": 1, "b": 2},
                },
            },
        )
    )

    assert response is None
    assert runtime.last_invocation.function_name == "add_numbers"


def test_mcp_notification_with_invalid_params_returns_none_response():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {},
            },
        )
    )

    assert response is None


def test_mcp_tools_call_stream_mode_wraps_chunks():
    class StreamRuntime(FakeRuntime):
        async def list_functions(self):
            return [
                FunctionDescriptor(
                    name="stream_values",
                    description="Return iterable chunks",
                    node_ids=["node-stream"],
                )
            ]

        async def execute_invocation(self, invocation: FunctionInvocation):
            return [1, 2, 3]

    runtime = StreamRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "id": "stream-call-1",
                "method": "tools/call",
                "params": {
                    "name": "stream_values",
                    "arguments": {},
                    "stream": True,
                },
            },
        )
    )

    payload = response["result"]["content"][0]["json"]
    assert payload["mode"] == "stream"
    assert payload["chunkCount"] == 3
    assert payload["chunks"] == [1, 2, 3]


def test_a2a_task_execute_stream_mode_wraps_chunks():
    class StreamRuntime(FakeRuntime):
        async def list_functions(self):
            return [
                FunctionDescriptor(
                    name="stream_values",
                    description="Return iterable chunks",
                    node_ids=["node-stream"],
                )
            ]

        async def execute_invocation(self, invocation: FunctionInvocation):
            return ["a", "b"]

    runtime = StreamRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "id": "stream-task-1",
                "method": "task.execute",
                "params": {
                    "task": {
                        "function": "stream_values",
                        "input": {},
                        "stream": True,
                    }
                },
            },
        )
    )

    output = response["result"]["task"]["output"]
    assert output["mode"] == "stream"
    assert output["chunkCount"] == 2
    assert output["chunks"] == ["a", "b"]


def test_mcp_batch_mixed_request_and_notification():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            [
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "add_numbers", "arguments": {"a": 4, "b": 5}},
                },
                {
                    "jsonrpc": "2.0",
                    "method": "ping",
                },
                {
                    "jsonrpc": "2.0",
                    "id": "unknown-1",
                    "method": "tools/unknown",
                },
            ],
        )
    )

    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0]["id"] == "call-1"
    assert response[1]["id"] == "unknown-1"
    assert response[1]["error"]["code"] == -32601


def test_mcp_batch_notifications_only_returns_none():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            [
                {"jsonrpc": "2.0", "method": "ping"},
                {"jsonrpc": "2.0", "method": "tools/list"},
            ],
        )
    )

    assert response is None


def test_mcp_batch_empty_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(gateway.handle_request("mcp", []))

    assert response["error"]["code"] == -32600
    assert response["id"] is None


def test_mcp_batch_with_invalid_item_returns_invalid_request_entry():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "mcp",
            [
                "not-an-object",
                {"jsonrpc": "2.0", "id": "ok-list", "method": "tools/list"},
            ],
        )
    )

    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0]["id"] is None
    assert response[0]["error"]["code"] == -32600
    assert response[0]["error"]["data"]["protocol"] == "mcp"
    assert response[1]["id"] == "ok-list"


def test_a2a_batch_mixed_request_and_notification():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            [
                {
                    "jsonrpc": "2.0",
                    "id": "task-batch-1",
                    "method": "task.execute",
                    "params": {"task": {"function": "echo", "input": ["batch-a2a"]}},
                },
                {
                    "jsonrpc": "2.0",
                    "method": "task.send",
                    "params": {"task": {"function": "echo", "input": ["notify-only"]}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": "task-batch-err",
                    "method": "unknown.method",
                },
            ],
        )
    )

    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0]["id"] == "task-batch-1"
    assert response[0]["result"]["task"]["output"] == "batch-a2a"
    assert response[1]["id"] == "task-batch-err"
    assert response[1]["error"]["code"] == -32601


def test_a2a_batch_notifications_only_returns_none():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            [
                {"jsonrpc": "2.0", "method": "ping"},
                {
                    "jsonrpc": "2.0",
                    "method": "task.send",
                    "params": {"task": {"function": "echo", "input": ["only-notify"]}},
                },
            ],
        )
    )

    assert response is None


def test_a2a_batch_empty_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(gateway.handle_request("a2a", []))

    assert response["error"]["code"] == -32600
    assert response["id"] is None


def test_a2a_missing_jsonrpc_version_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "id": "a2a-missing-version",
                "method": "agent.capabilities",
            },
        )
    )

    assert response["id"] == "a2a-missing-version"
    assert response["error"]["code"] == -32600
    assert response["error"]["data"]["protocol"] == "a2a"
    assert response["error"]["data"]["method"] is None
    assert response["error"]["data"]["error_type"] == "InvalidRequestError"


def test_a2a_non_object_payload_returns_invalid_request():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            "invalid-payload",
        )
    )

    assert response["id"] is None
    assert response["error"]["code"] == -32600


def test_a2a_notification_returns_none_response():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "method": "task.execute",
                "params": {
                    "task": {"function": "echo", "input": ["notify"]},
                },
            },
        )
    )

    assert response is None
    assert runtime.last_invocation.function_name == "echo"


def test_a2a_notification_with_invalid_params_returns_none_response():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "method": "task.execute",
                "params": {},
            },
        )
    )

    assert response is None


def test_a2a_batch_with_invalid_item_returns_invalid_request_entry():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    response = asyncio.run(
        gateway.handle_request(
            "a2a",
            [
                1001,
                {
                    "jsonrpc": "2.0",
                    "id": "a2a-capabilities",
                    "method": "agent.capabilities",
                },
            ],
        )
    )

    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0]["id"] is None
    assert response[0]["error"]["code"] == -32600
    assert response[0]["error"]["data"]["protocol"] == "a2a"
    assert response[1]["id"] == "a2a-capabilities"


def test_error_object_has_consistent_data_shape_across_protocols():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(
        runtime=runtime,
        adapters=(MCPProtocolAdapter(), A2AProtocolAdapter()),
    )

    mcp_response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {"jsonrpc": "2.0", "id": "mcp-err", "method": "unknown.method"},
        )
    )
    a2a_response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {"jsonrpc": "2.0", "id": "a2a-err", "method": "unknown.method"},
        )
    )

    for response, protocol in ((mcp_response, "mcp"), (a2a_response, "a2a")):
        assert response["error"]["code"] == -32601
        assert isinstance(response["error"]["message"], str)
        assert response["error"]["message"]
        assert response["error"]["data"]["protocol"] == protocol
        assert response["error"]["data"]["method"] == "unknown.method"
        assert "error_type" in response["error"]["data"]


def test_invalid_params_error_object_details_are_consistent():
    runtime = FakeRuntime()
    gateway = ProtocolGateway(
        runtime=runtime,
        adapters=(MCPProtocolAdapter(), A2AProtocolAdapter()),
    )

    mcp_response = asyncio.run(
        gateway.handle_request(
            "mcp",
            {
                "jsonrpc": "2.0",
                "id": "mcp-invalid-params",
                "method": "tools/call",
                "params": {},
            },
        )
    )
    a2a_response = asyncio.run(
        gateway.handle_request(
            "a2a",
            {
                "jsonrpc": "2.0",
                "id": "a2a-invalid-params",
                "method": "task.execute",
                "params": {},
            },
        )
    )

    for response, protocol, method in (
        (mcp_response, "mcp", "tools/call"),
        (a2a_response, "a2a", "task.execute"),
    ):
        assert response["error"]["code"] == -32602
        assert response["error"]["data"]["protocol"] == protocol
        assert response["error"]["data"]["method"] == method
        assert response["error"]["data"]["error_type"] == "InvalidParamsError"
