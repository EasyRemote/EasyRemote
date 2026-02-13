# EasyRemote Packaging and Versioning Policy

Author: Silan Hu (silan.hu@u.nus.edu)

## Goals

- Keep runtime installation minimal and stable.
- Ship optional capabilities as explicit extras.
- Prevent version drift across package metadata and code.

## Dependency Layers

### Core runtime dependencies

These are required for normal gateway/node/client runtime:

- `grpcio`
- `protobuf`
- `rich`
- `pyfiglet`
- `psutil`

### Optional extras

- `gpu`: installs `GPUtil` for GPU usage metrics collection.
- `build`: installs `grpcio-tools` for protobuf/gRPC code generation.
- `dev`: development toolchain and test dependencies.
- `test`: test dependencies only.
- `docs`: documentation toolchain.

## uv Group Policy

`pyproject.toml` defines dependency groups for uv:

- `dev`
- `test`
- `docs`

Default uv groups are:

- `dev`
- `test`

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
3. Run `uv run pytest -q`.
4. Verify installation paths:
   - `pip install .`
   - `pip install .[gpu]`
   - `pip install .[build]`
5. Merge to `main` (or trigger `Publish easyremote to PyPI` manually).
6. Ensure GitHub OIDC Trusted Publisher is configured on PyPI for this repository.
7. Publish release notes.
