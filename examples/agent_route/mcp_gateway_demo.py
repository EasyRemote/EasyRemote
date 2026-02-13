#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP route demo with JSON-RPC requests against EasyRemote protocol gateway.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import json
from typing import Any, Dict, List

from easyremote.mcp import MCPGateway
from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class DemoRuntime(ProtocolRuntime):
    """
    In-memory runtime used to demonstrate MCP protocol behavior.
    """

    def __init__(self) -> None:
        self._tool_impl: Dict[str, Any] = {
            "add_numbers": lambda a, b: a + b,
            "echo": lambda value: value,
        }

    async def list_functions(self) -> List[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="add_numbers",
                description="Add two integers.",
                node_ids=["math-node"],
                tags=["math"],
            ),
            FunctionDescriptor(
                name="echo",
                description="Echo input.",
                node_ids=["utility-node"],
                tags=["utility"],
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        implementation = self._tool_impl.get(invocation.function_name)
        if implementation is None:
            raise ValueError(f"Unknown tool: {invocation.function_name}")

        if invocation.kwargs:
            return implementation(**invocation.kwargs)
        return implementation(*invocation.args)


class MCPRouteDemo:
    """
    Demonstrates initialize, tools/list, tools/call, notification and batch requests.
    """

    def __init__(self) -> None:
        self._gateway = MCPGateway(runtime=DemoRuntime())

    async def run(self) -> None:
        initialize_response = await self._gateway.handle_request(
            {"jsonrpc": "2.0", "id": "init-1", "method": "initialize"}
        )
        tools_response = await self._gateway.handle_request(
            {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
        )
        call_response = await self._gateway.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "add_numbers",
                    "arguments": {"a": 8, "b": 13},
                },
            }
        )
        batch_response = await self._gateway.handle_request(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "batch-1",
                    "method": "tools/call",
                    "params": {
                        "name": "echo",
                        "arguments": {"args": ["hello-mcp"], "kwargs": {}},
                    },
                },
                {"jsonrpc": "2.0", "method": "ping"},
                {"jsonrpc": "2.0", "id": "batch-err", "method": "unknown/method"},
            ]
        )

        print("initialize =>")
        print(json.dumps(initialize_response, ensure_ascii=False, indent=2))
        print("\ntools/list =>")
        print(json.dumps(tools_response, ensure_ascii=False, indent=2))
        print("\ntools/call =>")
        print(json.dumps(call_response, ensure_ascii=False, indent=2))
        print("\nbatch =>")
        print(json.dumps(batch_response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(MCPRouteDemo().run())
