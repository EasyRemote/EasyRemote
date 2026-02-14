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
│   ├── a2a_gateway_demo.py
│   └── easyremote_gateway_proxy_demo.py
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

### MCP/A2A 代理真实网关

文件：`examples/agent_route/easyremote_gateway_proxy_demo.py`

演示内容：
- 通过 `EasyRemoteClientRuntime` 把 EasyRemote 网关里的真实函数暴露成 MCP tools / A2A capabilities
- 用 `tools/list` / `agent.capabilities` 做在线能力发现
- （可选）用 `tools/call` / `task.execute` 直连指定 `node_id` 执行（适用于 CMP 能力管理端点）

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
7. `uv run python examples/agent_route/easyremote_gateway_proxy_demo.py`

## 5. 当前支持 vs 未来路线

- 当前可落地能力：见 `docs/zh/CORE_USE_CASES_AND_ROUTES.md`
- 未来应支持能力（Roadmap）：同文件第 4 节
