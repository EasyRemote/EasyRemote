# Decorator quickstart

Recreated from the v1 `examples/decorator_route/` demos on the v2
(EasyNet-native) API.

| File | Shows |
|---|---|
| `compute_node.py` | `@node.register` — sync math, async summarizer, multimodal bytes (image → thumbnail) |
| `client.py` | transparent `@remote` stubs, `asyncio.gather` fan-out via `.aio`, multimodal round trip, warm-latency report |
| `stream_quickstart.py` | streaming status, honestly: consumer surface live, generator producers unlock with EasyNet-Cli PR-1 |
| `bench_latency.py` | the transport floor — runnable **without a daemon** |

## Low latency

The per-invocation transport floor (spawn forwarder → stdin → UDS →
warm function → stdout), measured on this machine:

```
python shim        p50   63.4ms
native forwarder   p50    1.7ms     (lazily compiled C, automatic)
```

The C fast forwarder compiles itself on first use (any `cc`/`clang`/
`gcc`), caches under `~/.easynet/easyremote/bin/`, and falls back to
the Python shim when no compiler exists (`EASYREMOTE_FORWARDER=python`
forces the fallback). The daemon host-attach protocol (Cli PR-1)
removes the spawn entirely.

## Running

```bash
easynet pair          # once per machine
easyremote doctor     # sanity-check the link

python examples/decorator_quickstart/compute_node.py   # terminal 1
python examples/decorator_quickstart/client.py         # terminal 2
python examples/decorator_quickstart/bench_latency.py  # no daemon needed
```
