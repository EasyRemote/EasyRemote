#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Run MCP tool mesh quickstart project.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import json
import sys
from typing import Any
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote.mcp import MCPGateway  # noqa: E402

try:
    from .runtime import McpToolMeshRuntime
except ImportError:
    from runtime import McpToolMeshRuntime


class McpToolMeshDemo:
    """
    Exercises MCP initialize/list/call and batch behavior.
    """

    def __init__(self) -> None:
        self._gateway = MCPGateway(runtime=McpToolMeshRuntime())

    async def run(self) -> None:
        responses: dict[str, Any] = {
            "initialize": await self._gateway.handle_request(
                {"jsonrpc": "2.0", "id": "init-1", "method": "initialize"}
            ),
            "tools_list": await self._gateway.handle_request(
                {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
            ),
            "tools_call": await self._gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {
                        "name": "risk_score",
                        "arguments": {"severity": 4, "impact": 3},
                    },
                }
            ),
            "batch": await self._gateway.handle_request(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": "batch-1",
                        "method": "tools/call",
                        "params": {
                            "name": "echo",
                            "arguments": {"args": ["hello"], "kwargs": {}},
                        },
                    },
                    {"jsonrpc": "2.0", "method": "ping"},
                ]
            ),
        }

        print(json.dumps(responses, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(McpToolMeshDemo().run())
