# Standalone Gallery Projects

Each subdirectory is a self-contained uv application with this contract:

- `node.py` owns the local resource and publishes bounded functions with
  `@node.register`.
- `client.py` declares typed remote stubs with `@remote` and contains no copy of
  the provider's business implementation.
- `pyproject.toml` and `uv.lock` resolve the local EasyRemote checkout and the
  sibling EasyNet SDK independently of the repository root environment.
- `README.md` argues from a concrete production demand through the limitations
  of the existing approach to the measurable effect of the MVP.

The projects are intentionally small. Their value is the boundary between the
resource owner and the caller, not the amount of demonstration code.
