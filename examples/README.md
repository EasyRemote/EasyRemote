# EasyRemote v2 Examples

One-time prerequisites on every machine involved:

```bash
# 1. Pair this device into your realm.
easynet pair

# 2. Start the local daemon.
easynet start

# 3. Sanity-check library / daemon / identity / transport.
easyremote doctor
```

| Example | What it shows |
|---|---|
| `01_hello_node.py` | Register a local function as a capability and serve it warm |
| `02_hello_client.py` | Call it three ways: result-first, typed stub, full invocation object |
| `03_pipeline.py` | Compose capabilities into an EAL mission and submit it |
| `04_streaming_node.py` | Register a host_stream producer that yields multiple frames |
| `04_streaming_client.py` | Consume stream frames and the terminal value |
| `remote_demo_node.py` | Minimal remote demo node using the current facade |
| `remote_demo_client.py` | Minimal remote demo client using the current facade |

Run the node in one terminal, then the client in another:

```bash
python examples/01_hello_node.py
python examples/02_hello_client.py
```
