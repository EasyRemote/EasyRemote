# EasyRemote 示例（聚焦核心落地）

Author: Silan Hu (silan.hu@u.nus.edu)

## 示例路线总览

本项目当前只保留两条核心路线：

- Agent 路线：通过 MCP/A2A 协议接入。
- 人类编码路线：通过 `@node.register` + `@remote` 装饰器接入。

示例目录：

```text
examples/
├── README.md
├── agent_route/
│   ├── mcp_gateway_demo.py
│   └── a2a_gateway_demo.py
└── decorator_route/
    ├── server.py
    ├── compute_node.py
    └── client.py
```

## 1. Agent 路线（MCP/A2A）

### MCP 示例

文件：`examples/agent_route/mcp_gateway_demo.py`

演示内容：
- `initialize`
- `tools/list`
- `tools/call`
- 通知请求（无 `id`）
- 批量请求（含通知和错误响应）

### A2A 示例

文件：`examples/agent_route/a2a_gateway_demo.py`

演示内容：
- `agent.capabilities`
- `task.execute`
- `task.send` 通知请求
- 批量请求（含通知）
- 参数错误时的标准错误对象

## 2. 人类编码路线（Decorator）

文件：
- `examples/decorator_route/server.py`
- `examples/decorator_route/compute_node.py`
- `examples/decorator_route/client.py`

演示内容：
- Server 网关启动
- ComputeNode 注册函数
- `@remote` 直接节点调用
- `@remote` 负载均衡调用

## 3. 先跑哪个？

建议顺序：
1. 先跑 `decorator_route`，确认基础远程调用链路。
2. 再跑 `agent_route`，验证协议入口和 JSON-RPC 行为。

## 4. 运行命令（uv 管理）

1. `uv sync`
2. `uv run python examples/decorator_route/server.py`
3. `uv run python examples/decorator_route/compute_node.py`
4. `uv run python examples/decorator_route/client.py`
5. `uv run python examples/agent_route/mcp_gateway_demo.py`
6. `uv run python examples/agent_route/a2a_gateway_demo.py`

## 5. 当前支持 vs 未来路线

- 当前可落地能力：见 `docs/zh/CORE_USE_CASES_AND_ROUTES.md`
- 未来应支持能力（Roadmap）：同文件第 4 节
