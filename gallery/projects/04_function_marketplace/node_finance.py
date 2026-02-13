#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Finance domain node for function marketplace.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import ComputeNode  # noqa: E402


class FinanceDomainNode:
    """
    Provides finance-oriented reusable functions.
    """

    def __init__(self, gateway_address: str) -> None:
        self._node = ComputeNode(gateway_address=gateway_address, node_id="finance-node")
        self._register_functions()

    def _register_functions(self) -> None:
        @self._node.register(
            name="calculate_margin",
            description="Calculate gross margin rate",
            tags={"finance", "marketplace"},
        )
        def calculate_margin(revenue: float, cost: float) -> dict[str, float]:
            margin = revenue - cost
            margin_rate = (margin / revenue) if revenue else 0.0
            return {
                "margin": round(margin, 4),
                "margin_rate": round(margin_rate, 6),
            }

        @self._node.register(
            name="public_lookup",
            description="Marketplace generic lookup from finance node",
            load_balancing=True,
            tags={"shared", "marketplace"},
        )
        def public_lookup(query: str) -> dict[str, str]:
            return {
                "source": "finance-node",
                "query": query,
                "summary": f"finance interpretation for '{query}'",
            }

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    gateway_address = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8082")
    FinanceDomainNode(gateway_address=gateway_address).serve()
