# EasyRemote Examples (Core Paths)

Author: Silan Hu (silan.hu@u.nus.edu)

## Supported example routes

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

## Route A: Agent integration (MCP/A2A)

- `examples/agent_route/mcp_gateway_demo.py`
- `examples/agent_route/a2a_gateway_demo.py`
- `examples/agent_route/easyremote_gateway_proxy_demo.py` (proxy a real EasyRemote gateway)

## Route B: Human coding with decorators

- `examples/decorator_route/server.py`
- `examples/decorator_route/compute_node.py`
- `examples/decorator_route/client.py`

## Run with uv

1. `uv sync`
2. `uv run python examples/decorator_route/server.py`
3. `uv run python examples/decorator_route/compute_node.py`
4. `uv run python examples/decorator_route/client.py`
5. `uv run python examples/agent_route/mcp_gateway_demo.py`
6. `uv run python examples/agent_route/a2a_gateway_demo.py`
7. `uv run python examples/agent_route/easyremote_gateway_proxy_demo.py`

## Current vs future

- Implemented scope: `docs/zh/CORE_USE_CASES_AND_ROUTES.md`
- MCP scope: `docs/ai/mcp-integration.md`
- A2A scope: `docs/ai/a2a-integration.md`
