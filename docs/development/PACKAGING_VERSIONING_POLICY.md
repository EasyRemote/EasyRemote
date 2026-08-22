# EasyRemote Packaging and Versioning Policy

Author: Silan Hu (silan.hu@u.nus.edu)

## Goals

- Keep runtime installation minimal and stable.
- Ship optional capabilities as explicit extras.
- Prevent version drift across package metadata and code.

## Dependency Layers

### Core runtime dependencies

The core runtime intentionally has one SDK dependency:

- `easynet-sdk>=0.142.22,<0.143`

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

Tide is the source of the next release candidate, not a second metadata source.
`.tidemark.toml` makes its annotated-tag and `+08:00` day-boundary semantics
deterministic. `scripts/bump-version.sh` resolves `tide mark --local-only` once
for a clean committed functional HEAD; `scripts/update-project-version.sh`
transactionally updates `_version.py` and the packaged edge-policy projection.
Its `--check VERSION` mode is read-only and is enforced by the publish workflow.

The migration uses two real historical anchors:

- `v2.0.1` at `742e4a653184d9e33fe611a621c30049fc87c813`
- `v2.0.2` at `e5f163bf46a37b1771c11003757d6bb6528dd029`

These two anchors establish Tide epoch 2 and keep new versions ahead of the
immutable PyPI `2.0.2` release. Do not add older pre-Tide releases as anchors.

## Release Checklist

1. Fetch annotated tags and start from a clean functional HEAD.
2. Run `./scripts/bump-version.sh --dry-run`, then
   `./scripts/bump-version.sh`.
3. Commit the synchronized version once. Do not recompute Tide solely for that
   version-only commit.
4. Run `uv sync`.
5. Run `uv lock --check --no-sources` to prove published dependency
   metadata is installable without local sibling sources.
6. Run `uv run pytest -q`.
7. Verify installation paths:
   - `pip install .`
   - `pip install .[pydantic]`
   - `pip install .[gateway]`
8. Create an annotated `v<VERSION>` tag on the version commit. Pushing this tag
   is the only publishing trigger; manual dispatch remains validation-only.
9. Ensure GitHub OIDC Trusted Publisher is configured on PyPI for this repository.
10. Publish release notes.
