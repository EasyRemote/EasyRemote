# An Owned Tool Boundary for Enterprise Agents

## Concrete use case

A sales agent needs three narrow business operations: read an account, read its
recent revenue series, and create a follow-up task. The CRM team owns account
facts; sales operations owns task creation. The agent should call those
functions through stable schemas without receiving database credentials or a
general-purpose CRM session.

The MVP contains two known account identifiers, a revenue window of one to six
months, a four-person owner allowlist, a due date between one and thirty days,
and an in-memory fixture capped at one hundred follow-ups. The bounded dataset
keeps the project runnable; the function boundaries are the parts retained when
real system adapters replace the fixtures.

## Requirements

- Expose business operations rather than a generic database or HTTP proxy.
- Validate account identifiers, owner identity, time window, and due date.
- Keep each system's implementation and credentials on its provider node.
- Carry caller and invocation identity into the write operation.
- Return JSON-compatible values suitable for a tool adapter.

## Existing approach

Point-to-point agent integration gives each agent its own wrapper, credential
set, error mapping, and undocumented return conventions. As the number of
agents and systems grows, ownership becomes unclear and a tool can silently
turn into broad backend access. MCP improves presentation, but presentation
alone does not create a governed execution boundary behind the tool.

## EasyRemote approach

`node.py` registers the three owned functions as EasyRemote abilities.
`client.py` declares typed `@remote` stubs of the kind an agent adapter can
invoke. The daemon's MCP surface may present those abilities separately; this
project intentionally demonstrates only the capability backend and does not
reimplement an MCP server.

## Effect

An agent platform can validate a reusable tool backend without coupling the
agent directly to CRM internals. Business owners keep code and credentials,
while calls have explicit inputs, outputs, caller identity, and receipts. The
MVP is not a complete enterprise tool catalog; it establishes the smallest
owned unit from which one can be built.

## Run

```bash
uv sync
uv run python node.py
uv run python client.py
```
