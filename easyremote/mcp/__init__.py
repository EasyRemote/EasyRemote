#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP compatibility facade for EasyRemote.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, Mapping, Optional, Union

from ..protocols import MCPProtocolAdapter, ProtocolGateway, ProtocolName, ProtocolRuntime
from ..protocols.service import MCPService


class MCPGateway:
    """
    Thin MCP gateway facade backed by the unified protocol gateway.
    """

    def __init__(self, runtime: ProtocolRuntime):
        self._gateway = ProtocolGateway(runtime=runtime, adapters=(MCPProtocolAdapter(),))

    async def handle_request(
        self, payload: Union[Mapping[str, Any], list[Any]]
    ) -> Optional[Union[Dict[str, Any], list[Dict[str, Any]]]]:
        """
        Handle one MCP request payload.
        """
        return await self._gateway.handle_request(ProtocolName.MCP, payload)


__all__ = [
    "MCPGateway",
    "MCPProtocolAdapter",
    "MCPService",
]
