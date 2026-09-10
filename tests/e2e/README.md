# Paired-device function matrix

This exercises a real installed candidate Runtime, its SDK transport, and an
EasyRemote provider. It does not substitute a test transport or bypass admission.
It requires matching candidate CLI, Axon SDK, EasyNet SDK and EasyRemote sources;
NumPy and Pydantic must be installed on both devices. A local `localhost` realm
alone does not pair two devices. Enroll both devices into the same test realm
before this test and verify `easynet status` on each.

On provider B, from the EasyRemote checkout:

```bash
python tests/e2e/function_matrix.py provider --ready-file ./matrix-ready.json
```

Wait for `matrix-ready.json`, then obtain B's device ID from its Runtime status.
On caller A, from the matching EasyRemote checkout:

```bash
PROVIDER_DEVICE_ID='<B device ID from Runtime status>'
python tests/e2e/function_matrix.py caller --node "$PROVIDER_DEVICE_ID"
```

A passing command prints JSON and exits zero. It asserts custom classes nested
in a dataclass, non-contiguous NumPy data with an explicit non-native byte order,
and a Pydantic model retain their declared types and values. It also requires
sync and async duplex providers to echo exact audio bytes before the caller
half-closes its input, and then produce a terminal receipt. The receipt assertion
uses the SDK projection; it is not an independent offline proof verifier.

Use `--case objects` or `--case duplex` to isolate a failure. Passing one case is
not full acceptance. The caller explicitly discovers B's catalog first: cold
remote descriptor resolution remains a separate first-use acceptance item.
Stop the provider with Ctrl-C; its resident host is closed and the ready file
removed. Do not delete or copy device credentials to reset this exercise.

For Docker, run the provider and caller commands with `docker exec` inside the
paired provider/caller containers created by EasyNet-Cli's
`tools/scripts/docker-two-node-easyremote-cli-e2e.sh --keep`. Mount this checkout
and the matching SDK checkouts as that runner specifies. Use the Element-only
environment wrapper on the build Mac. Keep the runner's evidence and source
revision manifest with the matrix output.

## Recorded candidate result (2026-09-10)

Runtime `bc8b742d`, EasyRemote `4bb8b4a`: `--case objects` passed between
separately enrolled Docker provider and caller through a real Hub. The
`--case duplex` check remains unpassed. This is a source-candidate result, not
an installed public-release or official-Hub certification.

Runtime `b36af7e9` removes the custom Bidi publication gate, but the complete
paired matrix fails with `PROTOCOL_MISMATCH` when the direct FFI receives an
internal callback carrier frame. Object assertions complete before this failure.
Do not treat the route fix or the local carrier unit tests as full duplex
acceptance. Upstream media-type projection also needs descriptor-based routing.

## Latest verified result

Runtime `28a7d9e3` + Axon `0a65a1f0` passed the complete matrix on 2026-09-10
in the paired Linux ARM64 Docker topology. Both sync and async providers echoed
exact audio before input half-close, returned the JSON summary on declared
stream 2, and produced `Completed` terminal receipts with cleanup complete.
Custom classes, dataclasses, Pydantic and NumPy assertions also passed.

This supersedes the earlier custom-Bidi route and FFI failures above. It does
not certify ordinary server-stream transcript forwarding, official-Hub
installation, presentation timestamp fidelity or throughput. Output routing
requires unambiguous declared media types; duplicate-media output streams are
not supported by this candidate's resident-host API.
