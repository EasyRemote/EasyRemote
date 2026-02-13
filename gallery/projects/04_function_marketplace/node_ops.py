#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ops domain node for function marketplace.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode  # noqa: E402


class OpsDomainNode:
    """
    Provides ops-oriented reusable functions.
    """

    def __init__(self, gateway_address: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id="ops-node")
        self._register_functions()

    def _register_functions(self) -> None:
        @self._node.register(
            name="estimate_incident_cost",
            description="Estimate incident cost by minutes and users affected",
            tags={"ops", "marketplace"},
        )
        def estimate_incident_cost(
            minutes: int, affected_users: int
        ) -> dict[str, object]:
            cost = minutes * affected_users * 0.15
            return {
                "estimated_cost": round(cost, 4),
                "formula": "minutes * affected_users * 0.15",
            }

        @self._node.register(
            name="public_lookup",
            description="Marketplace generic lookup from ops node",
            load_balancing=True,
            tags={"shared", "marketplace"},
        )
        def public_lookup(query: str) -> dict[str, str]:
            return {
                "source": "ops-node",
                "query": query,
                "summary": f"ops interpretation for '{query}'",
            }

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8082")
    OpsDomainNode(gateway_address=gateway_address).serve()
