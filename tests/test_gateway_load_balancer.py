#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for gateway load balancer stability and strategy behavior.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
from types import SimpleNamespace

from easyremote.core.balancing import LoadBalancer, RequestContext
from easyremote.core.data import NodeInfo


def _node_with_metrics(node_id: str, cpu: float, memory: float) -> NodeInfo:
    node = NodeInfo(node_id=node_id)
    node.health_metrics.update_metrics(cpu_usage=cpu, memory_usage=memory)
    return node


def test_load_balancer_resource_aware_prefers_lower_load_node():
    gateway = SimpleNamespace(
        _nodes={
            "node-a": _node_with_metrics("node-a", cpu=85.0, memory=80.0),
            "node-b": _node_with_metrics("node-b", cpu=25.0, memory=30.0),
        }
    )

    balancer = LoadBalancer(gateway)
    ctx = RequestContext(function_name="predict")

    selected = balancer.select_node("predict", ctx, ["node-a", "node-b"])

    assert selected == "node-b"


def test_load_balancer_honors_round_robin_override_from_request_requirements():
    gateway = SimpleNamespace(_nodes={})
    balancer = LoadBalancer(gateway)

    ctx = RequestContext(
        function_name="transcode",
        requirements={"load_balancing_strategy": "round_robin"},
    )

    first = balancer.select_node("transcode", ctx, ["node-1", "node-2"])
    second = balancer.select_node("transcode", ctx, ["node-1", "node-2"])

    assert first == "node-1"
    assert second == "node-2"


def test_route_request_discovers_function_providers_from_gateway_registry():
    node = _node_with_metrics("node-a", cpu=40.0, memory=40.0)
    node.functions["embed"] = object()

    gateway = SimpleNamespace(_nodes={"node-a": node})
    balancer = LoadBalancer(gateway)

    ctx = RequestContext(function_name="embed")

    selected = asyncio.run(balancer.route_request("embed", ctx))

    assert selected == "node-a"
