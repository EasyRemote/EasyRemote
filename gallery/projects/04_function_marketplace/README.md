# Reuse an Owned Business Function Without Copying It

## Concrete use case

A customer-operations workflow needs three functions already maintained by
other teams: normalize an invoice, classify an incoming ticket, and score
customer health. The first useful marketplace is not a web storefront. It is a
small catalog in which each function has an owner, typed inputs, bounded
outputs, and a callable implementation that remains with its owning team.

The runnable MVP limits currency conversion to three known currencies, ticket
text to 2,000 characters, and health inputs to percentages or counts with
explicit ranges. These constraints make the functions safe to compose and make
failure understandable to callers.

## Requirements

- Publish independently named business functions with explicit validation.
- Keep one implementation under the original team's control.
- Let a new workflow consume functions without copying their source.
- Return stable JSON values suitable for later workflow composition.
- Avoid presenting arbitrary code execution as a marketplace capability.

## Existing approach

Internal reuse often ends at documentation or a snippet repository. A consumer
still copies code, freezes an old rule, negotiates access to another service, or
waits for the owning team to build a new endpoint. The organization knows a
function exists but lacks a low-cost callable boundary, so duplicated business
logic accumulates across repositories.

## EasyRemote approach

The owning node registers the three functions with `@node.register`. A consumer
declares only their signatures with `@remote`; the caller cannot execute an
embedded local fallback or mutate the provider's implementation. The broader
catalog can add discovery and policy around the same abilities without changing
these function contracts.

## Effect

The organization can test whether owned functions are actually reusable before
building marketplace ranking, billing, or SLA machinery. Consumers integrate
through a typed call instead of a source-code copy, and owners can improve the
implementation in place. This is the minimum evidence that a function can
become an organizational asset.

## Run

```bash
uv sync
uv run python node.py
uv run python client.py
```
