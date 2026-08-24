# Verification

Run the real smoke with a workspace-built native library and paired daemon:

```bash
EASYNET_CLI_LIB=/absolute/path/to/libeasynet_cli.dylib \
EASYREMOTE_LIVE_RAW_STREAM=1 \
uv run pytest -q tests/test_integration.py::test_live_v8_raw_stream_preserves_exact_frames
```

The proof requires base ABI 7, `axon_pb=true`,
`symbols.stream_raw_payload_v8=true`, three exact media frames, and successful
provider cleanup. It is a local live-runtime proof, not a cross-device network
or zero-copy guarantee.
