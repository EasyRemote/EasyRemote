#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Run A2A incident copilot quickstart project.

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

from easyremote.a2a import A2AGateway  # noqa: E402

try:
    from .runtime import A2AIncidentRuntime
except ImportError:
    from runtime import A2AIncidentRuntime


class A2AIncidentDemo:
    """
    Exercises A2A capabilities and task execution behavior.
    """

    def __init__(self) -> None:
        self._gateway = A2AGateway(runtime=A2AIncidentRuntime())

    async def run(self) -> None:
        responses: dict[str, Any] = {
            "capabilities": await self._gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "cap-1",
                    "method": "agent.capabilities",
                }
            ),
            "task_execute": await self._gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": "task-1",
                    "method": "task.execute",
                    "params": {
                        "task": {
                            "id": "incident-001",
                            "function": "propose_action",
                            "input": {"severity": "critical"},
                        }
                    },
                }
            ),
            "notification": await self._gateway.handle_request(
                {
                    "jsonrpc": "2.0",
                    "method": "task.send",
                    "params": {
                        "task": {
                            "function": "summarize_alert",
                            "input": {"service": "checkout", "error_rate": 7.2},
                        }
                    },
                }
            ),
            "batch": await self._gateway.handle_request(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": "batch-1",
                        "method": "task.execute",
                        "params": {
                            "task": {
                                "function": "summarize_alert",
                                "input": {
                                    "service": "payments",
                                    "error_rate": 2.1,
                                },
                            }
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "method": "task.send",
                        "params": {
                            "task": {
                                "function": "propose_action",
                                "input": {"severity": "low"},
                            }
                        },
                    },
                ]
            ),
        }

        print(json.dumps(responses, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(A2AIncidentDemo().run())
