# Request-side media and duplex functions (source candidate)

This candidate adds a provider `Duplex` parameter, incremental binary input,
concurrent send/receive, and input half-close. It requires the matching Runtime
and Python SDK changes; older runtimes reject `binary_duplex_v1` instead of
silently treating it as a server stream. This is not a published package or an
official-Hub acceptance result.

## Provider

Given an installed, paired, running Runtime, save this as `provider.py`:

```python
from easyremote import ComputeNode, Duplex

node = ComputeNode()

@node.register
def media_echo(channel: Duplex) -> None:
    count = 0
    for frame in channel:
        channel.send(frame)  # responds before the upload ends
        count += 1
    channel.send({"received": count})  # input closed; output still open

node.serve()
```

`Duplex` must be the first argument, after optional `Context`. Other typed
arguments are declared normally. Return `None`; use `send` for output values.
An upload-and-aggregate function can read all chunks incrementally and send its
single result after input closes. Async functions use `async for` / `arecv()`
and `await channel.asend(value)`. One receive may run at a time; a sender and
receiver may run concurrently. Binary values arrive as `StreamFrame`; JSON
frames arrive as Python values. EOF without an explicit half-close is an error.

## Caller

Use the actual provider device URA from your paired deployment. The example
uses a new causal invocation policy and declares its media lane explicitly:

```python
import base64
from easynet_sdk import BidiStreamDescriptor as StreamSpec
from easyremote import Client, CallTarget, FreshRoot, ResolvedTargetSubject, StreamFrame

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
provider_device_ura = "<provider device URA>"
target = CallTarget("media_echo", node=provider_device_ura)

with client.session(target, streams=[StreamSpec(stream_id=1, content_type="audio/pcm", ordering="STRICT")]) as session:
    session.send_frame(StreamFrame(b"\x00\x01\xff", "audio/pcm"), sequence=1)
    # Receive now, before close_send: this must not wait for all input.
    reply = session.recv(timeout=5)
    # Canonical receive frames may include admission/control events.
    while reply is not None and reply.get("kind") != "data":
        if reply.get("terminal"):
            raise RuntimeError("session ended before echo")
        reply = session.recv(timeout=5)
    assert reply is not None
    assert base64.b64decode(reply["payload_base64"]) == b"\x00\x01\xff"
    session.close_send()
    # Input is closed; continue receiving the final output and terminal receipt.
    while True:
        frame = session.recv(timeout=5)
        if frame is None:
            raise RuntimeError("missing explicit terminal frame")
        print(frame)
        if frame.get("terminal"):
            break
```

`sequence` follows the SDK's canonical send sequence, starting at 1; increment
it for subsequent sends. `stream_id` must match the declared lane. For multiple
in-flight frames, run bounded send and receive loops concurrently: sending an
unbounded batch before reading responses can exhaust either endpoint's buffers.
`cancel(reason)` requests canonical cancellation; keep receiving its outcome.
`close()` releases the local carrier and is not proof of remote cancellation.
Do not retry a side-effecting invocation solely because the local wait timed out.

The example's final JSON progress message and canonical terminal receipt are
separate events. The receipt output includes the verified host frame count and
rolling output hash; the Runtime owns signing, admission and verification.

## Verification commands

Run from the source candidate worktree with its matching SDK installed:

```bash
.venv/bin/python -m pytest -q tests/test_duplex.py tests/test_host.py
.venv/bin/python -m pytest -q tests/test_value_codec.py
```

For the Element-only Colima environment, Linux resident-host verification is:

```bash
ENV_RUN=/Volumes/Element/Tools/easynet-containers/env.sh
ER=/Volumes/Element/Github2/EasyRemote-value-fidelity
CLI=/Volumes/Element/Github2/EasyNet-Cli-first-use
AXON=/Volumes/Element/Github2/EasyNet-Axon-first-use
"$ENV_RUN" docker --context colima-first-use build \
  -t easynet/duplex-host-tests:local "$ER/tests/docker"
"$ENV_RUN" docker --context colima-first-use run --rm --network none \
  --cpus 2 --memory 1g \
  -v "$ER:/src/EasyRemote:ro" \
  -v "$CLI:/src/EasyNet-Cli:ro" \
  -v "$AXON:/src/EasyNet-Axon:ro" \
  easynet/duplex-host-tests:local
```

These checks exercise real local sockets on macOS/Linux, SDK projections, and
Runtime byte pumping separately. They do not exercise pairing, official-Hub
routing, or cross-device cancellation/receipt recovery. The caller/provider
example above still requires that deployment-level acceptance.

## Resource and lifecycle limits

The resident host admits at most 32 concurrent calls and rejects excess calls
with RESOURCE_EXHAUSTED. Stopping the host shuts down active sockets. The duplex
pump has two buffered frames per lane; framing retains the existing 64 MiB
per-frame ceiling. The Runtime's invocation and stream limits also apply.
Provider code must cooperate with cancellation by reading/writing its channel;
closing a socket does not interrupt arbitrary CPU-bound Python code. Long-lived
background work must use separately governed job lifecycle APIs.

## Recorded verification (2026-09-10)

Matching Runtime/SDK commits: `fd27897e` and `6cd1f69e` in
EasyNet-Cli's `codex/document-first-use` worktree. Three Rust tests passed;
673 SDK tests and 274 subtests passed. EasyRemote's full suite passed 403 tests
with four skips. The Linux Docker suite passed 52 tests, including actual
media/socket roundtrips, array fidelity, connection limits and host stop.
An initial Linux run exposed a blocking accept shutdown; after fixing listener
shutdown, the suite completed in 0.30 seconds. These scopes do not establish
an official-Hub cross-device result.
