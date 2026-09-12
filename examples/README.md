# EasyRemote v2 Examples

One-time prerequisites on every machine involved:

```bash
# 1. Pair this device into your realm.
easynet login
easynet device join <pairing-token>

# 2. Start the local device daemon.
easynet runtime start

# 3. Sanity-check library / daemon / identity / transport.
easyremote doctor

# Hub machines can start the hub daemon through the EasyRemote facade.
easyremote hub --realm my-team

# Existing EAL files can be submitted through the same daemon facade.
easyremote mission run ./nightly.eal --label nightly
```

| Example | What it shows |
|---|---|
| `01_hello_node.py` | Register a local function as a capability and serve it warm |
| `02_hello_client.py` | Call it three ways: result-first, typed stub, full invocation object |
| `03_pipeline.py` | Compose capabilities into an EAL mission and submit it |
| `04_streaming_node.py` | Register a host_stream producer that yields multiple frames |
| `04_streaming_client.py` | Consume stream frames and the terminal value |
| `05_remote_on_class.py` | `@remote` as a class attribute: name from the attribute, client from the host, `self` stripped |
| `06_owner_handles.py` | Owner handles (`client.device/agent/hub`) + `@handle.remote` — the client mirror of `@node.register` |
| `remote_demo_node.py` | Minimal remote demo node using the current facade |
| `remote_demo_client.py` | Minimal remote demo client using the current facade |

Run the node in one terminal, then the client in another:

```bash
python examples/01_hello_node.py
python examples/02_hello_client.py
```

## Companion providers

Run `uv sync --locked` first. Provider and caller use the same Runtime
configuration in separate terminals. Keep one provider running at a time.

| Provider (terminal 1) | Caller (terminal 2) | Preserved scenario |
|---|---|---|
| `uv run python examples/decorator_quickstart/compute_node.py` | `uv run python examples/decorator_quickstart/client.py` | Math, async fan-out, unary thumbnail bytes, latency. |
| `uv run python examples/05_gpu_cluster_node.py` | `uv run python examples/05_remote_on_class.py` | GPUCluster inference, embedding and summarization descriptors. |
| `uv run python examples/03_pipeline_node.py` | `uv run python examples/03_pipeline.py` | Two dependent inference calls, executed by Runtime. |
| `uv run python examples/06_owner_handles_node.py` | `uv run python examples/06_owner_handles.py` | Device, native Agent and Hub owner handles. |

The decorator's `make_thumbnail` is a byte-slicing stand-in for transport
validation, not an image decoder or resizer. Its signature remains `bytes ->
bytes`; unary JSON uses the existing base64 codec. GPUCluster uses deterministic
model fixtures; substitute real model implementations to measure GPU behavior.

Pipeline keeps the inference result object and adds an explicit
`completion_text` projection before passing its string into the next prompt.
Each Agent call pins the discovered owner and descriptor. The caller checks
the Runtime terminal state; merely submitting a mission is not a passing run.

### Native owner-handles setup

Use a Device paired to a reachable Hub for this case. The local merged
`localhost` mode currently does not establish the hosted-Agent publication
readiness proof needed for this scenario. Do not disable its admission gate.

The provider uses `client.agents.add` and `client.agents.put_abilities` to create
`owner-handles-demo` and publish a resident Python `greet` ability on that
Agent. It refuses to overwrite an existing Agent with that name. It waits up
to 120 seconds for the public Agent state to become `published`, then reports
readiness. Stop it with Ctrl-C; it stops its created Agent and provider bindings.

The caller retains `@gpu.remote`, `@alice.remote`, and `client.hub()` plus
ad-hoc Agent dispatch. Its `chat(prompt)` stub explicitly binds to the custom
`greet` descriptor: Runtime reserves `chat` for its structured model interface.
The custom greeting does not invoke a model driver. Hub route lookup uses the
actual `federation.resolve` contract with the selected Device as its explicit
read subject, then verifies that Device is active. `--device` and `--agent` select explicitly
deployed alternatives; the defaults match the companion provider.

See [current validation](../docs/guides/current-example-validation.md) for the
versions, tested outcomes and remaining limits.
