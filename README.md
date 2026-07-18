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
from easyremote import Client
Client().execute("ai_inference", prompt="hello")

# An agent runtime: call the same capability through the EasyRemote client
#   Client().call("ai_inference", prompt="hello")

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
pip install easyremote

# One-time identity setup (signs invocations and receipt chains).
# Start the device or Hub runtime with EasyNet-Cli operator tooling.
# `node.serve()` connects to that operator-managed runtime.
easynet pair
easyremote doctor                            # optional runtime diagnosis

# Ability and agent control surfaces are also available through the
# same daemon Invocation facade:
easyremote ability install ./my_ability
easyremote ability list --scope realm --json
easyremote agent add caesura --type claude-code --model sonnet
easyremote mission run ./nightly.eal --label nightly
```

Then it's the twelve lines above. `examples/` has runnable node/client pairs:

If this is the first run, `node.serve()` does not invent an identity. It prints
the one required action — `easynet pair` — and exits. Once paired, the same
script checks the SDK, reuses a running daemon or starts a device daemon, then
starts the warm host and publishes every registered capability.

| Example | Shows |
|---|---|
| `01_hello_node.py` / `02_hello_client.py` | minimal register → call |
| `03_pipeline.py` | compose abilities into an EAL mission |
| `remote_demo_node.py` / `remote_demo_client.py` | every function shape via `@node.register` + `@remote` (unary, `*args`/`**kwargs`, async, generator, Context) |
| `04_streaming_node.py` / `04_streaming_client.py` | proves streaming is **incremental, not batched** — measures per-frame arrival gaps |

### Three call layers, progressively disclosed

```python
from easyremote import Client

client = Client()

# L0 — result-first
client.execute("ai_inference", prompt="hi")

# L1 — targeting / streams / timeouts without stealing ability arg names
client.call(
    Client.target("ai_inference", node="gpu-1", timeout=10),
    prompt="hi",
)

# L2 — inspect the seven-tuple before dispatch
prepared = client.prepare("ai_inference", prompt="inspect me")
prepared.tuple.subject_ura

# send() is for daemon unary/system abilities; EasyRemote-hosted
# abilities are host_stream and should be consumed with call()/stream().
```

`Client.invocation_policy` exposes the read-only EasyRemote product policy
used to derive ordinary calls. Its documented default is
`DEFAULT_INVOCATION_POLICY`, a `FreshRoot(ResolvedTargetSubject())`. Supply a
different policy with `Client(invocation_policy=...)`, or attach a collision-free
single-call override with `Client.target(..., invocation_policy=...)`. A normal
ability argument named `policy` remains an ability argument.

The released `Client.target(..., subject=..., causal=...)` keywords remain as a
versioned edge adapter until EasyRemote 1.0.0. They lower immediately to the
same product policy object and are not a second invocation builder.

The released `InvocationTuple`, `Receipt`, `ReceiptChain`, and
`PreparedInvocation.with_causal` shapes are also bounded product-edge adapters.
They preserve their released constructors and fields while delegating
Invocation projection, receipt parsing, and causal projection to `easynet_sdk`.
`easyremote/edge-adapter-policy.v1.json` is the machine-readable allowlist; it
records package version `2.0.0a0`, removal version `1.0.0`, and prohibits new
internal callers.

### `@remote` as a class attribute

A `@remote` stub is a descriptor — like `property`. On a class body it
takes the attribute name as the ability name, and an instance access
binds it to that host: `self` is stripped from the wire arguments and
the host's own client is reused. Module-level `@remote` is unchanged.

```python
class GPUCluster:
    def __init__(self, client):
        self.client = client          # the host carries the client

    @remote                            # ability name = "ai_inference"
    def ai_inference(self, prompt: str, max_tokens: int = 64) -> str: ...

GPUCluster(Client()).ai_inference("hi")   # self stripped, host client reused
```

Client precedence is `@remote(client=...)` > `self.client` > `self._client`.
See [`examples/05_remote_on_class.py`](examples/05_remote_on_class.py).

### Owner handles — the mirror of `@node.register`

The serving side groups functions on a `ComputeNode` and publishes them with
`@node.register`. The calling side is symmetric: a handle to an ability owner
carries the target identity, and `@handle.remote` declares a stub bound to it.

```python
# serving side                    # calling side (symmetric)
node = ComputeNode()              gpu   = client.device("gpu-2")
@node.register                    @gpu.remote
def chat(...): ...                def chat(...): ...
```

```python
gpu   = client.device("gpu-2")              # a device in this realm
alice = client.agent("u-alice.chatbot")     # an agent: <user-id>.<agent-id>
hub   = client.hub()                        # the realm hub

@alice.remote
def chat(prompt: str) -> str: ...

chat("hi")                                  # routed to alice
hub.call("route", target="gpu-2")           # ad-hoc, no stub
```

`device`, `agent`, and `hub` owners are first-class daemon routes. A full
cross-realm owner URA is accepted but only routes where federation peers are
configured. See [`examples/06_owner_handles.py`](examples/06_owner_handles.py).

### Use-case facade map

| Use case | Minimal facade |
|---|---|
| Publish local functions | `node = ComputeNode(); @node.register; node.serve()` |
| Result-first call | `Client().execute("ai_inference", prompt="hi")` |
| Target a device / agent / hub | `Client().device("gpu-2").call(...)`, `Client().agent("u.a").call(...)`, `Client().hub().call(...)` |
| Inspect and send the invocation tuple | `prepared = Client().prepare(...); prepared.tuple; prepared.send()` |
| Compose a mission in Python | `Pipeline("nightly").step(...); pipe.run()` |
| Run existing EAL source | `Client().missions.run_eal(source, label="nightly")` or `Client().missions.run_file("nightly.eal")` |
| Control daemon catalogues | `Client().abilities.list(scope="realm")`, `Client().agents.add(...)` |

Mission plans, step/output references, child-fact conformance, result
projection, and bounded event tailing are EasyRemote product semantics. They
dispatch through generic `Client.invoke`; easynet-sdk remains responsible for
generic Invocation, addressing, transport, and typed runtime errors.

---

## Where it fits

| # | Scenario | Who it's for | What it solves |
|---|----------|-------------|----------------|
| K1 | **Private AI Inference Hub** (team GPU pool) | AI teams / R&D groups | Share team GPUs for inference with load spreading; eliminate redundant cloud spend |
| K2 | **Agent Capability Backend** (enterprise tool mesh) | Agent platform teams | A unified capability catalog custom agent runtimes can discover and call through EasyRemote |
| K6 | **Local Data Residency AI** | Healthcare / Finance / Government | Inference runs on the device where the data lives — compliant and accountable |

---

## Status (v2.0.0a0)

v2 is a clean reimplementation on the EasyNet stack ([EasyNet-Axon](https://github.com/EasyRemote/EasyNet-Axon) protocol layer + easynet-daemon), **not compatible with v1**. The spec, including the EasyNet-Cli/Axon contract notes, lives at [`docs/design/easyremote-v2-easynet-refactor.md`](docs/design/easyremote-v2-easynet-refactor.md).

`✅` means implemented in this repository and covered by unit/contract tests unless the row explicitly says "live daemon". Daemon availability, runtime ability loading, and receipt persistence are EasyNet-Cli/Axon contracts, so they are documented separately from facade-local behavior.

| Capability | Status |
|---|---|
| register → deploy package generation (device abilities, warm host) | ✅ implemented in the facade and unit-tested against the host_stream contract |
| Runtime ability deployment / hot-load | ✅ facade invokes daemon `ability.deploy` through complete Invocation; live daemon hot-load is an EasyNet-Cli contract |
| Ability catalogue / install control facade | ✅ `Client().abilities` plus `easyremote ability install/list/show`; `--scope realm` reads the hub-published network catalogue |
| Agent lifecycle control facade | ✅ `Client().agents` plus `easyremote agent add/list/refresh` |
| invoke closed loop against a live daemon | 🧪 integration/manual path only; CI skips without `EASYNET_CLI_LIB` + a running daemon |
| Three-layer client / `@remote` stubs / async mirror | ✅ |
| Pipeline → EAL → mission.run | ✅ EasyRemote owns plan/projection/event-tail semantics; `Pipeline.run()` dispatches via generic `Client.invoke` |
| Direct Mission/EAL run facade | ✅ `Client().missions.run_eal/run_file/track/cancel` plus `easyremote mission run/track/cancel` |
| Runtime connection | ✅ `ComputeNode` acquires an SDK `RuntimeConnection`; EasyNet-Cli owns device/Hub configuration and process lifecycle |
| `easyremote doctor` | ✅ |
| Streaming | ✅ host_stream producer/consumer implemented; see `examples/04_streaming_*.py` |
| Async functions / generators (sync + async) | ✅ |
| Server-side Context (read-only caller identity) | ✅ `ctx.caller` + `ctx.invocation_id` injected from the host_stream envelope |
| Server-side Context composition (`ctx.call` child invocations) | ⏳ needs the parent-receipt-URA path for causal chaining (RFC-007/008) |
| Warm-host latency target (`<50ms`) | 🧪 not claimed in this release; requires a live-daemon benchmark |
| Cryptographic receipt-chain verification | ⏳ pending the full-receipt fetch path (RFC-007/008) |

## Attribution

EasyRemote is MIT-licensed. Its EasyNet runtime dependencies are Apache-2.0 projects and are listed in [`NOTICE.md`](NOTICE.md). Research and systems references used to position the design are collected in [`docs/REFERENCES.md`](docs/REFERENCES.md).

## License

[MIT](LICENSE) © Silan Hu
