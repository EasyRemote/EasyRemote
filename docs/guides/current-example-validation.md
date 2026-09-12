# Current-version example validation

Source coordinates: Axon **0.205.34**, Runtime and Python SDK **0.162.9**,
EasyRemote **2.210.2**. Runs use current native sibling builds, separate
provider/caller processes and isolated Runtime homes.

All **16 logical scenarios passed**. Original example structure and purpose are
preserved; acceptance counts provider/caller pairs as one scenario.

## Original scenarios

| Scenario | Preserved behavior | Validation |
|---|---|---|
| Nine Gallery projects | Original project providers and callers | Passed all nine; Gallery 08 also passed after correcting the implicit module remote client. |
| Hello, streaming, remote_demo | Original provider/client pairs | Passed all three, including streaming and unary results. |
| Decorator quickstart | `make_thumbnail` bytes input/output, arithmetic, fanout and latency | Passed. Unary bytes use the existing JSON/base64 codec and annotation-based decoding. |
| GPUCluster | Class-bound inference, embedding and summarization | Passed all three calls and output assertions. |
| Pipeline | First inference completion feeds a second inference in a Runtime mission | Passed: three completed steps, no failures, and final `echo(echo(step one))` output. |
| Owner handles | Device call, typed Agent stub, ad-hoc Agent call and Hub directory query | Passed: native Agent creation/publication, Device and Agent calls, and Hub query with an explicit Device subject and active-route assertion. |

The companion providers retain the original examples' contracts. GPUCluster
uses deterministic demonstration functions, not actual GPU inference.
`make_thumbnail` remains the original byte-slicing stand-in, not an image
resizer. These runs do not establish hardware operation or external MCP/A2A
interoperability.

## Native Agent setup

Run `examples/06_owner_handles_node.py` on a Device paired with a Hub. It
creates an Agent with `client.agents.add`, publishes its greeting ability with
`client.agents.put_abilities`, waits for Runtime publication, and serves it
through ComputeNode. The caller retains the Python `chat` stub but explicitly
binds it to the custom `greet` ability; built-in Agent `chat` is reserved for
the Runtime's structured model interface. This example invokes no model driver.

A standalone merged Hub/Device Runtime currently does not complete this hot
Agent publication flow. Owner acceptance therefore uses separate native Hub
and paired Device processes; publication readiness is never skipped.

See [example commands](../../examples/README.md). Earlier arithmetic,
byte-preview, and single-Device substitutions were withdrawn and do not count
as acceptance. Versions remain unchanged and no release was published.

## Regression checks

Python: 422 tests passed, 21 optional tests skipped; Ruff and mypy passed.
Runtime: 11 Mission gateway tests and four Hub dispatcher tests passed.
The resident binary stream benchmark passed (64 one-MiB frames, three runs).
Changed Rust files pass formatting checks. Whole-repository `cargo fmt --check`
still reports existing differences in untouched files; release gates are not
claimed complete. No release was published.
