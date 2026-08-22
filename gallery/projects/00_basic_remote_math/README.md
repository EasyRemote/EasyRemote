# A Quote Function Before a Quote Service

## Concrete use case

A sales engineer owns the pricing rule for an early product. Account executives
need to calculate quotes during customer calls tomorrow, but the rule still
lives in a Python notebook. The minimum useful interface accepts a known plan,
between 1 and 5,000 seats, and an annual-billing flag. It returns integer money
values in cents so that the result is deterministic and does not inherit binary
floating-point ambiguity.

The demand is narrow but real: several people need the same answer, the owner
must retain one implementation, and a caller should not receive access to the
engineer's machine or source tree.

## Requirements

- Publish one typed `calculate_quote` capability.
- Reject unknown plans and seat counts outside the commercial range.
- Keep pricing logic on the provider machine.
- Give the caller an ordinary Python function signature and structured result.
- Reach one terminal result per invocation; no background job is necessary.

## Existing approach

The common response is a temporary HTTP service or a shared spreadsheet. The
HTTP service adds routing, serialization, deployment, authentication, and
operational ownership before demand is proven. The spreadsheet is easy to
share but forks the pricing rule, weakens validation, and makes later automation
depend on a document rather than an owned function.

## EasyRemote approach

The provider registers the existing calculation with `@node.register`. The
caller declares the same typed boundary with `@remote`; its body contains no
pricing logic. EasyRemote turns the function boundary into an Ability while the
paired runtime owns identity, admission, routing, and receipts.

## Effect

The first integration unit is one validated function instead of one newly
operated service. The pricing owner can change the implementation in one place,
and callers receive a stable capability without obtaining machine access. This
MVP proves remote product feedback; it does not claim to replace billing,
approval, or contract systems.

## Run

```bash
uv sync
uv run python node.py       # provider terminal
uv run python client.py     # caller terminal
```
