#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
High-level commander skill facade for MCP-driven robot deployment/operations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import Client, EasyRemoteClientRuntime, MCPGateway, RemoteSkill  # noqa: E402


class RobotCommanderSkill:
    """
    Agent-side facade: simple methods, MCP underneath.

    Intended usage (Claude Code / commander side):
    1) resolve target sandbox node by user capability
    2) install runtime robot skill remotely
    3) deploy mission and execute robot actions via MCP tools/call
    """

    def __init__(
        self,
        gateway_address: str,
        *,
        target_node_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
    ) -> None:
        self._gateway_address = str(gateway_address).strip() or "127.0.0.1:8085"
        self._target_node_id = str(target_node_id).strip() if target_node_id else None
        self._target_user_id = str(target_user_id).strip() if target_user_id else None

        self._client = Client(self._gateway_address)
        self._mcp = MCPGateway(runtime=EasyRemoteClientRuntime(self._gateway_address))
        self._request_seq = 0

    def _next_request_id(self, prefix: str) -> str:
        self._request_seq += 1
        return "{0}-{1}".format(prefix, self._request_seq)

    @staticmethod
    def _unwrap_mcp_result(response: Any, *, method: str) -> Any:
        if not isinstance(response, Mapping):
            raise RuntimeError("MCP response for '{0}' is invalid: {1}".format(method, response))

        error_obj = response.get("error")
        if isinstance(error_obj, Mapping):
            raise RuntimeError("MCP '{0}' failed: {1}".format(method, dict(error_obj)))

        result = response.get("result")
        if not isinstance(result, Mapping):
            return result

        content = result.get("content")
        if not isinstance(content, list):
            return dict(result)

        normalized: List[Any] = []
        for item in content:
            if not isinstance(item, Mapping):
                normalized.append(item)
                continue
            kind = str(item.get("type", "")).strip().lower()
            if kind == "json":
                normalized.append(item.get("json"))
            elif kind == "text":
                normalized.append(item.get("text"))
            else:
                normalized.append(dict(item))

        if len(normalized) == 1:
            return normalized[0]
        return normalized

    async def initialize(self) -> Dict[str, Any]:
        response = await self._mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id("init"),
                "method": "initialize",
            }
        )
        payload = self._unwrap_mcp_result(response, method="initialize")
        return payload if isinstance(payload, dict) else {"result": payload}

    async def list_tools(self) -> Dict[str, Any]:
        response = await self._mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id("tools-list"),
                "method": "tools/list",
            }
        )
        payload = self._unwrap_mcp_result(response, method="tools/list")
        return payload if isinstance(payload, dict) else {"result": payload}

    async def call_tool(
        self,
        tool_name: str,
        *,
        node_id: Optional[str],
        arguments: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Any:
        params: Dict[str, Any] = {
            "name": str(tool_name).strip(),
            "arguments": dict(arguments or {}),
        }
        if node_id:
            params["node_id"] = str(node_id).strip()
        if stream:
            params["stream"] = True

        response = await self._mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id("tools-call"),
                "method": "tools/call",
                "params": params,
            }
        )
        return self._unwrap_mcp_result(response, method="tools/call")

    def resolve_target_node_id(self) -> str:
        if self._target_node_id:
            return self._target_node_id

        if not self._target_user_id:
            raise ValueError("Provide target_node_id or target_user_id")

        matches = self._client.find_nodes(
            required_capabilities=["user:{0}".format(self._target_user_id)],
            required_functions=["device.install_remote_skill"],
        )
        if not matches:
            raise RuntimeError(
                "No online sandbox node found for user '{0}'".format(self._target_user_id)
            )

        matches.sort(
            key=lambda item: (
                float(item.get("current_load", 1.0)),
                str(item.get("node_id", "")),
            )
        )
        return str(matches[0]["node_id"])

    @staticmethod
    def _build_robot_skill_payload() -> Dict[str, Any]:
        skill = RemoteSkill.from_directory(
            Path(__file__).parent / "skills" / "robot-runtime-pack"
        )
        payload = skill.export_pipeline(as_json=False)
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected robot skill payload type")
        return payload

    async def install_runtime(self, *, node_id: str) -> Any:
        return await self.call_tool(
            "device.install_remote_skill",
            node_id=node_id,
            arguments={
                "skill_payload": self._build_robot_skill_payload(),
                "replace_existing_skill": True,
            },
        )

    async def run_decision_cycle(
        self,
        *,
        mission_id: str = "mission-robot-inspection",
        steps: Optional[List[str]] = None,
        action: str = "forward",
        distance_m: float = 1.5,
    ) -> Dict[str, Any]:
        target_node_id = self.resolve_target_node_id()
        mission_steps = [
            str(item).strip() for item in (steps or ["boot", "inspect", "report"]) if str(item).strip()
        ]

        initialize = await self.initialize()
        tools = await self.list_tools()
        install = await self.install_runtime(node_id=target_node_id)

        deploy = await self.call_tool(
            "user.robot.deploy_plan",
            node_id=target_node_id,
            arguments={
                "mission_id": str(mission_id).strip() or "mission-robot-inspection",
                "steps": mission_steps,
                "output_path": "robot-mission.json",
            },
        )
        set_mode = await self.call_tool(
            "user.robot.set_mode",
            node_id=target_node_id,
            arguments={
                "mode": "auto",
                "reason": "commander decision accepted",
            },
        )
        execute = await self.call_tool(
            "user.robot.execute_action",
            node_id=target_node_id,
            arguments={
                "action": str(action).strip() or "forward",
                "distance_m": float(distance_m),
                "turn_deg": 12.0,
            },
        )
        status = await self.call_tool(
            "user.robot.get_status",
            node_id=target_node_id,
            arguments={},
        )
        telemetry = await self.call_tool(
            "user.robot.stream_telemetry",
            node_id=target_node_id,
            arguments={
                "frame_count": 4,
                "interval_ms": 60,
            },
            stream=True,
        )

        return {
            "target_node_id": target_node_id,
            "target_user_id": self._target_user_id,
            "initialize": initialize,
            "tools_list_count": len(tools.get("tools", [])) if isinstance(tools, dict) else None,
            "install": install,
            "deploy": deploy,
            "set_mode": set_mode,
            "execute": execute,
            "status": status,
            "telemetry": telemetry,
        }
