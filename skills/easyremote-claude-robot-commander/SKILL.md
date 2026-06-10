---
name: easyremote-claude-robot-commander
description: Commander-side skill for Claude Code. Uses MCP tools/call over EasyRemote to deploy runtime robot capabilities onto client-sandbox nodes and execute robot actions with minimal boilerplate.
---

# EasyRemote Claude Robot Commander Skill

Use this skill when you need a commander-decision agent to deploy and operate remote robots on client-sandbox nodes through MCP.

## Role Model

- Commander side (agent): decides mission + actions
- Client-sandbox side (user node): receives runtime skill install and executes robot abilities

## Minimal Usage

```python
from pathlib import Path
import sys

project_dir = Path("gallery/projects/07_claude_code_robot_commander_mcp").resolve()
sys.path.insert(0, str(project_dir))

from commander_skill import RobotCommanderSkill

commander = RobotCommanderSkill(
    gateway_address="127.0.0.1:8085",
    target_user_id="demo-user",
)

result = await commander.run_decision_cycle(
    mission_id="mission-42",
    steps=["boot", "inspect", "report"],
    action="forward",
    distance_m=1.2,
)
```

## What It Wraps

- MCP `initialize` and `tools/list`
- MCP `tools/call` for:
  - `device.install_remote_skill`
  - `user.robot.deploy_plan`
  - `user.robot.set_mode`
  - `user.robot.execute_action`
  - `user.robot.get_status`
  - `user.robot.stream_telemetry`

## Runtime Skill Payload

Payload source:
- `gallery/projects/07_claude_code_robot_commander_mcp/skills/robot-runtime-pack/skill.md`

The payload includes transferred runtime code so the client-sandbox node can execute without preloading all robot logic.
