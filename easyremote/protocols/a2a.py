#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A2A protocol adapter for EasyRemote.

This adapter offers a practical A2A-style command surface for agent capability
discovery and distributed task execution.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from typing import Any, Dict, Mapping, Optional

from .adapter import InvalidParamsError, JsonRpcProtocolAdapter
from .models import FunctionInvocation, ProtocolName
from .runtime import ProtocolRuntime


class A2AProtocolAdapter(JsonRpcProtocolAdapter):
    """
    A2A-compatible adapter.

    Supported methods:
    - agent.capabilities
    - task.send
    - task.execute
    - ping
    """

    CAPABILITIES_METHODS = {
        "agent.capabilities",
        "agent/capabilities",
        "capabilities",
    }
    TASK_METHODS = {
        "task.send",
        "task.execute",
        "task/send",
        "task/execute",
        "tasks.send",
        "tasks.execute",
    }

    @property
    def protocol(self) -> ProtocolName:
        return ProtocolName.A2A

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

            if method in self.CAPABILITIES_METHODS:
                descriptors = await runtime.list_functions()
                capabilities = []
                for descriptor in descriptors:
                    capabilities.append(
                        {
                            "name": descriptor.name,
                            "description": descriptor.description
                            or "EasyRemote distributed capability",
                            "nodes": descriptor.node_ids,
                            "tags": descriptor.tags,
                            "metadata": descriptor.metadata,
                        }
                    )
                response = self._success(
                    request_id,
                    {
                        "agent": {
                            "name": "easyremote-gateway",
                            "protocol": "a2a",
                            "capabilities": capabilities,
                        }
                    },
                )
                return None if is_notification else response

            if method in self.TASK_METHODS:
                invocation = self._parse_invocation(params)
                result = await runtime.execute_invocation(invocation)
                task_id = params.get("task_id")
                if not task_id and isinstance(params.get("task"), Mapping):
                    task_id = params["task"].get("id")
                task_id = task_id or request_id

                response = self._success(
                    request_id,
                    {
                        "task": {
                            "id": task_id,
                            "status": "completed",
                            "output": result,
                        }
                    },
                )
                return None if is_notification else response

            if method == "ping":
                response = self._success(request_id, {"pong": True})
                return None if is_notification else response

            if is_notification:
                return None
            return self.method_not_found(
                request_id=request_id,
                protocol=ProtocolName.A2A.value,
                method=method,
                message="Unknown A2A method: {0}".format(method),
            )
        except Exception as exc:
            if is_notification:
                return None
            return self.error_from_exception(
                request_id=request_id,
                exc=exc,
                protocol=ProtocolName.A2A.value,
                method=method or None,
            )

    def _parse_invocation(self, params: Mapping[str, Any]) -> FunctionInvocation:
        task_payload = params.get("task")
        task_data: Dict[str, Any]
        if isinstance(task_payload, Mapping):
            task_data = dict(task_payload)
        elif task_payload is None:
            task_data = dict(params)
        else:
            raise InvalidParamsError("task payload must be an object")

        function_name = (
            task_data.get("function")
            or task_data.get("name")
            or task_data.get("tool")
        )
        if not function_name or not isinstance(function_name, str):
            raise InvalidParamsError(
                "task.send/task.execute requires task.function (or name/tool)"
            )

        arguments = task_data.get("input", task_data.get("arguments"))
        node_id = task_data.get("node_id") or task_data.get("target_node")
        load_balancing = task_data.get("load_balancing", False)

        return FunctionInvocation.from_arguments(
            function_name=function_name,
            arguments=arguments,
            node_id=node_id,
            load_balancing=load_balancing,
        )
