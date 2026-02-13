#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent route protocol demo for local data residency AI project.

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

from runtime import LocalResidencyProtocolRuntime  # noqa: E402


class LocalResidencyProtocolDemo:
    """
    Shows privacy-safe outputs through both MCP and A2A calls.
    """

    def __init__(self) -> None:
        runtime = LocalResidencyProtocolRuntime()
        self._mcp_gateway = MCPGateway(runtime=runtime)
        self._a2a_gateway = A2AGateway(runtime=runtime)

    async def run(self) -> None:
        sample_record = {
            "patient_id": "P-2026-ALPHA",
            "email": "bob@example.com",
            "phone": "+1-202-555-0130",
            "diagnosis_code": "DX-88",
        }

        responses: dict[str, Any] = {
            "mcp_sanitize": await self._mcp_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "mcp-sanitize",
                    "method": "tools/call",
                    "params": {
                        "name": "sanitize_claim_record",
                        "arguments": {"record": sample_record},
                    },
                }
            ),
            "mcp_risk": await self._mcp_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "mcp-risk",
                    "method": "tools/call",
                    "params": {
                        "name": "assess_claim_risk",
                        "arguments": {"amount": 23000.0, "anomaly_count": 4},
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
            "a2a_task": await self._a2a_gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "a2a-task",
                    "method": "task.execute",
                    "params": {
                        "task": {
                            "function": "assess_claim_risk",
                            "input": {"amount": 23000.0, "anomaly_count": 4},
                        }
                    },
                }
            ),
        }
        print(json.dumps(responses, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(LocalResidencyProtocolDemo().run())
