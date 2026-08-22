---
name: easyremote-ability-builder
description: Build, review, or diagnose EasyRemote Python capabilities that publish functions with @node.register and consume them with typed @remote stubs. Use for creating uv-managed provider/client projects, targeting paired devices, adding finite JSON or binary server streams, injecting caller Context, converting an existing local function into a governed ability, or troubleshooting EasyRemote identity, authority, signer, deployment, routing, and C ABI stream failures.
---

# EasyRemote Ability Builder

Build the smallest governed capability that solves one concrete task. Keep
identity, signing, authority, routing, receipts, and native transport inside
EasyNet-Cli and Axon.

## Start from repository truth

1. Read the repository `Agent.md` before changing code.
2. Inspect the nearest case under `gallery/projects/` instead of inventing an
   API shape from memory.
3. Read [references/api-patterns.md](references/api-patterns.md) for exact
   unary, stream, media, context, and device-targeting patterns.
4. Read [references/diagnostics.md](references/diagnostics.md) only when the
   runtime or a live invocation fails.

## Define the capability contract

Write down these facts before implementing:

- Primary user and the production pain they face.
- One minimum task the provider will expose.
- Typed inputs, explicit bounds, and rejected values.
- Output projection and whether it contains sensitive source data.
- Side effects, replay behavior, and concurrency ownership.
- Execution host: local device, selected paired device, Agent, or Hub.
- Call shape: unary, finite server stream, raw media stream, or bidi session.

Reject a design that exposes arbitrary shell commands, SQL, filesystem paths,
prompts, device handles, or unbounded item counts when a task-specific function
can express the same job.

## Select one public shape

| Task | Provider return | Caller operation |
|---|---|---|
| One result | JSON-compatible `T` | `stub(...)` or `client.call(...)` |
| Incremental finite results | `Iterator[T]` / `AsyncIterator[T]` | `stub.stream(...)` |
| Image, audio, video, bytes | `Iterator[StreamFrame]` | `stub.stream(...)` |
| Caller attribution | First argument `ctx: Context` | Do not declare `ctx` on caller stub |
| Interactive duplex exchange | Runtime bidi ability | `Client.session(...)` |

Do not model request-side streaming or bidi as an `@remote` decorator. Do not
call `.invoke()` for an EasyRemote-hosted `host_stream` result when `.call()` or
`.stream()` is the declared public behavior.

## Create an isolated uv project

Use the scaffold for a new case:

```bash
python skills/easyremote-ability-builder/scripts/scaffold_case.py \
  gallery/projects/08_example --name inspect_asset --workspace-sources
cd gallery/projects/08_example
uv lock
uv run ruff check node.py client.py
```

Add `--stream` for a finite JSON stream. Replace the scaffold domain logic and
README claims with the real bounded task before delivery. Keep `pyproject.toml`
and `uv.lock` inside the case directory.

## Implement the provider

1. Create one `ComputeNode(namespace="er")`.
2. Register only task-level functions with `@node.register`.
3. Type every public parameter and return value.
4. Validate allowlists, ranges, payload sizes, and item counts before touching
   the local resource.
5. Keep credentials, model handles, database connections, and hardware handles
   provider-local.
6. Make every stream finite and give every binary frame an explicit media type.
7. Make mutations idempotent by invocation identity or document why they are
   not; protect shared in-memory state with one owning abstraction.
8. End the executable module with `node.serve()`.

## Implement the caller

1. Construct one explicit client:

   ```python
   client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
   ```

2. Declare an `@remote(client=client)` stub with the provider's public name,
   parameters, defaults, and return annotation.
3. Add `node=<stable device id>` or an owner handle only when the use case
   requires explicit targeting.
4. Consume unary and stream results through the matching operation.
5. Close long-lived clients in application lifecycle code.

Never read `credentials.json`, substitute a username for the paired `user_id`,
mint delegation/session authority, choose a legacy signer, construct a
Device-owned Ability URA, bind C ABI symbols, or open a direct Axon gRPC channel
from EasyRemote code. The SDK and daemon own those decisions.

## Document the case

Write concise English prose under these headings:

1. `Concrete use case`
2. `Requirements`
3. `Existing approach`
4. `EasyRemote approach`
5. `Effect`
6. `Run`

State measurable bounds and the deliberate MVP boundary. Describe the existing
approach's operational mismatch without prompt-like instructions or inflated
claims. Never present local Unix-socket benchmarks as cross-device guarantees.

## Verify the delivery

Run the narrow project gates first:

```bash
uv lock --check
uv run ruff check node.py client.py
uv run python node.py
uv run python client.py
```

Run repository gates when editing EasyRemote itself:

```bash
uv run ruff check easyremote tests benchmarks gallery
uv run mypy easyremote
uv run pytest -q
```

For SDK, authority, signer, daemon routing, or ABI changes, move to the sibling
EasyNet-Cli repository and run its Python SDK tests plus the focused Rust suite.
Do not claim cross-device completion unless a live Hub and two runtime endpoints
were actually exercised.
