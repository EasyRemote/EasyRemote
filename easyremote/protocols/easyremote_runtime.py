#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EasyRemote-backed ProtocolRuntime implementations.

These runtimes allow MCP/A2A JSON-RPC requests to proxy into an EasyRemote
gateway using the standard synchronous Client APIs.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from .models import FunctionDescriptor, FunctionInvocation
from .runtime import ProtocolRuntime


class EasyRemoteClientRuntime(ProtocolRuntime):
    """
    ProtocolRuntime that proxies tool/task execution to an EasyRemote gateway.

    This is intended for "agent-side" usage where the agent prefers MCP/A2A
    JSON-RPC envelopes but wants to execute real distributed functions managed
    by an EasyRemote gateway.
    """

    def __init__(
        self,
        gateway_address: str,
        *,
        client: Optional[Any] = None,
        runtime_name: str = "easyremote-gateway-proxy",
        runtime_version: Optional[str] = None,
    ) -> None:
        gateway = str(gateway_address).strip()
        if not gateway:
            raise ValueError("gateway_address cannot be empty")
        self.gateway_address = gateway

        if runtime_version is None:
            try:
                from .._version import __version__ as _easyremote_version
            except Exception:
                _easyremote_version = "unknown"
            runtime_version = _easyremote_version

        self.runtime_name = str(runtime_name).strip() or "easyremote-gateway-proxy"
        self.runtime_version = str(runtime_version).strip() or "unknown"

        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from ..core.nodes.client import Client

        self._client = Client(self.gateway_address)
        return self._client

    async def list_functions(self) -> List[FunctionDescriptor]:
        """
        List all functions currently visible from the gateway.

        Note: gateway node listing only provides function names. Per-function
        metadata (description/tags) may be unavailable unless you expose a
        custom metadata endpoint (e.g. CMP `device.list_node_functions`).
        """
        client = self._get_client()
        nodes = await asyncio.to_thread(client.list_nodes)

        index: Dict[str, Dict[str, Any]] = {}
        for node in nodes:
            node_id = str(node.get("node_id", "")).strip()
            if not node_id:
                continue

            fn_names = node.get("functions", []) or []
            if not isinstance(fn_names, list):
                continue

            for fn_name in fn_names:
                name = str(fn_name).strip()
                if not name:
                    continue
                entry = index.get(name)
                if entry is None:
                    entry = {
                        "node_ids": set(),
                    }
                    index[name] = entry
                cast_ids: Set[str] = entry["node_ids"]
                cast_ids.add(node_id)

        descriptors: List[FunctionDescriptor] = []
        for name in sorted(index.keys()):
            node_ids = sorted(index[name]["node_ids"])
            descriptors.append(
                FunctionDescriptor(
                    name=name,
                    description="",
                    node_ids=node_ids,
                    tags=[],
                    metadata={
                        "gateway_address": self.gateway_address,
                        "node_count": len(node_ids),
                    },
                )
            )
        return descriptors

    @staticmethod
    def _normalize_optional_str_list(value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            return None
        items: List[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized:
                items.append(normalized)
        return items or None

    def _build_execution_context(self, invocation: FunctionInvocation) -> Tuple[Any, Optional[str]]:
        from ..core.nodes.client import ExecutionContext, ExecutionStrategy

        function_name = str(invocation.function_name).strip()
        if not function_name:
            raise ValueError("function_name cannot be empty")

        # Direct node targeting always wins.
        if invocation.node_id:
            node_id = str(invocation.node_id).strip()
            if not node_id:
                raise ValueError("node_id cannot be empty")
            return (
                ExecutionContext(
                    function_name=function_name,
                    strategy=ExecutionStrategy.DIRECT_TARGET,
                    preferred_node_ids=[node_id],
                    enable_caching=False,
                ),
                node_id,
            )

        # Load-balanced execution.
        if invocation.load_balancing:
            requirements = None
            cost_limit = None
            timeout_ms = None
            strategy = ExecutionStrategy.LOAD_BALANCED
            preferred_node_ids = None
            excluded_node_ids = None

            if isinstance(invocation.load_balancing, dict):
                requirements = invocation.load_balancing.get("requirements")
                cost_limit = invocation.load_balancing.get("cost_limit")

                raw_timeout_ms = invocation.load_balancing.get("timeout_ms")
                raw_timeout_seconds = invocation.load_balancing.get("timeout_seconds")
                if raw_timeout_ms is not None:
                    try:
                        timeout_ms = float(raw_timeout_ms)
                    except Exception:
                        timeout_ms = None
                elif raw_timeout_seconds is not None:
                    try:
                        timeout_ms = float(raw_timeout_seconds) * 1000.0
                    except Exception:
                        timeout_ms = None

                raw_strategy = invocation.load_balancing.get("strategy")
                if raw_strategy is not None:
                    try:
                        strategy = ExecutionStrategy(str(raw_strategy).strip())
                    except Exception:
                        strategy = ExecutionStrategy.LOAD_BALANCED

                preferred_node_ids = self._normalize_optional_str_list(
                    invocation.load_balancing.get("preferred_node_ids")
                )
                excluded_node_ids = self._normalize_optional_str_list(
                    invocation.load_balancing.get("excluded_node_ids")
                )
            elif isinstance(invocation.load_balancing, str):
                try:
                    strategy = ExecutionStrategy(str(invocation.load_balancing).strip())
                except Exception:
                    strategy = ExecutionStrategy.LOAD_BALANCED

            return (
                ExecutionContext(
                    function_name=function_name,
                    strategy=strategy,
                    requirements=requirements if isinstance(requirements, dict) else None,
                    cost_limit=float(cost_limit) if isinstance(cost_limit, (int, float)) else None,
                    timeout_ms=timeout_ms,
                    preferred_node_ids=preferred_node_ids,
                    excluded_node_ids=excluded_node_ids,
                    enable_caching=False,
                ),
                None,
            )

        # No node_id and no load balancing: pick a concrete node deterministically
        # (least loaded) and run a direct call.
        client = self._get_client()
        resolved_node_id = client.resolve_node_id(required_functions=[function_name])
        return (
            ExecutionContext(
                function_name=function_name,
                strategy=ExecutionStrategy.DIRECT_TARGET,
                preferred_node_ids=[resolved_node_id],
                enable_caching=False,
            ),
            resolved_node_id,
        )

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        client = self._get_client()
        context, _resolved_node = await asyncio.to_thread(
            self._build_execution_context, invocation
        )

        if invocation.stream:
            def _collect() -> List[Any]:
                iterator = client.stream_with_context(
                    context,
                    *invocation.args,
                    **invocation.kwargs,
                )
                return list(iterator)

            return await asyncio.to_thread(_collect)

        execution_result = await asyncio.to_thread(
            client.execute_with_context,
            context,
            *invocation.args,
            **invocation.kwargs,
        )
        return execution_result.result


__all__ = [
    "EasyRemoteClientRuntime",
]

