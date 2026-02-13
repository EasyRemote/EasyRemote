# EasyRemote Quick Start Guide

## 🚀 Get Started with EasyRemote in 5 Minutes

EasyRemote enables you to build distributed computing networks in the simplest way possible. With just 12 lines of code, you can deploy local functions as globally accessible services.

## 📦 Installation

```bash
pip install easyremote
```

For repository development/testing workflow, use uv:

```bash
uv sync
uv run pytest -q
```

## 🎯 Core Concepts

EasyRemote is built on three core components:

- **Server (Gateway Server)**: Coordinates and routes requests, typically deployed on a VPS
- **ComputeNode (Compute Node)**: Devices that provide actual computational resources
- **Client**: Applications that invoke remote functions

## ⚡ Quick Example

### 1. Start the Gateway Server (on VPS)

```python
# vps_server.py
from easyremote import Server

# Start the gateway server
server = Server(port=8080)
server.start()
```

### 2. Register a Compute Node (on your device)

```python
# compute_node.py
from easyremote import ComputeNode

# Connect to the gateway server
node = ComputeNode("your-vps-ip:8080")

# Register a simple function
@node.register
def add_numbers(a, b):
    return a + b

# Register an AI inference function
@node.register
def ai_inference(text):
    # Here you can call your local AI model
    return f"AI processing result: {text}"

# Start providing services
node.serve()
```

### 3. Call Remote Functions (from anywhere)

```python
# client.py
from easyremote import Client

# Connect to the gateway server
client = Client("your-vps-ip:8080")

# Call remote functions
result1 = client.execute("add_numbers", 10, 20)
print(f"Calculation result: {result1}")  # Output: 30

result2 = client.execute("ai_inference", "Hello World")
print(f"AI result: {result2}")  # Output: AI processing result: Hello World
```

## 🎉 Success!

Congratulations! You have successfully:
- ✅ Deployed a distributed computing network
- ✅ Turned local functions into globally accessible services
- ✅ Achieved zero cold-start function calls

## 🔗 Next Steps

- 📖 [Detailed Installation Guide](installation.md)
- 💡 [Core Examples](examples.md)
- 🌐 [MCP Implemented Scope](../../ai/mcp-integration.md)
- 🤝 [A2A Implemented Scope](../../ai/a2a-integration.md)
- 🧪 Gallery smoke test: `uv run python gallery/run_smoke_tests.py`

## 💡 Tips

- Ensure network connectivity between VPS and compute nodes
- Configure firewall and security authentication for production environments
- Multiple compute nodes can be registered under one gateway
- Supports various load balancing strategies

---

*Language: English | [中文](../../zh/user-guide/quick-start.md)* 
