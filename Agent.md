# EasyRemote Agent Guide

This file is the operating manual for agents working in this repository. Keep
it concrete: EasyRemote is a Python product facade over EasyNet-Cli and Axon,
not an independent runtime.

## Agent Bootstrap

Use this order whenever an agent enters the repository:

1. Read this file completely.
2. Read `AGENTS.md` for repository-level authorship and engineering rules.
3. Inspect the public surface in `easyremote/__init__.py`; do not infer APIs
   from old prose or examples.
4. For an application or concrete use case, load
   `skills/easyremote-ability-builder/SKILL.md` and inspect the closest project
   under `gallery/projects/`.
5. For runtime, SDK, authority, signer, routing, or ABI changes, also read the
   sibling EasyNet-Cli repository's instructions before editing it.
6. Check both worktrees before making changes. Never discard unrelated edits.

Source priority is executable code and tests, then this guide, then current
design documents, then historical PR notes. If two sources disagree, prove the
current behavior with a focused test before changing documentation.

## Repository Map

| Path | Responsibility |
|---|---|
| `easyremote/node.py` | `ComputeNode`, registration, package deployment, lease lifecycle |
| `easyremote/client.py` | `Client`, `@remote`, targeting, stream and bidi facades |
| `easyremote/schema.py` | Python signature and JSON-schema derivation |
| `easyremote/_host/` | Warm resident host and `binary_v1` framed execution |
| `easyremote/_sdk_transport/` | Thin error/value adapter over public `easynet_sdk` APIs |
| `easyremote/control.py` | Ability and Agent control facades |
| `easyremote/mission.py` | Mission/EAL product facade |
| `tests/` | Public contracts, host protocol, SDK-boundary, and lifecycle tests |
| `gallery/projects/` | Independent, uv-locked, production-shaped MVP cases |
| `skills/easyremote-ability-builder/` | Reusable instructions for another agent building with EasyRemote |
| `docs/design/` | Current architectural rationale; not a substitute for tests |
| `pr/` | Ignored task notes, invariants, verification, and decisions |

## Operational SOP

### Entering the repository

1. Read this file and `AGENTS.md` completely.
2. Run `git status --short` in EasyRemote and both sibling repositories before
   editing. Existing changes belong to their current owner; never reset, format,
   or stage them incidentally.
3. Inspect `easyremote/__init__.py` for the actual public surface and the closest
   tests for the behavior being changed.
4. For runtime, identity, authority, signer, routing, descriptor, receipt, or
   C ABI work, move the implementation to the owning EasyNet-Cli or Axon layer.
5. Create or update `pr/<date>-<task>/` with intent, invariants, a checklist,
   verification, and decisions before changing architecture or runtime-facing
   behavior.

### Development and runtime startup

Repository development and product runtime startup are separate operations:

```bash
# EasyRemote development environment
uv sync
uv run pytest -q

# One-time/operational EasyNet setup; run with the installed easynet CLI
easynet login
easynet device join <pairing-token>   # starts the daemon unless --boot no
easynet runtime start                 # explicit, idempotent start/attach
easynet status
```

There is no `easynet dev init` prerequisite. `uv run python node.py` starts the
EasyRemote provider process only; it does not install, pair, or start
`easynet-daemon`. A provider must fail with one actionable recovery instruction
when credentials or the daemon are unavailable.

Run a Gallery case from its own uv project, with provider and caller in separate
terminals:

```bash
cd gallery/projects/00_basic_remote_math
uv sync
uv run python node.py
# second terminal, same directory
uv run python client.py
```

### Version and release SOP

- EasyRemote version truth is `easyremote/_version.py`.
- The accepted EasyNet SDK line is declared once in the root `pyproject.toml`;
  Gallery manifests, scaffold output, policy documentation, tests, and locks
  must converge with it.
- Never derive the EasyRemote version from the EasyNet Runtime, SDK, or Axon
  version. These are separate distributions.
- Never hand-edit `uv.lock`; change the owning manifest and run `uv lock` in the
  root and in every affected independent Gallery project.
- `.github/workflows/publish-easyremote.yml` publishes only from an exact
  `v<easyremote-version>` tag. Manual dispatch is validation-only.
- Release order is dependency-first: publish the required Axon SDK, then
  `easynet-sdk`, then EasyRemote. Registry-only resolution must pass before the
  downstream tag is pushed.

“Current local version”, “latest published version”, and “next release version”
are different facts. Resolve them explicitly:

```bash
# Current version in this checkout (the candidate metadata source)
python3 -c 'exec(open("easyremote/_version.py").read()); print(__version__)'

# Latest immutable version already published on PyPI
curl --fail --silent --show-error https://pypi.org/pypi/easyremote/json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])'
```

EasyRemote does not use Tide. The next version is an explicit release decision:
it must be written to `easyremote/_version.py`, be strictly newer than the PyPI
value, and match the exact `v<VERSION>` tag. The publish workflow repeats the
PyPI comparison and rejects a stale or equal candidate.

Release preparation:

```bash
uv lock --check
for project in gallery/projects/*; do uv lock --project "$project" --check; done
uv run ruff check easyremote tests benchmarks gallery
uv run mypy easyremote
uv run pytest -q
uv build --out-dir dist/easyremote
uvx --from twine twine check dist/easyremote/*
```

Do not tag, push, upload, or dispatch a publishing workflow unless the user
explicitly requests that external state change.

### Script development standard

Scripts under `skills/**/scripts`, tests, or future root tooling must:

- be deterministic, non-interactive by default, and safe from any working
  directory;
- resolve repository paths from the script location rather than `$PWD`;
- validate all inputs before writes and keep target sets explicit;
- provide a read-only check/dry-run mode for release or migration operations;
- update related files transactionally and restore the original state on a
  failed generation step;
- use bounded waits, queues, payloads, and retries; never hide an unbounded loop
  behind a convenience command;
- fail non-zero with a specific recovery message; never swallow a failed lock,
  build, or conformance command;
- avoid developer-only tools in installation/release mutation paths when
  portable `find`, `awk`, `sed`, or language-standard tooling is sufficient;
- have a focused failure-path test, including rollback or no-write assertions
  where the script mutates files;
- avoid printing credentials, tokens, private keys, raw authority headers, or
  credential files.

For a skill script, run the structural validator and its repository contract
test listed in the Verification Commands section.

## Project Scope

EasyRemote lets Python developers publish local Python functions as governed
EasyNet abilities and call those abilities through the local `easynet-daemon`.
The user-facing surface is intentionally small:

- `ComputeNode` hosts Python callables on this device.
- `@node.register` publishes a callable as an EasyNet ability.
- `Client` discovers, calls, streams, opens bidi sessions, and accesses daemon
  control facades.
- `@remote` declares a typed client stub whose Python signature maps local
  arguments into an ability call.
- `StreamFrame` carries exact bytes plus a media type for multimodal
  server-stream output.

Do not move daemon lifecycle, plugin runtime, Axon receipt semantics, admission
policy, pairing, Hub/device routing, or key custody into EasyRemote. Those are
owned by EasyNet-Cli and Axon.

## Architecture Boundaries

EasyRemote owns Python ergonomics and packaging only:

- Derive schemas from Python type hints.
- Package an ability bundle for daemon `ability.deploy`.
- Keep a warm resident Python host socket for `host_stream` execution.
- Adapt Python values to and from SDK stream frames.
- Preserve EasyRemote's historical public names where the behavior remains
  semantically valid.

EasyNet-Cli owns product/device runtime behavior:

- `easynet-daemon` process lifecycle.
- Pairing-derived identity and local credentials.
- Ability install, uninstall, registry, lease renewal, and local/remote routing.
- Mission/EAL orchestration and product policy.
- The `host_stream` executor that connects daemon invocation to this Python
  resident host.
- SDK native transport selection, the base ABI gate, and C ABI v8 raw-stream
  feature discovery.

Axon owns protocol truth:

- Complete signed Invocation shape.
- Admission, ordering, cancellation, receipts, terminal stream semantics, and
  canonical verification.
- Canonical stream payload and content-type wire semantics.

When unsure where a feature belongs, classify it by policy ownership. If it
changes Invocation, receipts, stream terminal semantics, admission, signing, or
canonical wire shape, it does not belong in EasyRemote.

## Current Runtime Model

All EasyRemote-hosted abilities are packaged with daemon `host_stream` exec.
The public descriptor geometry still follows the Python callable:

- Plain functions are public RPC/unary abilities.
- Generator, async generator, and return-annotated `Iterator`/`Iterable`
  functions are public server-stream abilities.
- Context-taking functions inject `easyremote.Context` as the first parameter
  and still route through `host_stream`.

The resident host protocol is `binary_v1`. It is a length-prefixed Unix-socket
frame protocol with:

- Fixed magic/version/kind header.
- Bounded content-type and payload lengths.
- One request frame followed by zero or more item frames.
- Exactly one terminal/error outcome.
- Rolling SHA-256 over sequence, content type, and exact payload bytes.
- No JSON/base64 conversion for `StreamFrame` or raw `bytes` payloads on the
  host-to-daemon boundary.

This design supports low-overhead multimodal server-streaming on the local
provider boundary. Do not document it as a universal latency or bandwidth SLO.
End-to-end results depend on hardware, payload size, codec choice, daemon mode,
network path, receiver speed, and deployment topology.

## Canonical Lifecycle

Treat provider lifecycle as an explicit state machine:

```text
Python callable declared
  -> schema derived
  -> ability package written
  -> ability.deploy admitted
  -> descriptor + Axon runtime + execution-index mode committed
  -> Local active
  -> realm advertisement pending/published
  -> lease renewed or provider stopped
  -> route unbound and deployment expired/uninstalled
```

`Local active` is the local invocation readiness boundary. Realm advertisement
is a separate federation state and may remain pending while the Hub is offline.
Redeploying a public name with a different call mode must replace the previous
mode in descriptor, runtime, and execution index together. Rollback, expiry,
and uninstall must remove the same three facts.

The caller path is:

```text
typed arguments
  -> explicit InvocationDerivationPolicy
  -> SDK descriptor/identity projection
  -> exact authority binding when required
  -> active key-service managed signer
  -> daemon route selection and Axon admission
  -> host_stream execution
  -> verified terminal or structured failure
```

EasyRemote must not parse credentials, derive User UUIDs, mint authority, pick
signing keys, or select native ABI symbols along this path.

## Building A Concrete Use Case

Start with the production pain, not a protocol feature. Define one user, one
bounded task, the minimum typed inputs, the exact output projection, the local
resource that must remain private, and a deterministic terminal condition.

Choose the smallest public shape:

- Unary result: ordinary return annotation and ordinary `@remote` call.
- Incremental result: finite `Iterator[T]` and `.stream(...)`.
- Binary media: finite `Iterator[StreamFrame]` with explicit content type.
- Caller evidence: first provider argument `Context`; omit it from the caller.
- Duplex interaction: `Client.session(...)`, not an invented decorator.

Keep every Gallery case independently managed by uv. Its README must explain
`Concrete use case`, precise `Requirements`, `Existing approach`,
`EasyRemote approach`, `Effect`, and `Run` in concise English prose. Avoid
prompt-like instructions and do not simulate broader orchestration features in
the MVP.

Use `skills/easyremote-ability-builder/scripts/scaffold_case.py` only as a
starting point; replace its placeholder domain logic and claims before
delivery.

## Supported Function Shapes

Server registration supports:

- Sync unary functions.
- Async unary functions.
- Sync generators.
- Async generators.
- Ordinary functions whose return annotation is `Iterator[T]`,
  `Iterable[T]`, `AsyncIterator[T]`, or `AsyncIterable[T]`.
- Positional-only parameters.
- Keyword-only parameters.
- Defaults.
- `*args` as a JSON array under the variadic parameter name.
- `**kwargs` as additional JSON object properties.
- First-parameter `Context` injection.
- Dataclasses, enums, pydantic v2 models, JSON scalars, lists, tuples, dicts,
  mappings, sequences, `bytes`, and `StreamFrame` where schema derivation
  supports them.

Client stubs support:

- Module-level `@remote`.
- Class attribute `@remote` descriptors that strip `self`.
- Explicit `client=`, instance `self.client`, instance `self._client`, or lazy
  default `Client()`.
- `.stream(...)` for server-stream abilities.
- `.invoke(...)` for receipt-oriented invocation.
- `.aio(...)` as an async mirror that runs the sync stub in a worker thread.

Do not claim support for every Python object. File handles, sockets, arbitrary
custom objects without a schema, open device handles, and framework tensors are
not directly portable as invocation arguments. Convert them to JSON descriptors,
resource references, or `StreamFrame` byte chunks with explicit media types.

## Known Non-Goals And Limits

These are intentional until a spec and tests say otherwise:

- `@remote` is a client stub decorator. It does not publish functions; use
  `@node.register` for server registration.
- `@remote` does not create client-stream or bidirectional function decorators.
  Use `Client.session(...)` for bidi sessions.
- `StreamFrame` is for server-stream output. Request-side multimodal upload
  needs a separate client-stream/bidi contract.
- The binary host protocol is process-local Unix socket transport, not a
  network tunneling protocol.
- The installed SDK keeps the base `runtime_abi_version()` contract at 7 and
  feature-detects the additive `runtime_invocation_stream_open_v8` raw-payload
  stream extension. EasyRemote uses that SDK-owned C ABI transport; it does not
  bind ABI symbols or open an independent Axon gRPC channel itself.
- Benchmark numbers must state scope, frame count, payload size, and machine.
  Never present local Unix-socket throughput as a remote-device guarantee.

## Basic Server Example

```python
from easyremote import ComputeNode

node = ComputeNode(namespace="er")

@node.register
def add(a: int, b: int) -> int:
    return a + b

if __name__ == "__main__":
    node.serve()
```

The server must run on a machine where `easynet-daemon` is installed, paired,
and able to accept `ability.deploy`. `ComputeNode.start()` starts only the
Python resident host and deploys ability bundles through the daemon; it does
not start or pair the daemon.

## Basic Client Example

```python
from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(
    invocation_policy=FreshRoot(subject=ResolvedTargetSubject()),
)

@remote(client=client)
def add(a: int, b: int) -> int: ...

print(add(2, 3))
```

The `@remote` body is never executed. Its signature maps Python arguments into
the JSON ability argument object. The actual target descriptor is resolved by
the daemon catalogue and invoked through the SDK.

## Multimodal Server-Stream Example

```python
from collections.abc import Iterator
from easyremote import ComputeNode, StreamFrame

node = ComputeNode(namespace="er")

@node.register
def camera(frames: int) -> Iterator[StreamFrame]:
    for jpeg in capture_jpegs(frames):
        yield StreamFrame(jpeg, "image/jpeg")
```

```python
from collections.abc import Iterator
from easyremote import Client, FreshRoot, ResolvedTargetSubject, StreamFrame, remote

client = Client(
    invocation_policy=FreshRoot(subject=ResolvedTargetSubject()),
)

@remote(client=client)
def camera(frames: int) -> Iterator[StreamFrame]: ...

for frame in camera.stream(30):
    assert isinstance(frame, StreamFrame)
    consume_jpeg(frame.payload, frame.content_type)
```

Plain JSON yields arrive as Python values. Non-JSON payloads arrive as
`StreamFrame`.

## Context Example

```python
from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")

@node.register
def whoami(ctx: Context) -> dict[str, str]:
    return {
        "caller": ctx.caller,
        "invocation_id": ctx.invocation_id,
    }
```

`Context` must be the first parameter. It is injected by the host from the
daemon-relayed request envelope and is not part of the caller argument schema.

## Argument Shape Example

```python
from easyremote import ComputeNode

node = ComputeNode(namespace="er")

@node.register
def summarize(prefix: str, /, *items: str, max_words: int = 40, **tags: str) -> str:
    body = ", ".join(items)
    return f"{prefix}: {body} [{max_words}] {tags}"
```

The schema records positional order and the `*items` tail. The host rehydrates
the wire object back into positional-only arguments, varargs, keyword-only
arguments, and additional kwargs before calling the Python function.

## Bidi Example

```python
from easyremote import Client, FreshRoot, ResolvedTargetSubject

client = Client(
    invocation_policy=FreshRoot(subject=ResolvedTargetSubject()),
)

with client.session("interactive_chat") as session:
    session.send({"role": "user", "content": "hello"})
    reply = session.recv(timeout=5)
```

Bidi is intentionally a session API. Do not model it as `@remote` until the
client-stream/bidi decorator contract is specified and tested.

## Verification Commands

Run EasyRemote checks from this repository:

```bash
uv run ruff check easyremote tests benchmarks
uv run mypy easyremote
uv run pytest -q
uv run python benchmarks/host_stream_binary.py --frames 64 --frame-bytes 1048576 --runs 3
```

Run EasyNet-Cli alignment checks from the sibling repository when changing SDK
or daemon stream contracts:

```bash
cd /Users/macbook.silan.tech/Documents/GitHub/EasyNet-Cli
uv run ruff check sdk/python
uv run pytest -q sdk/python/tests
cargo fmt --check
```

Also run the focused Rust tests that cover `host_stream` binary framing,
bounded backpressure, raw progress projection, the base C ABI version gate,
and v8 raw-stream feature discovery. Keep
the exact test names in the task plan or verification log because they move
more often than the Python suite entry points.

For every project-local skill change, also run:

```bash
python /Users/macbook.silan.tech/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/easyremote-ability-builder
uv run pytest -q tests/test_easyremote_ability_builder_skill.py
```

## Definition Of Done

A change is complete only when:

- Public API behavior has a deterministic test.
- Runtime-bound behavior has a focused SDK/daemon test at the owning layer.
- A concrete application change runs through a real provider and caller when
  the required local runtime is available.
- uv locks, Ruff, mypy, and relevant pytest suites pass.
- Documentation describes the implementation that actually ran.
- Generated artifacts and test processes are cleaned up.
- Residual limits distinguish local, federation, and production guarantees.

## Change Discipline

- Read current code before editing; this repository often has dirty worktrees.
- Preserve user changes and unrelated generated outputs.
- Prefer root-cause refactors over local patches.
- Keep public behavior compatible unless the spec explicitly authorizes a
  breaking change.
- Remove obsolete internal branches after migration; do not keep compatibility
  layers whose only purpose is preserving legacy architecture.
- Keep lifecycle code as explicit state machines where possible.
- Do not duplicate protocol contracts in EasyRemote when they belong to
  EasyNet-Cli or Axon.
- Update `pr/<date>-<task>/` with intent, invariants, boundary proof,
  verification, and decisions for runtime or protocol work.
- Commit only as `Silan.Hu <silan.hu@u.nus.edu>` when the user asks for a
  commit.

## Current Stream Capability Status

As of 2026-08-22, the implemented and verified path is:

```text
Python generator
  -> EasyRemote resident HostServer
  -> binary_v1 host_stream Unix socket
  -> easynet-daemon host_stream executor
  -> Axon stream carrier
  -> Python SDK C ABI v8 raw-stream projection
  -> EasyRemote Stream / StreamFrame
```

This path is appropriate for server-produced text, audio, image, video, and
binary chunks. It is not the final answer for request-side media upload,
remote-desktop-class interactive sessions, GPU tensor zero-copy transport, or
cross-device SLO guarantees. Those require separate specs and end-to-end
benchmarks.
