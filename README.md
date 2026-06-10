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

# An agent: auto-projected as an MCP tool, discovered and called by Claude
#   claude mcp add easynet -- easynet mcp_server

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

Ray, Modal, and RunPod make remote execution *easy*. MCP makes tools *connectable*. Nobody makes local capabilities *composable and accountable* service units. We build the layer missing between them.

**Cloud computing moved code to the compute. EasyRemote keeps the compute where it is — and makes it globally callable.**

---

## Getting started

```bash
pip install easyremote

# One-time prerequisites (an ssh-keygen-style cost, buying you
# signed invocations and receipt chains)
easynet pair                                  # pair this device, issue identity
easyremote doctor                            # check library / daemon / identity / agent
```

Then it's the twelve lines above. `examples/` contains runnable node, client, and pipeline examples.

### Three call layers, progressively disclosed

```python
client = Client()

# L0 — result-first
client.execute("ai_inference", prompt="hi")

# L1 — targeting / streams / timeouts
client.call("ai_inference", prompt="hi", node="gpu-1", timeout=10)

# L2 — the full invocation object: seven-tuple in, receipts out
inv = client.invoke("ai_inference", prompt="inspect me")
inv.tuple.subject     # the seven-tuple is always inspectable
inv.receipts()        # the receipt chain
```

---

## Where it fits

| # | Scenario | Who it's for | What it solves |
|---|----------|-------------|----------------|
| K1 | **Private AI Inference Hub** (team GPU pool) | AI teams / R&D groups | Share team GPUs for inference with load spreading; eliminate redundant cloud spend |
| K2 | **Agent Tool Gateway** (enterprise tool mesh) | Agent platform teams | A unified capability catalog Claude, GPT, and custom agents discover and call directly |
| K6 | **Local Data Residency AI** | Healthcare / Finance / Government | Inference runs on the device where the data lives — compliant and accountable |
| K9 | **Runtime Device Capability Injection** | ToC agent apps / edge platforms | Hot-register new capabilities without restart (`easynet agent refresh`, live-verified) |
| K10 | **Claude Code Robot Commander** (Commander Skill + MCP) | Agent product teams / Robotics platforms | Install a commander skill in Claude Code, then remotely deploy and operate client-sandbox robots through MCP |

---

## Status (v2.0.0a0)

v2 is a clean reimplementation on the EasyNet stack ([EasyNet-Axon](https://github.com/EasyRemote/EasyNet-Axon) protocol layer + easynet-daemon), **not compatible with v1**. The spec, with line-by-line verification records against live daemon runs, lives at [`docs/design/easyremote-v2-easynet-refactor.md`](docs/design/easyremote-v2-easynet-refactor.md).

| Capability | Status |
|---|---|
| register → deploy → invoke closed loop (device abilities, warm host) | ⏳ facade verified contract-correct; blocked by an upstream daemon deploy→routing desync (minimal repro: `easynet ability deploy --node local` reports activated, yet `ability show`/invoke return not-found/ROUTE_NEGATIVE) |
| Three-layer client / `@remote` stubs / async mirror | ✅ |
| Pipeline → EAL → mission.run | ✅ |
| Server (hub + self-signed TLS bootstrap) | ✅ |
| `easyremote doctor` | ✅ |
| Streaming / server-side Context composition / <50ms warm latency | ⏳ pending the daemon host-attach protocol (EasyNet-Cli side) |
| Cryptographic receipt-chain verification | ⏳ pending the full-receipt fetch path (RFC-007/008) |

## License

[MIT](LICENSE) © Silan Hu
