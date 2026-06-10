#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Commander-side entrypoint for MCP-driven robot deployment/operations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from commander_skill import RobotCommanderSkill  # noqa: E402


async def main() -> None:
    gateway = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8085")
    target_node_id = os.getenv("TARGET_USER_NODE_ID")
    target_user_id = os.getenv("TARGET_USER_ID", "demo-user")

    mission_id = os.getenv("MISSION_ID", "mission-robot-inspection")
    mission_steps = [
        piece.strip()
        for piece in os.getenv("MISSION_STEPS", "boot,inspect,report").split(",")
        if piece.strip()
    ]
    action = os.getenv("ROBOT_ACTION", "forward")
    distance_m = float(os.getenv("ROBOT_DISTANCE_M", "1.5"))

    commander = RobotCommanderSkill(
        gateway,
        target_node_id=target_node_id,
        target_user_id=target_user_id,
    )
    result = await commander.run_decision_cycle(
        mission_id=mission_id,
        steps=mission_steps,
        action=action,
        distance_m=distance_m,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
