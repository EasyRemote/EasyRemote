#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP/A2A proxy demo backed by a real EasyRemote gateway.

This shows the "agent-side" usage pattern:
1) Run an EasyRemote gateway + at least one node.
2) Use EasyRemoteClientRuntime to expose gateway functions as MCP/A2A calls.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import asyncio
import json
import os

from easyremote import EasyRemoteClientRuntime
from easyremote.a2a import A2AGateway
from easyremote.mcp import MCPGateway


async def main() -> None:
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8080")
    runtime = EasyRemoteClientRuntime(gateway_address)

    mcp = MCPGateway(runtime=runtime)
    a2a = A2AGateway(runtime=runtime)

    # MCP: tools/list -> lists real gateway functions (aggregated across nodes).
    tools_response = await mcp.handle_request(
        {"jsonrpc": "2.0", "id": "tools-1", "method": "tools/list"}
    )
    print("MCP tools/list =>")
    print(json.dumps(tools_response, ensure_ascii=False, indent=2))

    # A2A: agent.capabilities -> same function surface, different envelope.
    caps_response = await a2a.handle_request(
        {"jsonrpc": "2.0", "id": "caps-1", "method": "agent.capabilities"}
    )
    print("\nA2A agent.capabilities =>")
    print(json.dumps(caps_response, ensure_ascii=False, indent=2))

    # Example call (requires a running user device node with CMP endpoints):
    #
    # node_id = "user-device-demo-user"
    # res = await mcp.handle_request(
    #     {
    #         "jsonrpc": "2.0",
    #         "id": "call-1",
    #         "method": "tools/call",
    #         "params": {
    #             "name": "device.list_node_functions",
    #             "node_id": node_id,
    #             "arguments": {},
    #         },
    #     }
    # )
    # print("\nMCP tools/call device.list_node_functions =>")
    # print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

