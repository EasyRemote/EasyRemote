# Decorator quickstart

Recreated from the v1 `examples/decorator_route/` demos on the v2
(EasyNet-native) API.

| File | Shows |
|---|---|
| `compute_node.py` | `@node.register` — sync math, async summarizer, multimodal bytes (image → thumbnail) |
| `client.py` | transparent `@remote` stubs, `asyncio.gather` fan-out via `.aio`, multimodal round trip, warm-latency report |

## Execution path

Each registered function is deployed as a device-owned ability whose
manifest uses the daemon's `host_stream` executor. The daemon connects
directly to the warm Python host socket, so there is no per-call Python
or native package-level shim.

Use `examples/04_streaming_node.py` and `examples/04_streaming_client.py`
for the dedicated streaming proof.

## Running

```bash
easynet pair          # once per machine
easyremote doctor     # sanity-check the link

python examples/decorator_quickstart/compute_node.py   # terminal 1
python examples/decorator_quickstart/client.py         # terminal 2
```
