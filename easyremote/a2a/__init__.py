#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A2A compatibility facade for EasyRemote.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, Mapping, Optional, Union

from ..protocols import A2AProtocolAdapter, ProtocolGateway, ProtocolName, ProtocolRuntime
from ..protocols.service import A2AService


class A2AGateway:
    """
    Thin A2A gateway facade backed by the unified protocol gateway.
    """

    def __init__(self, runtime: ProtocolRuntime):
        self._gateway = ProtocolGateway(runtime=runtime, adapters=(A2AProtocolAdapter(),))

    async def handle_request(
        self, payload: Union[Mapping[str, Any], list[Any]]
    ) -> Optional[Union[Dict[str, Any], list[Dict[str, Any]]]]:
        """
        Handle one A2A request payload.
        """
        return await self._gateway.handle_request(ProtocolName.A2A, payload)


__all__ = [
    "A2AGateway",
    "A2AProtocolAdapter",
    "A2AService",
]
