#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Robust gateway load balancers for EasyRemote.

This module intentionally favors deterministic, testable strategies over
placeholder "intelligent" or pseudo-ML routing logic.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from ..utils.exceptions import LoadBalancingError, NoAvailableNodesError
from ..utils.logger import ModernLogger
from .simple_balancer import (
    BalancingStrategy,
    NodeSelectionStrategy,
    ResourceAwareSelectionStrategy,
    RoundRobinSelectionStrategy,
    SimpleLoadBalancer,
    SimpleNodeStats,
)
from .strategies import LoadBalancerInterface, LoadBalancingStrategy, NodeStats, RequestContext


class BalancerPerformanceLevel(Enum):
    """Compatibility enum retained for public API stability."""

    LOW_LATENCY = "low_latency"
    BALANCED = "balanced"
    COMPREHENSIVE = "comprehensive"


@dataclass
class LoadBalancingMetrics:
    """Operational metrics for gateway routing decisions."""

    total_requests: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    average_routing_time_ms: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_routes / self.total_requests

    def record(self, routing_time_ms: float, success: bool) -> None:
        self.total_requests += 1
        if success:
            self.successful_routes += 1
        else:
            self.failed_routes += 1

        if self.total_requests == 1:
            self.average_routing_time_ms = routing_time_ms
        else:
            alpha = 0.1
            self.average_routing_time_ms = (
                alpha * routing_time_ms + (1 - alpha) * self.average_routing_time_ms
            )

        self.last_updated = datetime.now()


def _coerce_balancing_strategy(
    strategy: Union[str, BalancingStrategy, LoadBalancingStrategy, None]
) -> Optional[BalancingStrategy]:
    """Normalize user or config strategy to supported stable strategies."""

    if strategy is None:
        return None

    if isinstance(strategy, BalancingStrategy):
        return strategy

    if isinstance(strategy, LoadBalancingStrategy):
        mapping = {
            LoadBalancingStrategy.ROUND_ROBIN: BalancingStrategy.ROUND_ROBIN,
            LoadBalancingStrategy.RESOURCE_AWARE: BalancingStrategy.RESOURCE_AWARE,
        }
        return mapping.get(strategy, BalancingStrategy.RESOURCE_AWARE)

    if isinstance(strategy, str):
        normalized = strategy.strip().lower()
        aliases = {
            "round_robin": BalancingStrategy.ROUND_ROBIN,
            "rr": BalancingStrategy.ROUND_ROBIN,
            "random": BalancingStrategy.RANDOM,
            "resource_aware": BalancingStrategy.RESOURCE_AWARE,
            "resource": BalancingStrategy.RESOURCE_AWARE,
            "smart": BalancingStrategy.RESOURCE_AWARE,
            "smart_adaptive": BalancingStrategy.RESOURCE_AWARE,
            "dynamic": BalancingStrategy.RESOURCE_AWARE,
            "latency_based": BalancingStrategy.RESOURCE_AWARE,
            "cost_aware": BalancingStrategy.RESOURCE_AWARE,
            "ml_adaptive": BalancingStrategy.RESOURCE_AWARE,
        }
        return aliases.get(normalized)

    return None


def _node_stats_to_simple(node_id: str, stats: NodeStats) -> SimpleNodeStats:
    """Convert `NodeStats` to `SimpleNodeStats` for stable selectors."""

    return SimpleNodeStats(
        node_id=node_id,
        cpu_usage=float(getattr(stats, "cpu_usage", 0.0)),
        memory_usage=float(getattr(stats, "memory_usage", 0.0)),
        active_tasks=int(getattr(stats, "queue_length", 0)),
        response_time_ms=float(getattr(stats, "response_time", 0.0)),
    )


class GatewayLoadBalancer(ModernLogger):
    """
    Stable gateway load balancer with pluggable strategies.

    Design goals:
    - deterministic behavior
    - simple, inspectable routing decisions
    - explicit extension points via strategy registration
    """

    def __init__(
        self,
        gateway_instance: Any,
        performance_level: BalancerPerformanceLevel = BalancerPerformanceLevel.BALANCED,
        default_strategy: BalancingStrategy = BalancingStrategy.RESOURCE_AWARE,
    ) -> None:
        super().__init__(name="GatewayLoadBalancer")

        self.gateway = gateway_instance
        self.performance_level = performance_level
        self.metrics = LoadBalancingMetrics()

        self._selector_lock = threading.Lock()
        self._selector = SimpleLoadBalancer(default_strategy)
        self._default_strategy = default_strategy

    def register_strategy(
        self,
        strategy: BalancingStrategy,
        selection_strategy: NodeSelectionStrategy,
    ) -> None:
        """Register a custom selection strategy implementation."""
        with self._selector_lock:
            self._selector.register_strategy(strategy, selection_strategy)

    def set_default_strategy(
        self,
        strategy: Union[str, BalancingStrategy, LoadBalancingStrategy],
    ) -> None:
        """Update default routing strategy for future requests."""
        resolved = _coerce_balancing_strategy(strategy)
        if resolved is None:
            raise LoadBalancingError(
                message=f"Unsupported balancing strategy: {strategy}",
                strategy=str(strategy),
            )

        self._default_strategy = resolved
        with self._selector_lock:
            self._selector.set_strategy(resolved)

    async def route_request(
        self,
        function_name: str,
        request_context: RequestContext,
        balancing_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Async-compatible routing entry retained for backward compatibility."""
        available_nodes = self._discover_function_providers(function_name)
        if not available_nodes:
            raise NoAvailableNodesError(
                message=f"No compute nodes provide function '{function_name}'",
                function_name=function_name,
                total_nodes=0,
                healthy_nodes=0,
            )

        strategy_override = None
        if isinstance(balancing_config, Mapping):
            strategy_override = _coerce_balancing_strategy(
                balancing_config.get("strategy")
            )

        return self._select_node_internal(
            function_name=function_name,
            request_context=request_context,
            available_nodes=available_nodes,
            strategy_override=strategy_override,
        )

    def select_node(
        self,
        function_name: str,
        request_context: RequestContext,
        available_nodes: List[str],
    ) -> str:
        """
        Synchronous node selection API used by the gateway runtime.
        """
        return self._select_node_internal(
            function_name=function_name,
            request_context=request_context,
            available_nodes=available_nodes,
            strategy_override=None,
        )

    def _select_node_internal(
        self,
        function_name: str,
        request_context: RequestContext,
        available_nodes: Sequence[str],
        strategy_override: Optional[BalancingStrategy],
    ) -> str:
        if not available_nodes:
            raise NoAvailableNodesError(
                message=f"No nodes available for function '{function_name}'",
                function_name=function_name,
                total_nodes=0,
                healthy_nodes=0,
            )

        start_time = time.time()

        try:
            node_stats = self._collect_node_stats(available_nodes)
            strategy = self._resolve_strategy(
                request_context=request_context,
                strategy_override=strategy_override,
                node_stats=node_stats,
            )

            with self._selector_lock:
                self._selector.set_strategy(strategy)
                selected = self._selector.select_node(list(available_nodes), node_stats)

            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.record(elapsed_ms, success=True)
            return selected

        except Exception as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.record(elapsed_ms, success=False)
            self.error(f"Load balancing failed for function '{function_name}': {exc}")

            # Stable fallback: deterministic round-robin as last resort.
            with self._selector_lock:
                self._selector.set_strategy(BalancingStrategy.ROUND_ROBIN)
                return self._selector.select_node(list(available_nodes), {})

    def _resolve_strategy(
        self,
        request_context: RequestContext,
        strategy_override: Optional[BalancingStrategy],
        node_stats: Mapping[str, SimpleNodeStats],
    ) -> BalancingStrategy:
        if strategy_override is not None:
            return strategy_override

        # Request-level explicit override.
        requirements = getattr(request_context, "requirements", None)
        if isinstance(requirements, Mapping):
            requested = _coerce_balancing_strategy(
                requirements.get("load_balancing_strategy")
                or requirements.get("strategy")
            )
            if requested is not None:
                return requested

        # If no statistics are available, prefer fairness over guessed scoring.
        if not node_stats:
            return BalancingStrategy.ROUND_ROBIN

        return self._default_strategy

    def _discover_function_providers(self, function_name: str) -> List[str]:
        providers: List[str] = []
        nodes = getattr(self.gateway, "_nodes", None)
        if not isinstance(nodes, Mapping):
            return providers

        for node_id, node_info in nodes.items():
            if not hasattr(node_info, "functions"):
                continue
            if function_name in node_info.functions and getattr(node_info, "is_alive", lambda: True)():
                providers.append(node_id)
        return providers

    def _collect_node_stats(
        self,
        available_nodes: Sequence[str],
    ) -> Dict[str, SimpleNodeStats]:
        stats: Dict[str, SimpleNodeStats] = {}

        nodes = getattr(self.gateway, "_nodes", None)
        if not isinstance(nodes, Mapping):
            return stats

        for node_id in available_nodes:
            node_info = nodes.get(node_id)
            if node_info is None:
                continue

            health_metrics = getattr(node_info, "health_metrics", None)
            if health_metrics is None:
                continue

            stats[node_id] = SimpleNodeStats(
                node_id=node_id,
                cpu_usage=float(getattr(health_metrics, "cpu_usage_percent", 0.0)),
                memory_usage=float(getattr(health_metrics, "memory_usage_percent", 0.0)),
                active_tasks=int(getattr(health_metrics, "concurrent_executions", 0)),
                response_time_ms=float(getattr(health_metrics, "network_latency_ms", 0.0)),
            )

        return stats

    def get_performance_metrics(self) -> LoadBalancingMetrics:
        return self.metrics

    def get_strategy_performance(self) -> Dict[str, float]:
        # Kept for backward compatibility with legacy diagnostics APIs.
        return {
            BalancingStrategy.ROUND_ROBIN.value: 1.0,
            BalancingStrategy.RANDOM.value: 1.0,
            BalancingStrategy.RESOURCE_AWARE.value: 1.0,
        }


class IntelligentLoadBalancer(GatewayLoadBalancer):
    """
    Backward-compatible public class name.

    `enable_adaptive_learning` and `metrics_retention_hours` are intentionally
    retained for constructor compatibility, but are not used by the stable
    deterministic routing core.
    """

    def __init__(
        self,
        gateway_instance: Any,
        performance_level: BalancerPerformanceLevel = BalancerPerformanceLevel.BALANCED,
        enable_adaptive_learning: bool = False,
        metrics_retention_hours: int = 24,
    ) -> None:
        super().__init__(
            gateway_instance=gateway_instance,
            performance_level=performance_level,
            default_strategy=BalancingStrategy.RESOURCE_AWARE,
        )
        self.enable_adaptive_learning = enable_adaptive_learning
        self.metrics_retention_hours = metrics_retention_hours


class EnhancedRoundRobinBalancer(LoadBalancerInterface):
    """Compatibility strategy that delegates to stable round-robin selection."""

    def __init__(self) -> None:
        self._selector = RoundRobinSelectionStrategy()

    async def select_node(
        self,
        available_nodes: List[str],
        request_context: RequestContext,
        node_stats: Dict[str, NodeStats],
    ) -> str:
        simple_stats = {
            node_id: _node_stats_to_simple(node_id, stats)
            for node_id, stats in node_stats.items()
        }
        return self._selector.select_node(available_nodes, simple_stats)

    def get_strategy_name(self) -> str:
        return "enhanced_round_robin"


class IntelligentResourceAwareBalancer(LoadBalancerInterface):
    """Compatibility strategy that delegates to stable resource-aware selection."""

    def __init__(self) -> None:
        self._selector = ResourceAwareSelectionStrategy()

    async def select_node(
        self,
        available_nodes: List[str],
        request_context: RequestContext,
        node_stats: Dict[str, NodeStats],
    ) -> str:
        simple_stats = {
            node_id: _node_stats_to_simple(node_id, stats)
            for node_id, stats in node_stats.items()
        }
        return self._selector.select_node(available_nodes, simple_stats)

    def get_strategy_name(self) -> str:
        return "intelligent_resource_aware"


class AdaptiveLatencyBasedBalancer(LoadBalancerInterface):
    """Compatibility latency-based strategy using measured response time."""

    async def select_node(
        self,
        available_nodes: List[str],
        request_context: RequestContext,
        node_stats: Dict[str, NodeStats],
    ) -> str:
        if not available_nodes:
            raise NoAvailableNodesError(message="No available nodes")

        best_node = available_nodes[0]
        best_latency = float("inf")

        for node_id in available_nodes:
            stats = node_stats.get(node_id)
            latency = float(getattr(stats, "response_time", 0.0)) if stats else 0.0
            if latency < best_latency:
                best_latency = latency
                best_node = node_id

        return best_node

    def get_strategy_name(self) -> str:
        return "adaptive_latency_based"


class SmartCostAwareBalancer(LoadBalancerInterface):
    """Compatibility cost-aware strategy favoring lower load as proxy cost."""

    def __init__(self) -> None:
        self._selector = ResourceAwareSelectionStrategy()

    async def select_node(
        self,
        available_nodes: List[str],
        request_context: RequestContext,
        node_stats: Dict[str, NodeStats],
    ) -> str:
        simple_stats = {
            node_id: _node_stats_to_simple(node_id, stats)
            for node_id, stats in node_stats.items()
        }
        return self._selector.select_node(available_nodes, simple_stats)

    def get_strategy_name(self) -> str:
        return "smart_cost_aware"


class MachineLearningAdaptiveBalancer(IntelligentResourceAwareBalancer):
    """Deprecated compatibility wrapper using deterministic resource-aware logic."""

    def get_strategy_name(self) -> str:
        return "ml_adaptive"

    def supports_learning(self) -> bool:
        return False


class DynamicStrategyBalancer(LoadBalancerInterface):
    """Compatibility dynamic strategy choosing between latency and resource-aware."""

    def __init__(self, parent_balancer: Optional[Any] = None) -> None:
        self.parent_balancer = parent_balancer
        self._latency = AdaptiveLatencyBasedBalancer()
        self._resource = IntelligentResourceAwareBalancer()

    async def select_node(
        self,
        available_nodes: List[str],
        request_context: RequestContext,
        node_stats: Dict[str, NodeStats],
    ) -> str:
        max_latency = getattr(request_context, "max_network_latency_ms", None)
        if max_latency is not None and max_latency <= 100:
            return await self._latency.select_node(available_nodes, request_context, node_stats)
        return await self._resource.select_node(available_nodes, request_context, node_stats)

    def get_strategy_name(self) -> str:
        return "dynamic"


# Backward compatibility alias
LoadBalancer = IntelligentLoadBalancer


__all__ = [
    "GatewayLoadBalancer",
    "IntelligentLoadBalancer",
    "LoadBalancer",
    "LoadBalancingMetrics",
    "BalancerPerformanceLevel",
    "EnhancedRoundRobinBalancer",
    "IntelligentResourceAwareBalancer",
    "AdaptiveLatencyBasedBalancer",
    "SmartCostAwareBalancer",
    "MachineLearningAdaptiveBalancer",
    "DynamicStrategyBalancer",
]
