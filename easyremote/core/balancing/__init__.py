#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Load balancing public exports for EasyRemote (lazy-loaded).

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from importlib import import_module
from typing import Any, Dict, Tuple

_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    # Stable runtime balancers
    "LoadBalancer": ("easyremote.core.balancing.balancers", "LoadBalancer"),
    "RoundRobinBalancer": (
        "easyremote.core.balancing.balancers",
        "EnhancedRoundRobinBalancer",
    ),
    "ResourceAwareBalancer": (
        "easyremote.core.balancing.balancers",
        "IntelligentResourceAwareBalancer",
    ),
    "LatencyBasedBalancer": (
        "easyremote.core.balancing.balancers",
        "AdaptiveLatencyBasedBalancer",
    ),
    "CostAwareBalancer": (
        "easyremote.core.balancing.balancers",
        "SmartCostAwareBalancer",
    ),
    "SmartAdaptiveBalancer": (
        "easyremote.core.balancing.balancers",
        "MachineLearningAdaptiveBalancer",
    ),
    # Optional monitoring components
    "NodeHealthMonitor": (
        "easyremote.core.balancing.health_monitor",
        "NodeHealthMonitor",
    ),
    "NodeHealthStatus": (
        "easyremote.core.balancing.health_monitor",
        "NodeHealthStatus",
    ),
    "PerformanceCollector": (
        "easyremote.core.balancing.performance_collector",
        "PerformanceCollector",
    ),
    # Core strategy data models
    "LoadBalancingStrategy": (
        "easyremote.core.balancing.strategies",
        "LoadBalancingStrategy",
    ),
    "RequestContext": ("easyremote.core.balancing.strategies", "RequestContext"),
    "NodeStats": ("easyremote.core.balancing.strategies", "NodeStats"),
}

__all__ = sorted(_EXPORT_MAP.keys())


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(
            "module 'easyremote.core.balancing' has no attribute '{0}'".format(name)
        )

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
