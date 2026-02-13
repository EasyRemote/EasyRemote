#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from easyremote.core.balancing.simple_balancer import (
    BalancingStrategy,
    NodeSelectionStrategy,
    SimpleLoadBalancer,
    SimpleNodeStats,
)
from easyremote.core.utils.exceptions import NoAvailableNodesError


def test_round_robin_selection_is_stable():
    balancer = SimpleLoadBalancer(BalancingStrategy.ROUND_ROBIN)
    nodes = ["n1", "n2", "n3"]

    picks = [balancer.select_node(nodes) for _ in range(4)]

    assert picks == ["n1", "n2", "n3", "n1"]


def test_resource_aware_prefers_lower_load_node():
    balancer = SimpleLoadBalancer(BalancingStrategy.RESOURCE_AWARE)
    nodes = ["slow", "fast"]
    stats = {
        "slow": SimpleNodeStats(
            node_id="slow",
            cpu_usage=90,
            memory_usage=92,
            active_tasks=10,
            response_time_ms=950,
        ),
        "fast": SimpleNodeStats(
            node_id="fast",
            cpu_usage=25,
            memory_usage=20,
            active_tasks=1,
            response_time_ms=40,
        ),
    }

    assert balancer.select_node(nodes, stats) == "fast"


class _PreferLastNodeStrategy(NodeSelectionStrategy):
    def select_node(self, available_nodes, node_stats):
        return available_nodes[-1]


def test_custom_strategy_can_be_registered_and_used():
    balancer = SimpleLoadBalancer(BalancingStrategy.ROUND_ROBIN)
    balancer.register_strategy(BalancingStrategy.ROUND_ROBIN, _PreferLastNodeStrategy())
    balancer.set_strategy(BalancingStrategy.ROUND_ROBIN)

    assert balancer.select_node(["a", "b", "c"]) == "c"


def test_select_node_empty_candidates_raises_layered_error():
    balancer = SimpleLoadBalancer(BalancingStrategy.ROUND_ROBIN)

    with pytest.raises(NoAvailableNodesError):
        balancer.select_node([])
