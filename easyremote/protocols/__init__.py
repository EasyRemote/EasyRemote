#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote protocol adapters and unified gateway.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from .adapter import (
    InvalidParamsError,
    InvalidRequestError,
    JsonRpcProtocolAdapter,
    JsonRpcProtocolError,
    ProtocolAdapter,
)
from .gateway import ProtocolGateway
from .models import FunctionDescriptor, FunctionInvocation, ProtocolName
from .runtime import ProtocolRuntime
from .mcp import MCPProtocolAdapter
from .a2a import A2AProtocolAdapter

__all__ = [
    "ProtocolAdapter",
    "JsonRpcProtocolAdapter",
    "JsonRpcProtocolError",
    "InvalidRequestError",
    "InvalidParamsError",
    "ProtocolGateway",
    "ProtocolName",
    "ProtocolRuntime",
    "FunctionDescriptor",
    "FunctionInvocation",
    "MCPProtocolAdapter",
    "A2AProtocolAdapter",
]
