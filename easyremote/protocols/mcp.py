#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP protocol adapter for EasyRemote.

This adapter translates MCP-style requests into EasyRemote runtime invocations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, Mapping, Optional

from .adapter import InvalidParamsError, JsonRpcProtocolAdapter
from .models import FunctionInvocation, ProtocolName
from .runtime import ProtocolRuntime


class MCPProtocolAdapter(JsonRpcProtocolAdapter):
    """
    MCP-compatible adapter.

    Supported methods:
    - initialize
    - tools/list
    - tools/call
    - ping
    """

    INITIALIZE_METHODS = {"initialize", "mcp.initialize"}
    TOOLS_LIST_METHODS = {"tools/list", "mcp.tools/list"}
    TOOLS_CALL_METHODS = {"tools/call", "mcp.tools/call"}

    @property
    def protocol(self) -> ProtocolName:
        return ProtocolName.MCP

    async def handle_request(
        self, payload: Mapping[str, Any], runtime: ProtocolRuntime
    ) -> Optional[Dict[str, Any]]:
        request_id: Any = None
        method = ""
        is_notification = False
        if isinstance(payload, Mapping):
            request_id = payload.get("id")

        try:
            request_id, method, params, is_notification = self._parse_jsonrpc_request(
                payload
            )

            if method in self.INITIALIZE_METHODS:
                response = self._success(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "easyremote", "version": "0.1.4"},
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": False},
                        },
                    },
                )
                return None if is_notification else response

            if method in self.TOOLS_LIST_METHODS:
                descriptors = await runtime.list_functions()
                tools = []
                for descriptor in descriptors:
                    tools.append(
                        {
                            "name": descriptor.name,
                            "description": descriptor.description
                            or "EasyRemote distributed function",
                            "inputSchema": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "annotations": {
                                "nodes": descriptor.node_ids,
                                "tags": descriptor.tags,
                            },
                        }
                    )
                response = self._success(request_id, {"tools": tools})
                return None if is_notification else response

            if method in self.TOOLS_CALL_METHODS:
                function_name = params.get("name") or params.get("tool")
                if not function_name or not isinstance(function_name, str):
                    raise InvalidParamsError(
                        "tools/call requires string params.name"
                    )

                invocation = FunctionInvocation.from_arguments(
                    function_name=function_name,
                    arguments=params.get("arguments"),
                    node_id=params.get("node_id"),
                    load_balancing=params.get("load_balancing", False),
                )
                result = await runtime.execute_invocation(invocation)

                if isinstance(result, (dict, list, int, float, bool)) or result is None:
                    content = [{"type": "json", "json": result}]
                else:
                    content = [{"type": "text", "text": str(result)}]

                response = self._success(request_id, {"content": content})
                return None if is_notification else response

            if method == "ping":
                response = self._success(request_id, {"pong": True})
                return None if is_notification else response

            if is_notification:
                return None
            return self.method_not_found(
                request_id=request_id,
                protocol=ProtocolName.MCP.value,
                method=method,
                message="Unknown MCP method: {0}".format(method),
            )
        except Exception as exc:
            if is_notification:
                return None
            return self.error_from_exception(
                request_id=request_id,
                exc=exc,
                protocol=ProtocolName.MCP.value,
                method=method or None,
            )
