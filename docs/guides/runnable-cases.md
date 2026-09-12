# Runnable source examples

The aligned source versions are Axon **0.205.34**, EasyNet Runtime **0.162.9**,
Python `easynet-sdk` **0.162.9**, and EasyRemote **2.210.2**. These are distinct
release coordinates. EasyRemote accepts `easynet-sdk>=0.162.9,<0.163`; that SDK
accepts `axon-runtime-sdk>=0.205.34,<0.206`.

Keep the three repositories as siblings. The Gallery projects use local uv
sources and checked locks. Before running, install and pair the EasyNet Runtime
and confirm `easynet runtime status --json` reports running. Provider and caller
use separate terminals; the provider stays running. This guide is a source
checkout entry point, not a claim that these versions have been published.

| Case | Directory under `gallery/projects/` | Result and scope |
|---|---|---|
| Quote calculation | `00_basic_remote_math` | Typed plan/seat inputs produce a deterministic quote in cents. |
| Business tool backend | `02_mcp_tool_mesh` | Account/revenue queries and bounded follow-up tasks on synthetic data; this case does not itself start an MCP server. |
| Local data projection | `05_local_data_residency_ai` | Synthetic records remain at the provider; caller gets a bounded summary and audit identity. Not a production medical/redaction system. |

For example, from the EasyRemote checkout:

```bash
cd gallery/projects/00_basic_remote_math
uv sync --locked
uv run --locked python node.py
```

In a second terminal, from the same case directory:

```bash
uv run --locked python client.py
```

Use the same pair of commands in either of the other listed case directories.
For the smallest echo-like example, run `examples/01_hello_node.py` and
`examples/02_hello_client.py` from the repository root after `uv sync --locked`.

## Existing Runtime acceptance scenarios

The sibling EasyNet-Cli repository contains
`packaging/docker/e2e/document-first-use/document-authorization.md`,
`receipt-capture.md` and `response-loss.md`. Their retained Alice/Bob deployment
has exercised exact document permission, expiry/revocation, offline signature
verification, lost responses and replay across restart. It uses recorded
candidate/historical components and is not a clean installation of this release.

`document-revision.md` covers transactional business operation IDs and independent
process recovery. Its Runtime integration remains pending; do not list it as an
end-to-end deployed example yet.
