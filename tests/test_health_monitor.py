#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for deterministic node health monitoring behavior."""

import asyncio
from types import SimpleNamespace

from easyremote.core.balancing.health_monitor import (
    NodeHealthLevel,
    NodeHealthMonitor,
    NodeHealthStatus,
)
from easyremote.core.data import NodeInfo, NodeStatus


def _build_gateway_with_node(node_id: str, *, alive: bool = True) -> SimpleNamespace:
    node = NodeInfo(node_id=node_id)
    if not alive:
        node.status = NodeStatus.DISCONNECTED
    return SimpleNamespace(_nodes={node_id: node})


def test_health_monitor_uses_gateway_metrics_without_random_simulation():
    gateway = _build_gateway_with_node("node-a")
    node = gateway._nodes["node-a"]

    node.health_metrics.update_metrics(cpu_usage=35.0, memory_usage=45.0, gpu_usage=25.0)
    node.health_metrics.network_latency_ms = 120.0
    node.health_metrics.concurrent_executions = 3

    monitor = NodeHealthMonitor(monitoring_interval=10.0, health_check_timeout=1.0)
    monitor._gateway = gateway

    status = asyncio.run(monitor.check_node_health("node-a"))

    assert status.is_reachable is True
    assert status.cpu_usage == 35.0
    assert status.memory_usage == 45.0
    assert status.gpu_usage == 25.0
    assert status.response_time_ms == 120.0
    assert status.queue_length == 3


def test_health_monitor_marks_dead_node_as_unreachable_then_quarantined():
    gateway = _build_gateway_with_node("node-dead", alive=False)

    monitor = NodeHealthMonitor(monitoring_interval=10.0, health_check_timeout=1.0)
    monitor._gateway = gateway

    status = None
    for _ in range(5):
        status = asyncio.run(monitor.check_node_health("node-dead"))

    assert status is not None
    assert status.is_reachable is False
    assert status.overall_health == NodeHealthLevel.QUARANTINED


def test_health_monitor_falls_back_when_node_has_no_health_metrics():
    node = SimpleNamespace(
        functions={},
        is_alive=lambda: True,
    )
    gateway = SimpleNamespace(_nodes={"node-no-metrics": node})

    monitor = NodeHealthMonitor(monitoring_interval=10.0, health_check_timeout=1.0)
    monitor._gateway = gateway

    first = asyncio.run(monitor.check_node_health("node-no-metrics"))
    second = asyncio.run(monitor.check_node_health("node-no-metrics"))

    assert first.is_reachable is True
    assert first.cpu_usage == 0.0
    assert first.memory_usage == 0.0
    assert second.cpu_usage == 0.0
    assert second.memory_usage == 0.0


def test_health_monitor_adaptive_interval_is_deterministic():
    monitor = NodeHealthMonitor(monitoring_interval=12.0, health_check_timeout=1.0)

    base_interval = monitor._next_interval(monitoring_duration=2.0)
    assert base_interval == 10.0

    with monitor._health_cache_lock:
        monitor._health_cache["a"] = NodeHealthStatus(
            node_id="a", overall_health=NodeHealthLevel.UNHEALTHY
        )
        monitor._health_cache["b"] = NodeHealthStatus(
            node_id="b", overall_health=NodeHealthLevel.HEALTHY
        )

    aggressive_interval = monitor._next_interval(monitoring_duration=2.0)
    assert aggressive_interval == 5.0

    with monitor._health_cache_lock:
        monitor._health_cache["a"].overall_health = NodeHealthLevel.HEALTHY

    relaxed_interval = monitor._next_interval(monitoring_duration=2.0)
    assert relaxed_interval == 15.0
