# EasyRemote Quick Start Guide

##  Get Started with EasyRemote in 5 Minutes

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

##  Core Concepts

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

### 4. Convert Local Calls to Stable Remote + Streaming in a Few Lines

```python
from easyremote import remote
from easyremote.core.nodes.client import set_default_gateway

set_default_gateway("your-vps-ip:8080")  # built-in retry and circuit breaker

@remote(function_name="transcribe_audio", load_balancing=True, timeout=30)
def transcribe_audio(path):
    return path

@remote(function_name="stream_video_frames", load_balancing=True, stream=True, timeout=60)
def stream_video_frames(source):
    return source

print(transcribe_audio("meeting.wav"))
for chunk in stream_video_frames("camera://lobby"):
    print(chunk)
```

### 5. Share Remote Capabilities as an Agent Skill Pipeline

```python
from easyremote import RemoteSkill, pipeline_function

skill = RemoteSkill(
    name="voice-agent",
    gateway_address="your-vps-ip:8080",
    namespace="assistant",
)

@skill.voice(name="transcribe_live", timeout=30)
def transcribe_live(audio):
    return audio

# send this JSON to another device (queue/file/RPC)
pipeline_json = skill.export_pipeline(include_gateway=True)

# rebuild as callable pipeline on another device
remote_pipe = pipeline_function(pipeline_json)
print(remote_pipe.capabilities())
```

### 6. User-Side Remote Agent Service (Runtime Skill Install + Language)

```python
from easyremote import RemoteAgentService

service = RemoteAgentService(
    user_id="alice",
    preferred_language="zh-CN",
    gateway_address="your-vps-ip:8080",
)

# remote agent pushes new skill payload to user software
service.install_skill(pipeline_json)

# run installed skill directly
result = service.run_any("transcribe_live", b"pcm16-bytes")
print(result)
```

### 7. Remote Agent Installs New Device Capabilities (Photo/Video) at Runtime

```python
from easyremote import UserDeviceCapabilityHost

host = UserDeviceCapabilityHost(node)  # node = user-side ComputeNode
host.register_action("camera.take_photo", take_photo)
host.register_action("camera.record_video", record_video)

# payload pushed from server-side agent:
# capability metadata carries device_action mapping
host.install_skill(camera_skill_payload)
```

This registers new node functions immediately so remote agent can call them.

### 8. Node/Gateway Pressure Protection (Production Recommendation)

```python
from easyremote import Server
from easyremote.core.nodes.compute_node import NodeConfiguration, ComputeNode

# Gateway-side safeguards: total streams, per-node streams, stream buffer size
server = Server(
    port=8080,
    max_total_active_streams=512,
    max_streams_per_node=32,
    stream_response_queue_size=256,
)

# Node-side safeguards: execution concurrency and bounded queue depth
config = NodeConfiguration(
    gateway_address="your-vps-ip:8080",
    node_id="node-a",
    max_concurrent_executions=8,
    queue_size_limit=512,
)
node = ComputeNode(gateway_address=config.gateway_address, node_id=config.node_id, config=config)
```

## Success!

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
