#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote public API with lazy imports.

This avoids importing heavy gRPC/protobuf modules unless the corresponding API
objects are actually requested.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from importlib import import_module
from typing import Any, Dict, Tuple

from ._version import __version__

__author__ = "Silan Hu"
__email__ = "silan.hu@u.nus.edu"

_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "Server": ("easyremote.core", "Server"),
    "ComputeNode": ("easyremote.core", "ComputeNode"),
    "Client": ("easyremote.core", "Client"),
    "remote": ("easyremote.decorators", "remote"),
    "get_performance_monitor": ("easyremote.core", "get_performance_monitor"),
    "LoadBalancer": ("easyremote.core.balancing", "LoadBalancer"),
    "LoadBalancingStrategy": ("easyremote.core.balancing", "LoadBalancingStrategy"),
    "RequestContext": ("easyremote.core.balancing", "RequestContext"),
    "NodeStats": ("easyremote.core.balancing", "NodeStats"),
    "MCPGateway": ("easyremote.mcp", "MCPGateway"),
    "A2AGateway": ("easyremote.a2a", "A2AGateway"),
    "ProtocolGateway": ("easyremote.protocols", "ProtocolGateway"),
    "ProtocolName": ("easyremote.protocols", "ProtocolName"),
    "ProtocolAdapter": ("easyremote.protocols", "ProtocolAdapter"),
    "MCPProtocolAdapter": ("easyremote.protocols", "MCPProtocolAdapter"),
    "A2AProtocolAdapter": ("easyremote.protocols", "A2AProtocolAdapter"),
}

__all__ = ["__version__", *sorted(_EXPORT_MAP.keys())]


def __getattr__(name: str) -> Any:
    """
    Resolve public API symbols lazily.
    """
    if name not in _EXPORT_MAP:
        raise AttributeError("module 'easyremote' has no attribute '{0}'".format(name))

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
