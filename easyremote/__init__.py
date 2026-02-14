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
    "ServiceRuntime": ("easyremote.protocols", "ServiceRuntime"),
    "ProtocolService": ("easyremote.protocols", "ProtocolService"),
    "ProtocolServiceTemplate": ("easyremote.protocols", "ProtocolServiceTemplate"),
    "agent_capability": ("easyremote.protocols", "agent_capability"),
    "EasyRemoteClientRuntime": ("easyremote.protocols", "EasyRemoteClientRuntime"),
    "MCPService": ("easyremote.mcp", "MCPService"),
    "A2AService": ("easyremote.a2a", "A2AService"),
    "MediaFrame": ("easyremote.skills", "MediaFrame"),
    "stream_bytes": ("easyremote.skills", "stream_bytes"),
    "stream_audio_pcm": ("easyremote.skills", "stream_audio_pcm"),
    "CapabilitySpec": ("easyremote.skills", "CapabilitySpec"),
    "RemotePipeline": ("easyremote.skills", "RemotePipeline"),
    "RemoteSkill": ("easyremote.skills", "RemoteSkill"),
    "pipeline_function": ("easyremote.skills", "pipeline_function"),
    "UserAgentProfile": ("easyremote.agent_service", "UserAgentProfile"),
    "InstalledSkill": ("easyremote.agent_service", "InstalledSkill"),
    "RemoteAgentService": ("easyremote.agent_service", "RemoteAgentService"),
    "device_action": ("easyremote.device_host", "device_action"),
    "DeviceAction": ("easyremote.device_host", "DeviceAction"),
    "InstalledDeviceSkill": ("easyremote.device_host", "InstalledDeviceSkill"),
    "UserDeviceCapabilityHost": ("easyremote.device_host", "UserDeviceCapabilityHost"),
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
