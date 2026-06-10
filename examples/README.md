# EasyRemote v2 Examples

One-time prerequisites on every machine involved:

```bash
# 1. Pair this device into your realm (issues identity + credentials)
easynet pair

# 2. Register the agent namespace these examples publish under
easynet agent add --type claude-code er

# 3. Make sure the daemon is up
easynet start

# 4. Sanity-check the whole link
easyremote doctor
```

| Example | What it shows |
|---|---|
| `01_hello_node.py` | Register a local function as a capability and serve it warm |
| `02_hello_client.py` | Call it three ways: result-first, typed stub, full invocation object |
| `03_pipeline.py` | Compose capabilities into an EAL mission and submit it |

Run the node in one terminal, then the client in another:

```bash
python examples/01_hello_node.py
python examples/02_hello_client.py
```
