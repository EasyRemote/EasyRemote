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

覆盖能力：
- MCP: `initialize`、`tools/list`、`tools/call`、通知请求、批量请求、错误对象一致性。
- A2A: `agent.capabilities`、`task.send` / `task.execute`、通知请求、批量请求、错误对象一致性。

### 2. 人类编码装饰器路线（Decorator）

- `decorator_route/server.py`
- `decorator_route/compute_node.py`
- `decorator_route/client.py`

覆盖能力：
- `@node.register` 注册函数。
- `@remote` 远程调用（指定节点 + 负载均衡模式）。
- 同步调用入口的工程化封装。

## 运行方式（uv 管理）

- MCP Demo: `uv run python examples/agent_route/mcp_gateway_demo.py`
- A2A Demo: `uv run python examples/agent_route/a2a_gateway_demo.py`
- Decorator 路线：
1. `uv run python examples/decorator_route/server.py`
2. `uv run python examples/decorator_route/compute_node.py`
3. `uv run python examples/decorator_route/client.py`

## 未来应支持（建议新增示例）

- MCP `resources` / `prompts` 全量能力与流式传输。
- A2A 长任务生命周期（queued/running/partial/completed/cancelled）。
- A2A-MCP 混合编排（A2A 任务内部调用 MCP tools）。
- 装饰器签名约束自动导出为协议层 schema（减少重复定义）。
