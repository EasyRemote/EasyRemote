# EasyRemote API patterns

## Contents

- Runtime prerequisites
- Unary provider and caller
- Finite JSON stream
- Binary media stream
- Caller context
- Explicit device targeting
- Argument and output rules

## Runtime prerequisites

EasyRemote connects to an operator-managed EasyNet runtime. It does not create
identity or start a Hub implicitly.

```bash
easynet pair
easynet start
easyremote doctor
```

A provider reporting `Local active` is ready for local invocation. `Realm
advertisement pending` means Hub publication is still converging; it is not a
local activation failure.

## Unary provider and caller

Provider:

```python
from easyremote import ComputeNode

node = ComputeNode(namespace="er")


@node.register(description="Calculate one bounded quote.")
def calculate_quote(seats: int, monthly_cents: int) -> dict[str, int]:
    if not 1 <= seats <= 5_000:
        raise ValueError("seats must be between 1 and 5,000")
    if not 1 <= monthly_cents <= 1_000_000:
        raise ValueError("monthly_cents is outside the supported range")
    return {"seats": seats, "total_cents": seats * monthly_cents}


if __name__ == "__main__":
    node.serve()
```

Caller:

```python
from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def calculate_quote(seats: int, monthly_cents: int) -> dict[str, int]: ...


print(calculate_quote(seats=24, monthly_cents=3_900))
```

Keep the public function name and signature aligned. `@remote` declares a
stub; its ellipsis body never runs.

## Finite JSON stream

Provider:

```python
from collections.abc import Iterator

from easyremote import ComputeNode

node = ComputeNode(namespace="er")


@node.register(description="Return finite ordered telemetry samples.")
def telemetry(samples: int = 3) -> Iterator[dict[str, int]]:
    if not 1 <= samples <= 20:
        raise ValueError("samples must be between 1 and 20")
    for sequence in range(1, samples + 1):
        yield {"sequence": sequence, "temperature_c": 42}
```

Caller:

```python
from collections.abc import Iterator

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def telemetry(samples: int = 3) -> Iterator[dict[str, int]]: ...


for sample in telemetry.stream(samples=3):
    print(sample)
```

Use `.stream(...)`, not a normal stub call, when incremental delivery is part
of the contract.

## Binary media stream

Provider:

```python
from collections.abc import Iterator

from easyremote import ComputeNode, StreamFrame

node = ComputeNode(namespace="er")


@node.register(description="Return a finite sequence of JPEG frames.")
def camera_frames(count: int = 3) -> Iterator[StreamFrame]:
    if not 1 <= count <= 10:
        raise ValueError("count must be between 1 and 10")
    for _ in range(count):
        yield StreamFrame(capture_jpeg(), "image/jpeg")
```

Caller:

```python
from collections.abc import Iterator

from easyremote import (
    Client,
    FreshRoot,
    ResolvedTargetSubject,
    StreamFrame,
    remote,
)

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def camera_frames(count: int = 3) -> Iterator[StreamFrame]: ...


for frame in camera_frames.stream(count=3):
    consume(frame.payload, frame.content_type)
```

`StreamFrame` preserves exact bytes and content type through the SDK-owned C
ABI v8 raw-stream extension. Do not base64-encode the frame in user code.

## Caller context

The provider may accept `Context` only as its first parameter:

```python
from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")


@node.register
def audit_lookup(ctx: Context, record_id: str) -> dict[str, str]:
    return {
        "record_id": record_id,
        "requested_by": ctx.caller,
        "invocation_id": ctx.invocation_id,
    }
```

The caller stub omits `Context`:

```python
@remote(client=client)
def audit_lookup(record_id: str) -> dict[str, str]: ...
```

The host injects caller and invocation identity from the daemon-relayed
envelope. Caller arguments cannot spoof it.

## Explicit device targeting

Bind a stub to a stable paired device id:

```python
import os

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client, node=os.environ["EASYREMOTE_TARGET_NODE"])
def run_inference(prompt: str) -> str: ...
```

Alternatively use an owner handle:

```python
gpu = client.device("gpu-2")


@gpu.remote
def run_inference(prompt: str) -> str: ...
```

The device is the execution host. EasyRemote deployment publishes the ability
under that device's `ability-management` SystemAgent; do not construct a
legacy Device-owned Ability URA.

## Argument and output rules

- Prefer JSON scalars, lists, mappings, dataclasses, enums, and pydantic v2
  models.
- Use `bytes` or `StreamFrame` for binary output.
- Convert file handles, sockets, tensors, model objects, database connections,
  and device handles to bounded descriptors or provider-local state.
- Preserve positional-only parameters, defaults, `*args`, keyword-only
  parameters, and `**kwargs` exactly between provider and stub.
- Bound any input that controls work, allocation, time range, frame count, or
  external side effects.
