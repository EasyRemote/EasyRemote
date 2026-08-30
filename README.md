# You wrote a function. The world wants a service.

<div align="center">

![EasyRemote Logo](docs/easyremote-logo.png)

[![PyPI version](https://badge.fury.io/py/easyremote.svg)](https://badge.fury.io/py/easyremote)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/easyremote)]()

> **EasyRemote turns a local function into a globally callable capability.**

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

Those are not three use cases — **that is the entire semantics of the capability abstraction.** Your code and your model never leave your machine; the world gets the right to call, not a copy.

Git lowered the unit of sharing code from a project to a commit. Docker lowered the unit of shipping software from a machine to an image. **EasyRemote lowers the unit of sharing services from a deployment to a function.**

**The first direct corollary: a team GPU pool.** When functions execute where they live, compute sharing falls out for free — GPUs in the office, at home, in a dorm form one inference cluster. Nodes only dial out, so NAT is not an obstacle; models stay resident, so there is no cold start; the gateway is a $5 VPS.

**You'll ask: isn't opening my machine to the world dangerous?** That's exactly why nobody dared to do this before. EasyRemote is built on the EasyNet stack: every call is a signed invocation object — who called, whom they called, what was acted on, which causal chain it follows — and every execution terminates in a verifiable receipt. **There is no switch for this layer, no configuration; you will barely notice it exists.** It is also the entire reason you can dare to share your machine.

**And the moment nothing else can replace it: the day agents operate real-world resources.** Agent capability jumps a tier every quarter, but agent accountability hasn't changed since day one — a tool call goes out, and everything after that is self-reported. Letting an agent check the weather is fine; letting it touch your database, place orders, or drive hardware means "what did it actually do" can no longer be an autobiography. Signed invocations plus receipt chains express authorization the way it was always meant to be said: **this agent, under my authority, within this task chain, may call this capability and act on this object.**

Ray, Modal, and RunPod make remote execution *easy*. Tool protocols make agents *connectable*. Nobody makes local capabilities *composable and accountable* service units. We build the layer missing between them.

**Cloud computing moved code to the compute. EasyRemote keeps the compute where it is — and makes it globally callable.**

---

## Getting started

```bash
pip install --pre --upgrade easyremote

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

Binary frames preserve their exact bytes and media type without JSON or base64
conversion. Calls retain the same signed invocation and receipt-backed
completion semantics as ordinary function results. JSON generators use the same
`.stream(...)` interface.

---

## Project status

EasyRemote v2 is currently in alpha and is not compatible with v1. It supports
typed sync and async functions, finite server streams, exact binary/media
frames, device targeting, warm providers, caller context, and signed invocation
receipts.

Using it requires a paired, running EasyNet runtime. Cross-device latency and
bandwidth depend on the deployment, and this alpha does not claim a universal
network SLO. Request-side media streaming, composed `ctx.call` receipt chains,
and full receipt-chain fetch verification remain future work.

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
