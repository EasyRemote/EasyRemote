# MCP Integration Guide (Implemented Scope)

Author: Silan Hu (silan.hu@u.nus.edu)

## 1. What is implemented now

EasyRemote MCP support is implemented as a JSON-RPC adapter on top of `ProtocolGateway`.

Implemented methods:
- `initialize`
- `mcp.initialize`
- `tools/list`
- `mcp.tools/list`
- `tools/call`
- `mcp.tools/call`
- `ping`

Implemented protocol behaviors:
- Requests must include `jsonrpc: "2.0"` (strict JSON-RPC 2.0 envelope).
- JSON-RPC notifications (requests without `id`) return no response.
- JSON-RPC batch requests are supported.
- Error object shape is consistent:
  - `error.code`
  - `error.message`
  - `error.data.protocol`
  - `error.data.method`
  - `error.data.error_type`

Core files:
- `easyremote/protocols/mcp.py`
- `easyremote/protocols/adapter.py`
- `easyremote/protocols/gateway.py`
- `easyremote/mcp/__init__.py`

Conformance tests:
- `tests/test_protocol_adapters.py`

## 2. Minimal usage

### 2.1 Zero-boilerplate (recommended)

```python
import asyncio
from easyremote.mcp import MCPService

service = MCPService(name="tool-mesh", version="1.0.0")

@service.capability(description="Add two numbers", tags=("math",))
def add_numbers(a, b):
    return a + b

async def main():
    response = await service.handle_mcp(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "add_numbers",
                "arguments": {"a": 2, "b": 3},
            },
        }
    )
    print(response)

asyncio.run(main())
```

### 2.2 Custom runtime (advanced)

```python
import asyncio

from easyremote.mcp import MCPGateway
from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class Runtime(ProtocolRuntime):
    async def list_functions(self):
        return [FunctionDescriptor(name="add_numbers", node_ids=["node-1"])]

    async def execute_invocation(self, invocation: FunctionInvocation):
        return invocation.kwargs["a"] + invocation.kwargs["b"]


async def main():
    gateway = MCPGateway(runtime=Runtime())

    response = await gateway.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "add_numbers",
                "arguments": {"a": 2, "b": 3},
            },
        }
    )
    print(response)


asyncio.run(main())
```

### 2.3 Proxy an EasyRemote gateway (agent-side)

Use `EasyRemoteClientRuntime` to expose *real* gateway functions as MCP tools.

```python
import asyncio

from easyremote import EasyRemoteClientRuntime
from easyremote.mcp import MCPGateway


async def main():
    runtime = EasyRemoteClientRuntime("127.0.0.1:8080")
    gateway = MCPGateway(runtime=runtime)

    tools = await gateway.handle_request(
        {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
    )
    print(tools)

    # Call a specific node function (example: CMP install endpoint).
    # await gateway.handle_request(
    #     {
    #         "jsonrpc": "2.0",
    #         "id": "call-1",
    #         "method": "tools/call",
    #         "params": {
    #             "name": "device.list_node_functions",
    #             "node_id": "user-device-demo-user",
    #             "arguments": {},
    #         },
    #     }
    # )


asyncio.run(main())
```

## 3. Not implemented yet (roadmap)

- MCP `resources/*` methods.
- MCP `prompts/*` methods.
- Transport adapters beyond the in-process gateway usage pattern.
