#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent route demo for function marketplace (MCP + A2A).

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote.a2a import A2AGateway  # noqa: E402
from easyremote.mcp import MCPGateway  # noqa: E402

from runtime import MarketplaceProtocolRuntime  # noqa: E402


class AgentCatalogDemo:
    """
    Shows catalog discovery and execution in both MCP and A2A views.
    """

    def __init__(self) -> None:
        runtime = MarketplaceProtocolRuntime()
        self._mcp_gateway = MCPGateway(runtime=runtime)
        self._a2a_gateway = A2AGateway(runtime=runtime)

    async def run(self) -> None:
        responses: dict[str, Any] = {
            "mcp_tools_list": await self._mcp_gateway.handle_request(
                {"jsonrpc": "2.0", "id": "mcp-list", "method": "tools/list"}
            ),
            "mcp_tools_call": await self._mcp_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "mcp-call",
                    "method": "tools/call",
                    "params": {
                        "name": "calculate_margin",
                        "arguments": {"revenue": 10000, "cost": 7600},
                    },
                }
            ),
            "a2a_capabilities": await self._a2a_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "a2a-cap",
                    "method": "agent.capabilities",
                }
            ),
            "a2a_task_execute": await self._a2a_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "a2a-task",
                    "method": "task.execute",
                    "params": {
                        "task": {
                            "function": "public_lookup",
                            "input": {"query": "marketplace governance"},
                        }
                    },
                }
            ),
        }
        print(json.dumps(responses, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(AgentCatalogDemo().run())
