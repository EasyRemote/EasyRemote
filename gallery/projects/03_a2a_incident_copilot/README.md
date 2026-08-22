# Incident Evidence Without an SSH Session

## Concrete use case

An on-call engineer receives a latency alert for one of three production
services. Before deciding on remediation, the engineer or incident agent needs
a bounded diagnosis and several recent evidence samples. The minimum task does
not restart anything: it accepts an allowlisted service, restricts the lookback
window to 1–60 minutes, returns a structured diagnosis, and streams at most ten
ordered samples.

The fixture represents metrics already available on the provider machine. A
real deployment replaces the fixture reads with local observability adapters;
it should preserve the allowlist and bounded response contract.

## Requirements

- Provide read-only diagnosis before any remediation capability.
- Reject arbitrary service names, shell commands, and unbounded time ranges.
- Attribute diagnosis to the caller and invocation identifier.
- Stream a finite sequence so the consumer can process evidence incrementally.
- Produce a deterministic terminal result even when no anomaly is present.

## Existing approach

Incident response commonly begins with SSH access, copied shell commands, and
manual context switching among dashboards. SSH grants a machine boundary when
the task needs only a diagnostic boundary. General shell tools are difficult to
authorize narrowly, and agent-generated transcripts are weak evidence of which
operation actually ran.

## EasyRemote approach

The provider publishes only `diagnose_service` and `stream_evidence` with
`@node.register`. The caller uses typed `@remote` stubs; neither the human nor
an agent receives a command channel. EasyRemote carries the bounded call while
the runtime supplies identity and receipt semantics.

## Effect

The first incident-automation milestone becomes safe evidence collection, not
autonomous remediation. An on-call engineer can retrieve the same normalized
facts without machine credentials, and an agent can consume them through the
same contract. A2A task planning, human approval, rollback, and durable incident
state remain outside this deliberately small MVP.

## Run

```bash
uv sync
uv run python node.py
uv run python client.py
```
