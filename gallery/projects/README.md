# Gallery Projects

Author: Silan Hu (silan.hu@u.nus.edu)

## Purpose

`gallery/projects/` now keeps scenario directories, not old implementation code. Each subdirectory README answers one question: if this project is rebuilt, which real usage scenario should it serve, which concrete problem should it solve, and what target outcome should the user get?

For currently runnable code, see [`../../examples/README.md`](../../examples/README.md). This directory no longer provides Makefiles, script entrypoints, or smoke test instructions.

## Project Index

| Directory | Scenario | Description |
|---|---|---|
| [`00_basic_remote_math`](00_basic_remote_math/README.md) | K4 Demo-as-API | Uses the smallest function case to explain how a local function becomes a demoable remote capability |
| [`01_team_gpu_pool_load_balancing`](01_team_gpu_pool_load_balancing/README.md) | K1 Private AI Inference Hub | Uses a team GPU pool to explain multi-node capability sharing and load distribution |
| [`02_mcp_tool_mesh`](02_mcp_tool_mesh/README.md) | K2 Agent Capability Backend | Uses an enterprise tool mesh to explain how agents discover and call organizational capabilities |
| [`03_a2a_incident_copilot`](03_a2a_incident_copilot/README.md) | K3 A2A Incident Copilot Network | Uses an incident copilot to explain how operations actions can be orchestrated by agents |
| [`04_function_marketplace`](04_function_marketplace/README.md) | K5 Internal Function Marketplace | Uses cross-team function reuse to explain the value of a capability catalog |
| [`05_local_data_residency_ai`](05_local_data_residency_ai/README.md) | K6 Local Data Residency AI | Uses sensitive data processing to explain why computation should move toward the data |
| [`06_runtime_device_capability_injection`](06_runtime_device_capability_injection/README.md) | K9 Runtime Device Capability Injection | Uses camera, video, and streaming actions to explain on-demand user-device capability installation |
| [`07_claude_code_robot_commander_mcp`](07_claude_code_robot_commander_mcp/README.md) | K10 Claude Code Robot Commander | Uses a commander skill to explain how an agent remotely deploys and operates device capabilities |

## Writing Rule

Each project README uses the same structure:

- Usage scenario
- Concrete use case
- Current problem
- Intent
- Target outcome

This keeps the gallery from becoming another code index. It should first clarify demand and product judgment, then decide whether an implementation is worth rebuilding.
