#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quickstart for decorator and OOP templates over MCP/A2A services.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import json

from easyremote import ProtocolService, ProtocolServiceTemplate, agent_capability


service = ProtocolService(name="quick-agent", version="1.0.0")


@service.capability(description="Add two numbers", tags=("math",))
def add_numbers(a: int, b: int) -> int:
    return a + b


class OpsTemplate(ProtocolServiceTemplate):
    @agent_capability(description="Echo incident summary")
    def summarize(self, content: str) -> str:
        return f"[summary] {content}"


async def main() -> None:
    mcp_response = await service.handle_mcp(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "add_numbers", "arguments": {"a": 7, "b": 9}},
        }
    )

    oop_service = OpsTemplate(name="ops-agent", version="1.0.0")
    a2a_response = await oop_service.handle_a2a(
        {
            "jsonrpc": "2.0",
            "id": "task-1",
            "method": "task.execute",
            "params": {"task": {"function": "summarize", "input": ["disk full"]}},
        }
    )

    print("MCP ->")
    print(json.dumps(mcp_response, ensure_ascii=False, indent=2))
    print("\nA2A ->")
    print(json.dumps(a2a_response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
