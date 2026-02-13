#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Runtime model for A2A incident copilot quickstart.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any

from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class A2AIncidentRuntime(ProtocolRuntime):
    """
    In-memory runtime exposing incident-handling capabilities.
    """

    async def list_functions(self) -> list[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="summarize_alert",
                description="Build a one-line alert summary",
                node_ids=["incident-agent-a"],
                tags=["incident", "summary"],
            ),
            FunctionDescriptor(
                name="propose_action",
                description="Return first-action recommendation",
                node_ids=["incident-agent-b"],
                tags=["incident", "action"],
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        if invocation.function_name == "summarize_alert":
            service = str(invocation.kwargs.get("service", "unknown"))
            error_rate = float(invocation.kwargs.get("error_rate", 0.0))
            return f"{service} error_rate={error_rate:.2f}%"

        if invocation.function_name == "propose_action":
            severity = str(invocation.kwargs.get("severity", "low"))
            if severity in {"critical", "high"}:
                return "Page on-call and start rollback procedure"
            return "Create ticket and monitor for 15 minutes"

        raise ValueError(f"Unknown A2A function: {invocation.function_name}")
