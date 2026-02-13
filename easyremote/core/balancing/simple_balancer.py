#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote Simple Load Balancing Module

This module provides basic load balancing functionality for the EasyRemote
distributed computing framework. It focuses on simplicity and core functionality
needed for basic distributed computing operations.

Author: Silan Hu (silan.hu@u.nus.edu)
Version: 1.0.0 (Simplified)
"""

import random
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Union

from ..utils.exceptions import LoadBalancingError, NoAvailableNodesError

class BalancingStrategy(Enum):
    """Simple load balancing strategies."""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    RESOURCE_AWARE = "resource_aware"


@dataclass
class SimpleNodeStats:
    """Basic node statistics."""
    node_id: str
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    active_tasks: int = 0
    response_time_ms: float = 0.0
    
    @property
    def load_score(self) -> float:
        """Calculate simple load score (0-100, lower is better)."""
        return (self.cpu_usage + self.memory_usage) / 2 + (self.active_tasks * 5)


@dataclass(frozen=True)
class LoadScoringWeights:
    """Weights used to score node load (lower score means better candidate)."""
    cpu_weight: float = 0.4
    memory_weight: float = 0.35
    active_tasks_weight: float = 0.2
    response_time_weight: float = 0.05

    def __post_init__(self):
        total = (
            self.cpu_weight
            + self.memory_weight
            + self.active_tasks_weight
            + self.response_time_weight
        )
        if total <= 0:
            raise ValueError("At least one load scoring weight must be positive")


class NodeLoadScorer:
    """
    Encapsulates node scoring logic so strategies stay focused on node selection.
    """

    def __init__(self, weights: Optional[LoadScoringWeights] = None):
        self._weights = weights or LoadScoringWeights()

    def score(self, stats: SimpleNodeStats) -> float:
        """Return a normalized load score in the 0-100 range."""
        cpu_score = self._clamp(stats.cpu_usage, 0.0, 100.0)
        memory_score = self._clamp(stats.memory_usage, 0.0, 100.0)
        task_score = self._clamp(stats.active_tasks * 10.0, 0.0, 100.0)
        # Treat 1000ms as the high-latency baseline for simple mode.
        latency_score = self._clamp(stats.response_time_ms / 10.0, 0.0, 100.0)

        return (
            self._weights.cpu_weight * cpu_score
            + self._weights.memory_weight * memory_score
            + self._weights.active_tasks_weight * task_score
            + self._weights.response_time_weight * latency_score
        )

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))


class NodeSelectionStrategy(ABC):
    """Interface for node selection strategies."""

    @abstractmethod
    def select_node(
        self,
        available_nodes: Sequence[str],
        node_stats: Mapping[str, SimpleNodeStats],
    ) -> str:
        """Select one node from available candidates."""
        raise NotImplementedError


def _require_nodes(available_nodes: Sequence[str]) -> None:
    """Validate candidate nodes before strategy selection."""
    if not available_nodes:
        raise NoAvailableNodesError(message="No available nodes")


class RoundRobinSelectionStrategy(NodeSelectionStrategy):
    """Thread-safe round-robin strategy."""

    def __init__(self):
        self._counter = 0
        self._lock = threading.Lock()

    def select_node(
        self,
        available_nodes: Sequence[str],
        node_stats: Mapping[str, SimpleNodeStats],
    ) -> str:
        _require_nodes(available_nodes)

        with self._lock:
            selected = available_nodes[self._counter % len(available_nodes)]
            self._counter += 1
        return selected


class RandomSelectionStrategy(NodeSelectionStrategy):
    """Random strategy with injectable RNG for deterministic testing."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()

    def select_node(
        self,
        available_nodes: Sequence[str],
        node_stats: Mapping[str, SimpleNodeStats],
    ) -> str:
        _require_nodes(available_nodes)
        return self._rng.choice(list(available_nodes))


class ResourceAwareSelectionStrategy(NodeSelectionStrategy):
    """Selects the least-loaded node using `NodeLoadScorer`."""

    def __init__(
        self,
        scorer: Optional[NodeLoadScorer] = None,
        fallback: Optional[NodeSelectionStrategy] = None,
    ):
        self._scorer = scorer or NodeLoadScorer()
        self._fallback = fallback or RoundRobinSelectionStrategy()

    def select_node(
        self,
        available_nodes: Sequence[str],
        node_stats: Mapping[str, SimpleNodeStats],
    ) -> str:
        _require_nodes(available_nodes)

        if not node_stats:
            return self._fallback.select_node(available_nodes, node_stats)

        best_node = None
        best_score = float("inf")
        for node in available_nodes:
            stats = node_stats.get(node)
            if stats is None:
                continue
            score = self._scorer.score(stats)
            if score < best_score:
                best_score = score
                best_node = node

        if best_node is None:
            return self._fallback.select_node(available_nodes, node_stats)
        return best_node


class SimpleLoadBalancer:
    """
    Simple load balancer with pluggable strategy objects.

    Public API remains backward compatible with legacy callers that pass
    `BalancingStrategy` and use `create_balancer`.
    """

    def __init__(
        self,
        strategy: BalancingStrategy = BalancingStrategy.ROUND_ROBIN,
    ):
        self._strategies: Dict[BalancingStrategy, NodeSelectionStrategy] = {}
        self._register_default_strategies()
        self.strategy = BalancingStrategy.ROUND_ROBIN
        self.set_strategy(strategy)

    def _register_default_strategies(self) -> None:
        self.register_strategy(BalancingStrategy.ROUND_ROBIN, RoundRobinSelectionStrategy())
        self.register_strategy(BalancingStrategy.RANDOM, RandomSelectionStrategy())
        self.register_strategy(
            BalancingStrategy.RESOURCE_AWARE,
            ResourceAwareSelectionStrategy(),
        )

    def register_strategy(
        self,
        strategy: BalancingStrategy,
        selection_strategy: NodeSelectionStrategy,
    ) -> None:
        """Register or replace a strategy implementation."""
        self._strategies[strategy] = selection_strategy

    def set_strategy(self, strategy: BalancingStrategy) -> None:
        """Switch active balancing strategy."""
        if strategy not in self._strategies:
            raise LoadBalancingError(
                message=f"Unsupported strategy: {strategy}",
                strategy=str(strategy),
            )
        self.strategy = strategy

    def select_node(
        self,
        available_nodes: List[str],
        node_stats: Optional[Dict[str, SimpleNodeStats]] = None,
    ) -> str:
        """
        Select optimal node using configured strategy.
        
        Args:
            available_nodes: List of available node IDs
            node_stats: Optional node statistics
            
        Returns:
            Selected node ID
        """
        _require_nodes(available_nodes)

        selector = self._strategies[self.strategy]
        stats = node_stats or {}
        return selector.select_node(available_nodes, stats)

    # Kept for backward compatibility with legacy internal usage.
    def _round_robin_select(self, nodes: List[str]) -> str:
        return self._strategies[BalancingStrategy.ROUND_ROBIN].select_node(nodes, {})

    # Kept for backward compatibility with legacy internal usage.
    def _resource_aware_select(
        self,
        nodes: List[str],
        node_stats: Optional[Dict[str, SimpleNodeStats]],
    ) -> str:
        selector = self._strategies[BalancingStrategy.RESOURCE_AWARE]
        return selector.select_node(nodes, node_stats or {})


def _resolve_strategy(strategy: Union[str, BalancingStrategy]) -> BalancingStrategy:
    if isinstance(strategy, BalancingStrategy):
        return strategy

    if isinstance(strategy, str):
        normalized = strategy.strip().lower()
        for candidate in BalancingStrategy:
            if candidate.value == normalized:
                return candidate

    # Preserve legacy behavior: unknown strategy falls back to round-robin.
    return BalancingStrategy.ROUND_ROBIN


def create_balancer(strategy: Union[str, BalancingStrategy] = "round_robin") -> SimpleLoadBalancer:
    """Create a simple load balancer with specified strategy."""
    strategy_map = {
        "round_robin": BalancingStrategy.ROUND_ROBIN,
        "random": BalancingStrategy.RANDOM,
        "resource_aware": BalancingStrategy.RESOURCE_AWARE,
    }
    selected_strategy = _resolve_strategy(strategy)

    # Keep map for backward compatibility with older custom inputs.
    if isinstance(strategy, str) and strategy in strategy_map:
        selected_strategy = strategy_map[strategy]

    return SimpleLoadBalancer(selected_strategy)


__all__ = [
    "BalancingStrategy",
    "SimpleNodeStats",
    "LoadScoringWeights",
    "NodeLoadScorer",
    "NodeSelectionStrategy",
    "RoundRobinSelectionStrategy",
    "RandomSelectionStrategy",
    "ResourceAwareSelectionStrategy",
    "SimpleLoadBalancer",
    "create_balancer",
]
