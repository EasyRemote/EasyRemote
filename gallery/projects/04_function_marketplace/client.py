#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Human route client for function marketplace.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import remote  # noqa: E402

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8082")


@remote(
    function_name="calculate_margin",
    node_id="finance-node",
    gateway_address=GATEWAY_ADDRESS,
)
def calculate_margin(revenue: float, cost: float) -> dict[str, float]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    margin = revenue - cost
    margin_rate = (margin / revenue) if revenue else 0.0
    return {
        "margin": round(margin, 4),
        "margin_rate": round(margin_rate, 6),
    }


@remote(
    function_name="estimate_incident_cost",
    node_id="ops-node",
    gateway_address=GATEWAY_ADDRESS,
)
def estimate_incident_cost(minutes: int, affected_users: int) -> dict[str, object]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return {
        "estimated_cost": round(minutes * affected_users * 0.15, 4),
        "formula": "minutes * affected_users * 0.15",
    }


@remote(
    function_name="public_lookup",
    load_balancing={"strategy": "resource_aware"},
    gateway_address=GATEWAY_ADDRESS,
)
def public_lookup(query: str) -> dict[str, str]:
    # Local fallback for static analysis/debugging; @remote wrapper executes remotely.
    return {
        "source": "local-fallback",
        "query": query,
        "summary": f"local interpretation for '{query}'",
    }


class MarketplaceClientDemo:
    """
    Demonstrates marketplace calls from human coding route.
    """

    def run(self) -> None:
        finance = calculate_margin(120000.0, 86000.0)
        ops = estimate_incident_cost(42, 1800)
        shared = public_lookup("error budget strategy")

        print(f"calculate_margin => {finance}")
        print(f"estimate_incident_cost => {ops}")
        print(f"public_lookup(load_balanced) => {shared}")


if __name__ == "__main__":
    MarketplaceClientDemo().run()
