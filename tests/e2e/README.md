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
