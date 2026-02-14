#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP protocol adapter for EasyRemote.

This adapter translates MCP-style requests into EasyRemote runtime invocations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, List, Mapping, Optional

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

    @staticmethod
    def _runtime_identity(runtime: ProtocolRuntime) -> Dict[str, str]:
        name = str(getattr(runtime, "runtime_name", "easyremote")).strip()
        version = str(getattr(runtime, "runtime_version", "0.1.4")).strip()
        return {
            "name": name or "easyremote",
            "version": version or "0.1.4",
        }

    @staticmethod
    async def _collect_chunks(value: Any) -> List[Any]:
        if hasattr(value, "__aiter__"):
            chunks: List[Any] = []
            async for item in value:
                chunks.append(item)
            return chunks

        if hasattr(value, "__iter__") and not isinstance(
            value,
            (str, bytes, bytearray, Mapping),
        ):
            return list(value)

        return [value]

    async def _normalize_call_result(
        self,
        result: Any,
        stream_requested: bool,
    ) -> List[Dict[str, Any]]:
        if stream_requested:
            chunks = await self._collect_chunks(result)
            return [
                {
                    "type": "json",
                    "json": {
                        "mode": "stream",
                        "chunks": chunks,
                        "chunkCount": len(chunks),
                    },
                }
            ]

        if hasattr(result, "__aiter__") or (
            hasattr(result, "__iter__")
            and not isinstance(result, (str, bytes, bytearray, Mapping))
        ):
            result = await self._collect_chunks(result)

        if isinstance(result, (dict, list, int, float, bool)) or result is None:
            return [{"type": "json", "json": result}]
        return [{"type": "text", "text": str(result)}]

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
            runtime_identity = self._runtime_identity(runtime)

            if method in self.INITIALIZE_METHODS:
                response = self._success(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": runtime_identity,
                        "capabilities": {
                            "tools": {"listChanged": False, "streaming": True},
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
                    stream=bool(params.get("stream")),
                )
                result = await runtime.execute_invocation(invocation)
                content = await self._normalize_call_result(
                    result=result,
                    stream_requested=bool(params.get("stream")),
                )

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
