#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Runtime model for MCP tool mesh quickstart.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any

from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class McpToolMeshRuntime(ProtocolRuntime):
    """
    In-memory runtime exposing business tools for MCP requests.
    """

    async def list_functions(self) -> list[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="risk_score",
                description="Score a ticket risk based on severity and impact",
                node_ids=["risk-node"],
                tags=["risk", "ops"],
            ),
            FunctionDescriptor(
                name="echo",
                description="Echo plain text",
                node_ids=["utility-node"],
                tags=["utility"],
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        if invocation.function_name == "risk_score":
            severity = int(invocation.kwargs.get("severity", 1))
            impact = int(invocation.kwargs.get("impact", 1))
            return {"score": severity * impact, "policy": "severity*impact"}

        if invocation.function_name == "echo":
            return invocation.args[0] if invocation.args else ""

        raise ValueError(f"Unknown MCP tool: {invocation.function_name}")
