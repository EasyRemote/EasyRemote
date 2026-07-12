# EasyRemote Packaging and Versioning Policy

Author: Silan Hu (silan.hu@u.nus.edu)

## Goals

- Keep runtime installation minimal and stable.
- Ship optional capabilities as explicit extras.
- Prevent version drift across package metadata and code.

## Dependency Layers

### Core runtime dependencies

The core runtime intentionally has one SDK dependency:

- `easynet-sdk>=0.91.30`

The native runtime is provided by EasyNet CLI through `easynet-sdk`. Users
either install EasyNet CLI so the SDK can discover the daemon/library, or
point `EASYNET_CLI_LIB` / `configure(library_path=...)` at an explicit ABI
library. A future platform wheel may bundle that library, but this repository
must not advertise bundled native bytes until the binary-wheel pipeline
actually ships them.

### Optional extras

- `pydantic`: optional Pydantic schema support.
- `gateway`: optional gateway compatibility dependencies.

## uv Group Policy

`pyproject.toml` defines dependency groups for uv:

- `dev`

The default uv group is:

- `dev`

So a plain `uv sync` in repository context gives a usable development + testing environment.

## Single Source of Version Truth

Package version is defined in:

- `easyremote/_version.py` as `__version__`

`pyproject.toml` uses setuptools dynamic version:

- `[project] dynamic = ["version"]`
- `[tool.setuptools.dynamic] version = {attr = "easyremote._version.__version__"}`

`easyremote/__init__.py` imports from `easyremote._version`.

## Release Checklist

1. Update `easyremote/_version.py`.
2. Run `uv sync`.
3. Run `uv lock --check --no-sources` to prove published dependency
   metadata is installable without local sibling sources.
4. Run `uv run pytest -q`.
5. Verify installation paths:
   - `pip install .`
   - `pip install .[pydantic]`
   - `pip install .[gateway]`
6. Merge to `main` (or trigger `Publish easyremote to PyPI` manually).
7. Ensure GitHub OIDC Trusted Publisher is configured on PyPI for this repository.
8. Publish release notes.
