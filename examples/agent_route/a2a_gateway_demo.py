#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A2A route demo with JSON-RPC requests against EasyRemote protocol gateway.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import json
from typing import Any, Dict, List

from easyremote.a2a import A2AGateway
from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class DemoRuntime(ProtocolRuntime):
    """
    In-memory runtime used to demonstrate A2A protocol behavior.
    """

    def __init__(self) -> None:
        self._task_impl: Dict[str, Any] = {
            "echo": lambda payload: payload,
            "sum_numbers": lambda a, b: a + b,
        }

    async def list_functions(self) -> List[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="echo",
                description="Echo task payload.",
                node_ids=["agent-node-a"],
                tags=["utility"],
            ),
            FunctionDescriptor(
                name="sum_numbers",
                description="Add two numbers.",
                node_ids=["agent-node-b"],
                tags=["math"],
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        implementation = self._task_impl.get(invocation.function_name)
        if implementation is None:
            raise ValueError(f"Unknown task function: {invocation.function_name}")

        if invocation.kwargs:
            return implementation(**invocation.kwargs)
        return implementation(*invocation.args)


class A2ARouteDemo:
    """
    Demonstrates capabilities, task execution, notification and error responses.
    """

    def __init__(self) -> None:
        self._gateway = A2AGateway(runtime=DemoRuntime())

    async def run(self) -> None:
        capabilities_response = await self._gateway.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "cap-1",
                "method": "agent.capabilities",
            }
        )
        task_response = await self._gateway.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "task-1",
                "method": "task.execute",
                "params": {
                    "task": {
                        "id": "task-001",
                        "function": "sum_numbers",
                        "input": {"a": 5, "b": 9},
                    }
                },
            }
        )
        notification_response = await self._gateway.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "task.send",
                "params": {
                    "task": {
                        "function": "echo",
                        "input": ["notification-only"],
                    }
                },
            }
        )
        batch_response = await self._gateway.handle_request(
            [
                {
                    "jsonrpc": "2.0",
                    "id": "task-batch-1",
                    "method": "task.execute",
                    "params": {
                        "task": {
                            "function": "echo",
                            "input": ["batch-a2a"],
                        }
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "task.send",
                    "params": {
                        "task": {
                            "function": "echo",
                            "input": ["notify-batch-only"],
                        }
                    },
                },
            ]
        )
        error_response = await self._gateway.handle_request(
            {"jsonrpc": "2.0", "id": "err-1", "method": "task.execute", "params": {}}
        )

        print("agent.capabilities =>")
        print(json.dumps(capabilities_response, ensure_ascii=False, indent=2))
        print("\ntask.execute =>")
        print(json.dumps(task_response, ensure_ascii=False, indent=2))
        print("\nnotification(task.send) =>")
        print(notification_response)
        print("\nbatch(task.execute + task.send notification) =>")
        print(json.dumps(batch_response, ensure_ascii=False, indent=2))
        print("\nerror(task.execute invalid params) =>")
        print(json.dumps(error_response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(A2ARouteDemo().run())
