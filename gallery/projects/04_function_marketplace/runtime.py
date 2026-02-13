#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent protocol runtime for function marketplace.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any

from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class MarketplaceProtocolRuntime(ProtocolRuntime):
    """
    In-memory catalog runtime for protocol demos.
    """

    async def list_functions(self) -> list[FunctionDescriptor]:
        return [
            FunctionDescriptor(
                name="calculate_margin",
                description="Calculate gross margin rate",
                node_ids=["finance-node"],
                tags=["finance", "marketplace"],
                metadata={"domain": "finance"},
            ),
            FunctionDescriptor(
                name="estimate_incident_cost",
                description="Estimate incident cost",
                node_ids=["ops-node"],
                tags=["ops", "marketplace"],
                metadata={"domain": "ops"},
            ),
            FunctionDescriptor(
                name="public_lookup",
                description="Shared marketplace lookup",
                node_ids=["finance-node", "ops-node"],
                tags=["shared", "marketplace"],
                metadata={"domain": "shared"},
            ),
        ]

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        if invocation.function_name == "calculate_margin":
            revenue = float(invocation.kwargs["revenue"])
            cost = float(invocation.kwargs["cost"])
            margin = revenue - cost
            return {
                "margin": round(margin, 4),
                "margin_rate": round((margin / revenue) if revenue else 0.0, 6),
            }

        if invocation.function_name == "estimate_incident_cost":
            minutes = int(invocation.kwargs["minutes"])
            users = int(invocation.kwargs["affected_users"])
            return {
                "estimated_cost": round(minutes * users * 0.15, 4),
            }

        if invocation.function_name == "public_lookup":
            query = str(invocation.kwargs.get("query", ""))
            return {
                "query": query,
                "catalog": ["finance-node", "ops-node"],
            }

        raise ValueError(f"Unknown marketplace function: {invocation.function_name}")
