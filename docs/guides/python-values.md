# Typed Python values

This source candidate supports typed unary arguments and returns for dataclasses,
Pydantic v2 models, registered custom classes, and NumPy numeric/datetime arrays.
The caller stub and provider must declare the corresponding Python annotations.
Install optional dependencies in each source environment:

```bash
uv sync --extra numpy --extra pydantic
```

Register custom codecs on both endpoints before registering functions or stubs:

```python
from easyremote import ValueCodec, register_value_codec

class Job:
    def __init__(self, name: str):
        self.name = name

register_value_codec(ValueCodec(
    python_type=Job,
    schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
    encode=lambda job: {"name": job.name},
    decode=lambda value: Job(value["name"]),
))
```

Keep that definition in a shared interface module. Codecs serialize state;
methods come from the locally installed class definition. No class name from
an incoming payload is imported or executed. Duplicate registrations fail.
The encoder must produce JSON data conforming to its declared schema and the
decoder must reconstruct the declared type. Codec definitions must match on
both endpoints; changing their shape requires updating the ability contract.

For example, a provider can accept and return a nested inference job:

```python
from dataclasses import dataclass
import numpy as np
from easyremote import ComputeNode

@dataclass
class Batch:
    job: Job
    values: np.ndarray

node = ComputeNode()

@node.register
def evaluate(batch: Batch) -> Batch:
    return Batch(Job(batch.job.name + "-done"), batch.values * 2)
```

On the caller, import the same interface types and codec registration. Given
an explicitly configured `client` targeting the provider, declare:

```python
from easyremote import remote

@remote(client=client)
def evaluate(batch: Batch) -> Batch: ...

result = evaluate(Batch(Job("sample"), np.arange(6).reshape(2, 3)))
assert isinstance(result, Batch)
assert isinstance(result.job, Job)
assert isinstance(result.values, np.ndarray)
```

`@remote` calls, bound class stubs and `.aio()` restore annotated unary results.
Unannotated ad-hoc calls retain their JSON result projection. Dataclasses and
Pydantic models retain their existing JSON representation. NumPy arrays use
`dtype`, `shape`, and base64 `data`, preserving logical C-order bytes, dtype
(including endianness), and shape; strides, shared backing storage and subclass
identity are not transferred. The decoder returns an independent writable array.
Object/structured/string dtypes are rejected; numeric, boolean, complex, and
datetime arrays are supported. Each array is bounded to 16 MiB and 32 dimensions;
the Runtime's total invocation size limits still apply. This codec is not a
zero-copy or streaming transport.

Validation includes a real local Unix-socket Python host roundtrip and malformed
array rejection before allocation. This is not an official-Hub E2E claim.
Request-side media streams, full Python-provider duplex execution and automatic
typed stream-result projection are still separate unfinished work.
