# EasyRemote v2 Examples

One-time prerequisites on every machine involved:

```bash
# 1. Pair this device into your realm.
easynet pair

# 2. Start the local device daemon.
easynet start

# 3. Sanity-check library / daemon / identity / transport.
easyremote doctor

# Hub machines can start the hub daemon through the EasyRemote facade.
easyremote hub --realm my-team

# Existing EAL files can be submitted through the same daemon facade.
easyremote mission run ./nightly.eal --label nightly
```

| Example | What it shows |
|---|---|
| `01_hello_node.py` | Register a local function as a capability and serve it warm |
| `02_hello_client.py` | Call it three ways: result-first, typed stub, full invocation object |
| `03_pipeline.py` | Compose capabilities into an EAL mission and submit it |
| `04_streaming_node.py` | Register a host_stream producer that yields multiple frames |
| `04_streaming_client.py` | Consume stream frames and the terminal value |
| `05_remote_on_class.py` | `@remote` as a class attribute: name from the attribute, client from the host, `self` stripped |
| `06_owner_handles.py` | Owner handles (`client.device/agent/hub`) + `@handle.remote` — the client mirror of `@node.register` |
| `remote_demo_node.py` | Minimal remote demo node using the current facade |
| `remote_demo_client.py` | Minimal remote demo client using the current facade |

Run the node in one terminal, then the client in another:

```bash
python examples/01_hello_node.py
python examples/02_hello_client.py
```
