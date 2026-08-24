# Verification

```bash
uv run pytest -q
uv run ruff check easyremote tests
uv run mypy easyremote
EASYNET_CLI_LIB=/absolute/path/to/libeasynet_cli.dylib \
EASYREMOTE_LIVE_RAW_STREAM=1 \
uv run pytest -q tests/test_integration.py::test_live_v8_raw_stream_preserves_exact_frames
```

The live smoke places the real package inside the EasyRemote checkout while the
daemon runs from EasyNet-Cli. A short symlink only keeps the macOS Unix socket
under `sun_path`; path resolution still points at the foreign workspace. The
test proves upload, receipt validation, deploy, raw stream, uninstall, and
cleanup compose through the real daemon.
