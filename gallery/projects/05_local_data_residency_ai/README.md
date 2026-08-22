# Move the Function to Sensitive Data

## Concrete use case

A hospital analytics team needs a sanitized case summary and bounded risk
labels from patient notes stored inside a protected environment. The remote
workflow may provide a record identifier, but it must never receive the raw
note, a database credential, or an unrestricted query interface. The provider
must also retain the caller and invocation identifiers alongside the released
projection.

This MVP contains two synthetic records. Its release contract is precise: one
known identifier enters; a summary of at most 160 characters, an allowlisted
set of risk labels, and audit identifiers leave. The local `sanitize` function
is the seam where a production redaction or local-model pipeline belongs.

## Requirements

- Resolve records exclusively inside the provider boundary.
- Reject unknown identifiers without revealing the record inventory.
- Remove direct identifiers before producing the summary.
- Release only allowlisted risk labels and bounded text.
- Attribute every projection to the runtime-supplied caller and invocation.

## Existing approach

Central AI pipelines typically upload source documents to a cloud model or
copy them into a shared analytics store. That simplifies orchestration by
weakening data residency. A fully isolated local script preserves residency but
usually falls out of remote workflows, leading to manual exports and informal
handoffs that are difficult to audit.

## EasyRemote approach

The protected node registers `summarize_patient_record` with
`@node.register`. The external workflow calls an `@remote` stub containing only
the record identifier. Execution and source data stay local; the capability
returns the explicitly released projection. EasyRemote supplies the function
boundary, while data access and sanitization remain owned by the hospital.

## Effect

The team can test remote orchestration without testing whether sensitive data
may leave its boundary. The caller gets a useful structured result, and the
data owner keeps records, processing code, and release policy local. Production
deployment still requires clinical validation, durable audit storage, and
organization-specific authorization; this project does not substitute for
those controls.

## Run

```bash
uv sync
uv run python node.py
uv run python client.py
```
