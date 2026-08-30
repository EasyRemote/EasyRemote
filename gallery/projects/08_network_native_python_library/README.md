# Use a Network Function as a Native Python Library

## Concrete use case

A data team wants to use semantic operators maintained by another group. The
provider owns the model, prompts, runtime dependencies, and deployment. The
consumer wants the experience of a normal Python package: install a named
contract once, receive autocomplete and type checking, and import functions
without cloning the provider repository.

This project publishes a small `lotus` operator set. The deterministic provider
keeps the example runnable without a model download, while preserving the same
remote boundary that a production LLM-backed implementation would use.

## Requirements

- Address a package by Realm, Publisher, Package, and Interface Version.
- Install only schemas and typed call facades, never provider implementation.
- Keep Python import local, fast, and free of discovery network calls.
- Use collision-safe imports for packages published by different people.
- Route function calls through EasyNet identity, policy, transport, and receipts.
- Allow a published descriptor reference to pin the installed call contract.

## Existing approach

A consumer normally clones a repository, installs its model stack, repeats
remote stubs by hand, or accepts an HTTP client generated for a service-shaped
API. Cloning destroys implementation ownership and makes updates expensive.
Handwritten stubs drift from provider schemas. Dynamic network imports make
ordinary `import` slow, failure-prone, and unsafe. A single global package name
also collides as soon as multiple publishers offer a package called `lotus`.

## EasyRemote approach

`library.json` is an interface package. Its coordinate is
`@silan/lotus@1.0.0` in Realm `easynet.run`. EasyRemote validates the manifest
and materializes a local projection containing generated `.py`, `.pyi`,
`py.typed`, and lock metadata. The default projection is scoped by publisher:

```python
from easyremote.silan.lotus import semantic_filter, semantic_map
```

Importing this module performs no network work. Calling a function creates a
normal EasyRemote invocation. The Gallery manifest uses logical ability names
so the example can run on any paired developer device. A registry-published
manifest may additionally carry canonical Ability URAs, owner URAs, and exact
descriptor references; the installer already preserves those pins.

The files have deliberately separate ownership:

- `node.py` contains the private implementation and enforces workload bounds.
- `library.json` contains public names, signatures, schemas, and package identity.
- `inspect_library.py` inspects only the locally generated projection.
- `client.py` imports that projection exactly like an ordinary Python package.

The manifest describes the same limits enforced by the provider: 1–1,000
records, at most 2,000 characters per record, and a finite instruction set.
Provider validation remains authoritative because callers may exist outside
Python and generated type hints are not a security boundary.

## Effect

The consumer sees a native, typed Python library but does not possess the
provider implementation. `inspect.signature(semantic_filter)` works locally,
IDEs can read the generated type stub, and package identity is explicit in the
lock file. The provider can replace its internal algorithm without forcing a
consumer clone, provided the installed interface contract remains compatible.

The remaining platform step is Realm-wide resolution of a coordinate such as
`@silan/lotus@^1.0` into this manifest. This example does not pretend that the
current EasyNet control plane already supplies that registry operation.

## Run

Install the interface projection:

```bash
uv sync
export EASYREMOTE_LIBRARY_ROOT="$PWD/.libraries"
uv run easyremote add library.json
uv run python inspect_library.py
```

The inspection should report `easyremote.silan.lotus`, both typed signatures,
and exactly four interface artifacts: `__init__.py`, `__init__.pyi`, `py.typed`,
and `easyremote-library.lock.json`. It should not contain `node.py` or the
provider's `_terms` implementation.

Start the provider in one terminal:

```bash
uv run python node.py
```

Then call it from another terminal with the same environment variable:

```bash
uv run python client.py
```

The client prints the three input records, keeps the two invoice-related
records, and returns a lowercase projection. To observe a contract failure,
change the map instruction to `write a poem`; the provider rejects it rather
than interpreting an unbounded instruction.

Both callers need a paired, running EasyNet runtime. Use `easynet login`,
`easynet device join <pairing-token>`, `easynet runtime start`, and
`easyremote doctor` before the live call.
