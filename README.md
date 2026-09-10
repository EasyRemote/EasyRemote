# You wrote a function. The world wants a service.

<div align="center">

![EasyRemote Logo](docs/easyremote-logo.png)

[![PyPI version](https://badge.fury.io/py/easyremote.svg)](https://badge.fury.io/py/easyremote)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/easyremote)]()

> **EasyRemote turns a local function into a governed Ability callable by admitted EasyNet users, agents, and devices.**

**EasyNet-native · Signed invocations · Verifiable execution**

English | [中文](README_zh.md)

</div>

---

You have a capability sitting on your machine — a model, a pipeline, a function that queries your database. A teammate wants to use it. An agent wants to call it. Another project wants to build on it. Today the answer is always the same ritual: package, containerize, deploy, authenticate, maintain. **The unit of sharing is "a deployment" — which is why most capabilities are never shared at all.**

Why is deployment mandatory? Because your machine sits behind NAT and the world cannot reach it. The 4090 under your desk isn't gathering dust because it's weak — ten years ago it would have been a supercomputer — but because there is no safe way for anything to call it. Uploading was the only way out.

EasyRemote shrinks the unit of sharing down to one function:

```python
from easyremote import ComputeNode

node = ComputeNode()

@node.register
def ai_inference(prompt: str) -> str:
    return model.generate(prompt)   # runs on your GPU, model stays warm

node.serve()
```

After registration, that function is a **capability** — and capability is not a metaphor. It has a minimal definition: **callable, discoverable, composable**, all three at once:

```python
# A teammate: call it like a local function
from easyremote import Client, FreshRoot, ResolvedTargetSubject
client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
client.execute("ai_inference", prompt="hello")

# An agent runtime: call the same capability through the EasyRemote client
#   client.call("ai_inference", prompt="hello")

# A system: one step in a pipeline, composed with other people's functions
from easyremote import Pipeline
pipe = Pipeline("nightly")
fetch = pipe.step("teamA.fetch_sales", quarter="Q2")
pipe.step("er.summarize", rows=fetch.output)
```

Those are not three separate products — they are three views of the same governed Ability. Your code and your model never leave your machine; authorized callers get the right to invoke the interface, not a copy of its implementation.

Git lowered the unit of sharing code from a project to a commit. Docker lowered the unit of shipping software from a machine to an image. **EasyRemote lowers the unit of sharing services from a deployment to a function.**

**The first direct corollary: a team GPU pool.** Functions execute where they live, so GPUs in the office, at home, or in a dorm can provide one governed inference surface. Devices connect outward to their Hub and models can remain warm; actual reachability, startup time, latency, and cost depend on the deployment.

**You'll ask: isn't opening my machine dangerous?** That's exactly why nobody dared to do this before. EasyRemote is built on the EasyNet stack: signed invocations carry who called, whom they called, what was acted on, and which causal chain the call follows; signed paths close with verifiable receipt facts. Application code does not construct that machinery, but operators still configure identity, pairing, policy, and lifecycle. EasyRemote does not bypass those decisions.

**And the moment nothing else can replace it: the day agents operate real-world resources.** Agent capability jumps a tier every quarter, but agent accountability hasn't changed since day one — a tool call goes out, and everything after that is self-reported. Letting an agent check the weather is fine; letting it touch your database, place orders, or drive hardware means "what did it actually do" can no longer be an autobiography. Signed invocations plus receipt chains express authorization the way it was always meant to be said: **this agent, under my authority, within this task chain, may call this capability and act on this object.**

Ray, Modal, and RunPod make remote execution *easy*. Tool protocols make agents *connectable*. Nobody makes local capabilities *composable and accountable* service units. We build the layer missing between them.

**Cloud computing moved code to the compute. EasyRemote keeps the compute where it is — and makes its governed interface callable through EasyNet.**

EasyRemote owns Python ergonomics: schema derivation, `@node.register`,
`@remote`, Ability packaging, and the warm resident Python host. EasyNet-Cli
owns `easynet-daemon`, pairing, keys, routing, provider lifecycle, and SDK
transport. Axon owns canonical Invocation, admission, Receipt, and stream
terminal semantics. `node.serve()` starts the Python provider only; it does not
install, pair, or start the daemon.

---

## Getting started

The current source preview requires `easynet-sdk>=0.142.22,<0.143`, which is not
yet available from the public package registry. Until the dependency-first
release completes, keep these repositories as sibling checkouts:

```text
workspace/
  EasyNet-Axon/
  EasyNet-Cli/
  EasyRemote/
```

```bash
cd EasyRemote
uv sync

cd ../EasyNet-Cli
packaging/release/dev-install-local.sh --debug

cd ../EasyRemote

# One-time identity setup (signs invocations and receipt chains).
# Start the device or Hub runtime with EasyNet-Cli operator tooling.
# `node.serve()` connects to that operator-managed runtime.
easynet login
easynet device join <pairing-token>
easynet runtime start
easyremote doctor                            # optional runtime diagnosis
```

Then it's the twelve lines above. `examples/` has runnable node/client pairs.

If this is the first run, `node.serve()` does not invent an identity. Complete
`easynet login` and `easynet device join <pairing-token>`, then start or attach
to the operator-managed Runtime with `easynet runtime start`. The provider
connects to that Runtime, starts the warm Python host, and publishes every
registered function. Pairing supplies caller identity and signing; selecting a
device chooses where the function runs without granting machine access.

| Example | Shows |
|---|---|
| `01_hello_node.py` / `02_hello_client.py` | minimal register → call |
| `03_pipeline.py` | compose abilities into an EAL mission |
| `remote_demo_node.py` / `remote_demo_client.py` | every function shape via `@node.register` + `@remote` (unary, `*args`/`**kwargs`, async, generator, Context) |
| `04_streaming_node.py` / `04_streaming_client.py` | proves streaming is **incremental, not batched** — measures per-frame arrival gaps |

### Production use cases

For production-shaped MVPs, [`gallery/projects/`](gallery/projects/) contains
independent uv applications rather than feature snippets:

| Project | Minimum task |
|---|---|
| [Remote quote](gallery/projects/00_basic_remote_math/) | Share one validated pricing rule without building a quote service |
| [Warm model](gallery/projects/01_team_gpu_pool_load_balancing/) | Call a model that remains on a selected GPU device |
| [Enterprise tool boundary](gallery/projects/02_mcp_tool_mesh/) | Give agents typed business operations without backend credentials |
| [Incident evidence](gallery/projects/03_a2a_incident_copilot/) | Diagnose an allowlisted service and stream bounded evidence without SSH |
| [Function reuse](gallery/projects/04_function_marketplace/) | Consume owned business logic without copying its source |
| [Data-resident AI](gallery/projects/05_local_data_residency_ai/) | Release a bounded projection while source records remain local |
| [Device camera](gallery/projects/06_runtime_device_capability_injection/) | Stream finite media from a paired device without opening the device |
| [Robot action](gallery/projects/07_claude_code_robot_commander_mcp/) | Give an Agent one constrained, attributable action instead of machine control |
| [Network-native library](gallery/projects/08_network_native_python_library/) | Install a typed local Python interface while provider code remains remote |

Each project owns its `pyproject.toml`, `uv.lock`, provider, caller, and concise
case paper. Start with the [Gallery index](gallery/projects/README.md).

### Call it like Python

```python
from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))

@remote(client=client)
def ai_inference(prompt: str) -> str: ...

print(ai_inference("hello"))
```

The stub has the same name and typed signature as the published function, but
contains no copy of its implementation. The call runs where the provider lives.

### Choose where it runs

```python
gpu = client.device("gpu-2")

@gpu.remote
def ai_inference(prompt: str) -> str: ...

print(ai_inference("hello from this GPU"))
```

Targeting a paired device selects the execution host without exposing SSH,
ports, model files, database credentials, or the underlying device API.

### Multimodal binary streams

Yield `StreamFrame` to preserve the original media bytes and content type. The
same `@remote` stub consumes the stream: JSON frames remain ordinary Python
values, while media frames remain `StreamFrame` objects.

```python
from collections.abc import Iterator
from easyremote import ComputeNode, StreamFrame, remote

node = ComputeNode()

@node.register
def camera(frames: int) -> Iterator[StreamFrame]:
    for jpeg in capture_jpegs(frames):
        yield StreamFrame(jpeg, "image/jpeg")

@remote(client=client)
def camera(frames: int) -> Iterator[StreamFrame]: ...

for frame in camera.stream(30):
    consume(frame.payload, frame.content_type)
```

On the local provider-host → `easynet-daemon` Unix-socket boundary,
`binary_v1` preserves `StreamFrame` bytes and media type without JSON or base64
conversion. The network path is still owned by the Runtime and SDK; this is not
an end-to-end zero-copy, latency, or bandwidth claim. JSON generators use the
same `.stream(...)` interface.

### Provider lifecycle

`ComputeNode` treats readiness as an explicit sequence:

```text
declared → schema → package → ability.deploy → Local active
         → realm advertisement pending/confirmed → lease renewal → stop/expiry
```

`Local active` means the paired local daemon can invoke the provider. It does
not prove realm visibility. EasyRemote reports advertisement as pending until
the owning Runtime/product confirms publication.

---

## Project status

EasyRemote v2 is currently in alpha and is not compatible with v1. It supports
typed sync and async functions, finite server streams, exact local binary/media
host frames, device targeting, warm providers, caller context, signed invocation
receipts, and receipt-anchored `Context.call` / `Context.invoke` /
`Context.stream` child dispatch.

Using it requires a paired, running EasyNet runtime. Cross-device latency and
bandwidth depend on the deployment, and this alpha does not claim a universal
network SLO. The source candidate adds [request-side media and duplex providers](docs/guides/duplex-media.md). Full remote receipt-chain fetch
and independent verification remain future work.

Detailed architecture notes live in the
[`v2 design`](docs/design/easyremote-v2-easynet-refactor.md).

EasyRemote is the public Python facade of a wider research system released in
stages. The [Public Source Release Scope](https://github.com/EasyRemote/EasyRemote/blob/main/SOURCE_RELEASE_SCOPE.md)
explains the boundary without changing the MIT rights granted for this
repository.

## Attribution

EasyRemote is MIT-licensed. Its EasyNet runtime dependencies are Apache-2.0 projects and are listed in [`NOTICE.md`](NOTICE.md). Research and systems references used to position the design are collected in [`docs/REFERENCES.md`](docs/REFERENCES.md).

## License

[MIT](LICENSE) © Silan Hu

Typed Python values in the source candidate: see [custom classes, dataclasses, Pydantic and NumPy](docs/guides/python-values.md) for registration, return-type restoration and exact limits.
