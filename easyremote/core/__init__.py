#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote core module exports (lazy-loaded).

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from importlib import import_module
from typing import Any, Dict, Tuple

_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "BasicMonitor": ("easyremote.core.tools", "BasicMonitor"),
    "quick_health_check": ("easyremote.core.tools", "quick_health_check"),
    "quick_metrics": ("easyremote.core.tools", "quick_metrics"),
    "Server": ("easyremote.core.nodes", "Server"),
    "ComputeNode": ("easyremote.core.nodes", "ComputeNode"),
    "Client": ("easyremote.core.nodes", "Client"),
    "EasyRemoteConfig": ("easyremote.core.config", "EasyRemoteConfig"),
    "get_config": ("easyremote.core.config", "get_config"),
    "create_config": ("easyremote.core.config", "create_config"),
}

__all__ = sorted(list(_EXPORT_MAP.keys()) + ["get_performance_monitor"])


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError("module 'easyremote.core' has no attribute '{0}'".format(name))

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def get_performance_monitor():
    """
    Backward-compatible performance monitor constructor.
    """
    monitor_cls = __getattr__("BasicMonitor")
    return monitor_cls()
