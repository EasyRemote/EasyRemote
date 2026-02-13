# A2A Integration Guide (Implemented Scope)

Author: Silan Hu (silan.hu@u.nus.edu)

## 1. What is implemented now

EasyRemote A2A support is implemented as a JSON-RPC adapter on top of `ProtocolGateway`.

Implemented methods:
- `agent.capabilities`
- `agent/capabilities`
- `capabilities`
- `task.send`
- `task.execute`
- `task/send`
- `task/execute`
- `tasks.send`
- `tasks.execute`
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
- Task id fallback:
  - `params.task_id`
  - `params.task.id`
  - request `id`

Core files:
- `easyremote/protocols/a2a.py`
- `easyremote/protocols/adapter.py`
- `easyremote/protocols/gateway.py`
- `easyremote/a2a/__init__.py`

Conformance tests:
- `tests/test_protocol_adapters.py`

## 2. Minimal usage

### 2.1 Zero-boilerplate (recommended)

```python
import asyncio
from easyremote.a2a import A2AService

service = A2AService(name="incident-agent", version="1.0.0")

@service.capability(description="Echo payload")
def echo(payload):
    return payload

async def main():
    response = await service.handle_a2a(
        {
            "jsonrpc": "2.0",
            "id": "task-1",
            "method": "task.execute",
            "params": {
                "task": {
                    "id": "task-001",
                    "function": "echo",
                    "input": ["hello-a2a"],
                }
            },
        }
    )
    print(response)

asyncio.run(main())
```

### 2.2 Custom runtime (advanced)

```python
import asyncio

from easyremote.a2a import A2AGateway
from easyremote.protocols import FunctionDescriptor, FunctionInvocation, ProtocolRuntime


class Runtime(ProtocolRuntime):
    async def list_functions(self):
        return [FunctionDescriptor(name="echo", node_ids=["agent-1"])]

    async def execute_invocation(self, invocation: FunctionInvocation):
        return invocation.args[0]


async def main():
    gateway = A2AGateway(runtime=Runtime())

    response = await gateway.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "task-1",
            "method": "task.execute",
            "params": {
                "task": {
                    "id": "task-001",
                    "function": "echo",
                    "input": ["hello-a2a"],
                }
            },
        }
    )
    print(response)


asyncio.run(main())
```

## 3. Not implemented yet (roadmap)

- Rich task lifecycle states (`queued/running/partial/cancelled`).
- Task cancellation and callback channels.
- Cross-protocol orchestration hooks (A2A task internally invoking MCP tools).
