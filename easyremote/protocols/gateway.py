#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified protocol gateway for EasyRemote.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, Iterable, List, Sequence, Union

from ..core.utils.exceptions import ProtocolHandlingError
from .adapter import JsonRpcProtocolAdapter, ProtocolAdapter
from .models import ProtocolName
from .runtime import ProtocolRuntime


class ProtocolGateway:
    """
    Dispatch gateway for all protocol adapters.

    This class keeps protocol parsing concerns modular and allows new protocol
    adapters to be added without changing core execution logic.
    """

    def __init__(
        self, runtime: ProtocolRuntime, adapters: Iterable[ProtocolAdapter] = ()
    ):
        self._runtime = runtime
        self._adapters: Dict[ProtocolName, ProtocolAdapter] = {}
        for adapter in adapters:
            self.register_adapter(adapter)

    def register_adapter(self, adapter: ProtocolAdapter) -> None:
        """
        Register or replace a protocol adapter.
        """
        self._adapters[adapter.protocol] = adapter

    def supported_protocols(self) -> List[str]:
        """
        List enabled protocol names.
        """
        return sorted([protocol.value for protocol in self._adapters.keys()])

    async def handle_request(
        self, protocol: Union[ProtocolName, str], payload: Any
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Route a request to its corresponding protocol adapter.
        """
        try:
            protocol_name = ProtocolName.from_value(protocol)
        except Exception as exc:
            raise ProtocolHandlingError(
                message=f"Unsupported protocol value: {protocol}",
                protocol=str(protocol),
                cause=exc,
            ) from exc

        adapter = self._adapters.get(protocol_name)
        if adapter is None:
            raise ProtocolHandlingError(
                message="Protocol adapter is not registered: {0}".format(
                    protocol_name.value
                ),
                protocol=protocol_name.value,
            )

        if (
            isinstance(payload, (list, tuple))
            and isinstance(adapter, JsonRpcProtocolAdapter)
            and adapter.supports_batch_requests
        ):
            return await self._handle_batch_request(
                protocol_name=protocol_name,
                adapter=adapter,
                payloads=payload,
            )

        return await adapter.handle_request(payload=payload, runtime=self._runtime)

    async def _handle_batch_request(
        self,
        protocol_name: ProtocolName,
        adapter: JsonRpcProtocolAdapter,
        payloads: Sequence[Any],
    ) -> Union[List[Dict[str, Any]], Dict[str, Any], None]:
        """
        Handle JSON-RPC batch requests.
        """
        if len(payloads) == 0:
            return adapter._error(
                request_id=None,
                code=-32600,
                message="Invalid Request",
                data=adapter.standard_error_data(
                    protocol=protocol_name.value,
                    method=None,
                    error_type="InvalidRequestError",
                ),
            )

        responses: List[Dict[str, Any]] = []
        for item in payloads:
            response = await adapter.handle_request(payload=item, runtime=self._runtime)
            if response is not None:
                responses.append(response)

        if not responses:
            return None
        return responses
