#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for high-level MCP/A2A service templates.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio

from easyremote.protocols import (
    A2AService,
    MCPService,
    ProtocolService,
    ProtocolServiceTemplate,
    agent_capability,
)


def test_protocol_service_decorator_registration_reduces_runtime_boilerplate():
    service = ProtocolService(name="demo-agent", version="1.2.3")

    @service.capability(description="Add two integers", tags=("math",))
    def add_numbers(a, b):
        return a + b

    list_response = asyncio.run(
        service.handle_mcp(
            {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
        )
    )
    call_response = asyncio.run(
        service.handle_mcp(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {"name": "add_numbers", "arguments": {"a": 2, "b": 4}},
            }
        )
    )
    init_response = asyncio.run(
        service.handle_mcp({"jsonrpc": "2.0", "id": "init-1", "method": "initialize"})
    )

    tools = list_response["result"]["tools"]
    assert tools[0]["name"] == "add_numbers"
    assert tools[0]["annotations"]["tags"] == ["math"]
    assert call_response["result"]["content"][0]["json"] == 6
    assert init_response["result"]["serverInfo"]["name"] == "demo-agent"
    assert init_response["result"]["serverInfo"]["version"] == "1.2.3"


class DemoTemplate(ProtocolServiceTemplate):
    @agent_capability(description="Echo payload")
    def echo(self, value):
        return value

    @agent_capability(name="chunk_stream", description="Yield stream chunks")
    async def stream_chunks(self, prefix):
        for idx in range(3):
            yield f"{prefix}-{idx}"


def test_protocol_service_template_auto_registers_oop_methods():
    service = DemoTemplate(name="template-agent")

    a2a_response = asyncio.run(
        service.handle_a2a(
            {
                "jsonrpc": "2.0",
                "id": "task-1",
                "method": "task.execute",
                "params": {"task": {"function": "echo", "input": ["hello"]}},
            }
        )
    )
    stream_response = asyncio.run(
        service.handle_mcp(
            {
                "jsonrpc": "2.0",
                "id": "stream-1",
                "method": "tools/call",
                "params": {
                    "name": "chunk_stream",
                    "arguments": ["item"],
                    "stream": True,
                },
            }
        )
    )

    assert a2a_response["result"]["task"]["output"] == "hello"
    payload = stream_response["result"]["content"][0]["json"]
    assert payload["mode"] == "stream"
    assert payload["chunkCount"] == 3
    assert payload["chunks"] == ["item-0", "item-1", "item-2"]


def test_single_protocol_service_helpers_limit_supported_protocols():
    mcp_service = MCPService(name="mcp-only")
    a2a_service = A2AService(name="a2a-only")

    assert mcp_service.supported_protocols() == ["mcp"]
    assert a2a_service.supported_protocols() == ["a2a"]
