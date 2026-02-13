# EasyRemote 核心示例（按路线分层）

> 仅保留与当前实现一致、可直接落地的示例。  
> Author: Silan Hu (silan.hu@u.nus.edu)

## 清理原则

- 删除了使用失效参数和伪能力的历史示例（如 `vps_address`、`streaming`、`interval` 等）。
- 删除重复场景，避免“看起来很多，实际不可运行”的示例膨胀。
- 只保留两条核心路线：`Agent 协议路线` 与 `人类编码装饰器路线`。

## 当前支持（可落地）

### 1. Agent 协议路线（MCP/A2A）

- `agent_route/mcp_gateway_demo.py`
- `agent_route/a2a_gateway_demo.py`
- `agent_route/protocol_service_quickstart.py`
- `agent_route/skill_pipeline_quickstart.py`
- `agent_route/user_remote_agent_service_quickstart.py`
- `agent_route/user_device_dynamic_camera_skill.py`

覆盖能力：
- MCP: `initialize`、`tools/list`、`tools/call`、通知请求、批量请求、错误对象一致性。
- A2A: `agent.capabilities`、`task.send` / `task.execute`、通知请求、批量请求、错误对象一致性。

### 2. 人类编码装饰器路线（Decorator）

- `decorator_route/server.py`
- `decorator_route/compute_node.py`
- `decorator_route/client.py`
- `decorator_route/remote_stream_quickstart.py`

覆盖能力：
- `@node.register` 注册函数。
- `@remote` 远程调用（指定节点 + 负载均衡模式）。
- `@remote(stream=True)` 流式结果消费（同步 `for` / 异步 `async for`）。
- Client/Gateway 双向流式 RPC（支持 cancel 控制帧）。
- 节点有界执行队列 + worker 池，避免过载。
- 同步调用入口的工程化封装。

## 运行方式（uv 管理）

- MCP Demo: `uv run python examples/agent_route/mcp_gateway_demo.py`
- A2A Demo: `uv run python examples/agent_route/a2a_gateway_demo.py`
- 协议服务快速封装（装饰器 + OOP 模版）：`uv run python examples/agent_route/protocol_service_quickstart.py`
- Skill 化远程能力导出与跨设备管道调用：`uv run python examples/agent_route/skill_pipeline_quickstart.py`
- 用户侧远程 Agent（运行时安装技能 + 语言偏好）：`uv run python examples/agent_route/user_remote_agent_service_quickstart.py`
- 远程 Agent 动态下发“拍照/录视频”能力并在用户设备注册函数：`uv run python examples/agent_route/user_device_dynamic_camera_skill.py`
- Decorator 路线：
1. `uv run python examples/decorator_route/server.py`
2. `uv run python examples/decorator_route/compute_node.py`
3. `uv run python examples/decorator_route/client.py`
- `@remote` 稳定服务 + 流式快速演示：`uv run python examples/decorator_route/remote_stream_quickstart.py`

## 未来应支持（建议新增示例）

- MCP `resources` / `prompts` 全量能力与流式传输。
- A2A 长任务生命周期（queued/running/partial/completed/cancelled）。
- A2A-MCP 混合编排（A2A 任务内部调用 MCP tools）。
- 装饰器签名约束自动导出为协议层 schema（减少重复定义）。
