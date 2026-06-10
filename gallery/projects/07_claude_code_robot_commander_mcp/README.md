# 07 Claude Code Robot Commander (MCP)

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

这是一个全新案例：
- 用户在 **Claude Code** 安装一个 commander Skill（决策端）
- Skill 通过 **MCP tools/call** 调用 EasyRemote 网关
- 远程向用户的 **client-sandbox** 节点下发机器人 runtime skill 并立即执行部署/操作

对应角色：
- `agent / commander-decision`：`commander_client.py` + `commander_skill.py`
- `client-sandbox`：`client_sandbox_node.py`

## 设计目标

- 复用 EasyRemote 现有实体：`RemoteSkill`、`UserDeviceCapabilityHost`、`EasyRemoteClientRuntime`、`MCPGateway`
- 业务调用高度封装：上层只写“部署任务 + 执行动作”，底层自动走 MCP
- 低代码和高通用：不依赖特定机器人 SDK，先用 sandbox/runtime 模块抽象动作

## 文件

- `server.py`: 网关（默认 8085）
- `client_sandbox_node.py`: 用户 client-sandbox 节点（动态能力安装入口）
- `commander_skill.py`: 高封装 commander Skill（安装、部署、操作全流程）
- `commander_client.py`: commander 入口脚本
- `skills/robot-runtime-pack`: 下发到 client-sandbox 的 runtime skill payload
- `sandbox/robot_actions.py`: 本地 sandbox 动作回退（可选）

## 快速运行

1. `uv run python gallery/projects/07_claude_code_robot_commander_mcp/server.py`
2. `USER_ID=demo-user uv run python gallery/projects/07_claude_code_robot_commander_mcp/client_sandbox_node.py`
3. `TARGET_USER_ID=demo-user uv run python gallery/projects/07_claude_code_robot_commander_mcp/commander_client.py`

或一键：
- `bash gallery/projects/07_claude_code_robot_commander_mcp/run_demo.sh`

## Claude Code 侧最简调用（Commander）

`commander_skill.py` 已经把 MCP 调用封装为高层方法。外部只要：

```python
commander = RobotCommanderSkill("127.0.0.1:8085", target_user_id="demo-user")
result = await commander.run_decision_cycle(
    mission_id="mission-42",
    steps=["boot", "inspect", "report"],
    action="forward",
    distance_m=1.2,
)
```

这段会自动完成：
- 目标节点解析（按 `user:<id>` capability）
- `device.install_remote_skill` 远程下发
- `user.robot.deploy_plan` / `user.robot.set_mode` / `user.robot.execute_action` / `user.robot.get_status`
- `user.robot.stream_telemetry` 流式采样

## 安全说明（Demo 默认放宽）

- 默认启用 `allow_transferred_code=True` 和 `EASYREMOTE_AUTO_CONSENT=1`
- 生产建议：
  - `EASYREMOTE_AUTO_CONSENT=0`
  - 对 skill payload 与 runtime modules 做签名/来源校验
  - 收紧 `UserDeviceCapabilityHost` 的 runtime 模块大小和数量阈值

## 一键命令

- `cd gallery/projects/07_claude_code_robot_commander_mcp && make help`
