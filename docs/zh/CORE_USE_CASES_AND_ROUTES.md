# EasyRemote 实际业务落地与路线分层（A2A/MCP + Decorator）

Author: Silan Hu (silan.hu@u.nus.edu)

## 1. 目标与清理标准

本轮只保留“当前代码已实现并可验证”的能力，不再保留不可运行的概念性炫技案例。

清理标准：
- 示例必须与当前 API 一致。
- 协议行为必须可通过测试验证（批量请求、通知请求、错误对象细节）。
- 文档中的“当前支持”与代码保持一一对应。

## 2. 当前系统已支持的用例（可落地）

### 路线 A：Agent 使用 MCP/A2A 协议

#### A1. MCP 工具网关（Agent Tool Calling）

目标用户：Agent 开发者（MCP 客户端）。

已支持能力：
- `initialize` / `mcp.initialize`
- `tools/list` / `mcp.tools/list`
- `tools/call` / `mcp.tools/call`
- `ping`
- JSON-RPC 通知请求（无 `id`）不返回响应
- JSON-RPC 批量请求（含混合通知）
- 统一错误对象结构：`error.code` + `error.message` + `error.data`

对应实现：
- `easyremote/protocols/mcp.py`
- `easyremote/protocols/gateway.py`
- `tests/test_protocol_adapters.py`
- 示例：`examples/agent_route/mcp_gateway_demo.py`

#### A2. A2A 任务路由（Agent Capability + Task Execution）

目标用户：Agent-to-Agent 协作系统。

已支持能力：
- `agent.capabilities` / `agent/capabilities` / `capabilities`
- `task.send` / `task.execute` 及其别名
- `ping`
- JSON-RPC 通知请求（无 `id`）不返回响应
- JSON-RPC 批量请求（含混合通知）
- 统一错误对象结构：`error.code` + `error.message` + `error.data`
- 任务 `task_id` 兼容回退（`params.task_id` -> `params.task.id` -> request id）

对应实现：
- `easyremote/protocols/a2a.py`
- `easyremote/protocols/gateway.py`
- `tests/test_protocol_adapters.py`
- 示例：`examples/agent_route/a2a_gateway_demo.py`

### 路线 B：人类编码使用 Decorator

#### B1. 远程函数暴露与调用

目标用户：Python 工程团队（业务函数远程化）。

已支持能力：
- `@node.register` 暴露函数
- `@remote` 调用远程函数
- 直接节点调用与负载均衡调用
- 无本地 Server 时自动回退到默认 Client / 环境变量网关

对应实现：
- `easyremote/decorators.py`
- `easyremote/core/nodes/compute_node.py`
- `easyremote/core/nodes/server.py`
- 示例：
  - `examples/decorator_route/server.py`
  - `examples/decorator_route/compute_node.py`
  - `examples/decorator_route/client.py`

## 3. 分层组织（按职责，而不是按“酷炫程度”）

### L0 执行层（Execution Plane）

- 节点注册、函数执行、负载均衡、序列化。
- 核心对象：`Server`、`ComputeNode`、`Client`。

### L1 协议层（Protocol Plane）

- 对外协议适配与 JSON-RPC 规范对齐。
- 核心对象：`ProtocolGateway`、`MCPProtocolAdapter`、`A2AProtocolAdapter`。

### L1.5 开发者入口层（Developer API Plane）

- 人类开发者入口：Decorator（`@node.register`, `@remote`）。
- Agent 开发者入口：MCP/A2A JSON-RPC 请求。

### L2 业务编排层（Orchestration Plane）

- 业务工作流、策略、权限、审计、成本控制。
- 当前由上层应用实现，EasyRemote 提供执行与协议基础设施。

## 4. 未来应该支持的用例（明确为 Roadmap，不冒充现状）

### R1. MCP 完整规范扩展

- `resources/*`、`prompts/*`、订阅与变更通知。
- 多传输协议适配（stdio/http/websocket）的一致行为测试。

### R2. A2A 长任务生命周期

- `queued/running/partial/completed/failed/cancelled` 状态机。
- 任务取消、重试策略、回调通知语义。

### R3. 协议间协同编排

- A2A 任务内部可调用 MCP tools。
- 统一 trace-id 与错误模型跨协议透传。

### R4. Decorator 与协议 schema 自动对齐

- 从 Python 类型注解自动导出 MCP/A2A 可消费的输入输出 schema。
- 减少手工重复建模与协议漂移。

## 5. 本次清理结果（仓库侧）

- 已移除历史冗余和失效示例，保留核心、可运行、可验证路径。
- 新示例集中到 `examples/agent_route/` 与 `examples/decorator_route/`。
- 示例索引更新为 `examples/README.md`，避免“文档说支持、代码跑不通”的偏差。

## 6. 杀手应用栏目（Gallery）

- 业务场景总览：`gallery/README.md`
- 杀手应用详单：`gallery/killer_apps.md`
- 项目化模板索引：`gallery/projects/README.md`
- 规则：Gallery 只收录“可验证价值路径”，并明确标记“当前可落地 / Roadmap”。
