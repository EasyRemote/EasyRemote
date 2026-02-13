---
name: easyremote-remote-agent
description: Build low-boilerplate remote agent capabilities with EasyRemote using RemoteSkill, pipeline export/import, and streaming media/voice payloads. Use when an agent needs to register remote functions in a few lines, share them across devices, or consume remote stream outputs safely with gateway/node pressure controls.
---

# EasyRemote Remote Agent Skill

Use this skill to package remote capabilities for agent reuse with minimal config.

## Build Capability Set

1. Create one `RemoteSkill` with gateway and namespace.
2. Register capabilities with `@skill.remote`, `@skill.media`, or `@skill.voice`.
3. Keep function bodies minimal; real execution is delegated to remote functions.

```python
from easyremote import RemoteSkill

skill = RemoteSkill(
    name="voice-agent",
    gateway_address="your-vps-ip:8080",
    namespace="assistant",
)

@skill.voice(name="transcribe_live", timeout=30)
def transcribe_live(audio):
    return audio

@skill.media(name="stream_frames", media_type="video/h264", stream=True, timeout=60)
def stream_frames(source):
    return source
```

## Share Across Devices

1. Export pipeline JSON from source device.
2. Transfer payload through queue/file/RPC.
3. Rebuild callable pipeline on target device.

```python
from easyremote import pipeline_function

pipeline_json = skill.export_pipeline(include_gateway=True)
remote_pipe = pipeline_function(pipeline_json)

print(remote_pipe.capabilities())
result = remote_pipe("transcribe_live", b"pcm16-bytes")
for chunk in remote_pipe("stream_frames", "camera://lobby"):
    print(chunk)
```

## User-Side Agent Service Install

Use `RemoteAgentService` when user software should install new skills at runtime.

```python
from easyremote import RemoteAgentService

service = RemoteAgentService(
    user_id="alice",
    preferred_language="zh-CN",
    gateway_address="your-vps-ip:8080",
)

service.install_skill(pipeline_json)  # pushed by remote agent
result = service.run_any("transcribe_live", b"pcm16-bytes")
```

## Install Device Abilities at Runtime (Camera/Video)

Use `UserDeviceCapabilityHost` when remote agent needs to add local hardware abilities.

```python
from easyremote import UserDeviceCapabilityHost

host = UserDeviceCapabilityHost(node)  # node = user-side ComputeNode
host.register_action("camera.take_photo", take_photo)
host.register_action("camera.record_video", record_video)

# capability metadata must include device_action mapping
host.install_skill(camera_skill_payload)
```

## Voice and Media Framing

Use `stream_audio_pcm` to chunk PCM bytes for low-latency voice flows.

```python
from easyremote import stream_audio_pcm

frames = list(stream_audio_pcm(pcm_bytes, frame_bytes=3200, sample_rate_hz=16000, channels=1))
```

Pass frames as regular function inputs when remote capability expects framed payload.

## Pressure Controls (Required for Production)

Apply limits on gateway and node to avoid stream overload.

```python
from easyremote import Server
from easyremote.core.nodes.compute_node import NodeConfiguration, ComputeNode

server = Server(
    port=8080,
    max_total_active_streams=512,
    max_streams_per_node=32,
    stream_response_queue_size=256,
)

config = NodeConfiguration(
    gateway_address="your-vps-ip:8080",
    node_id="node-a",
    max_concurrent_executions=8,
    queue_size_limit=512,
)
node = ComputeNode(gateway_address=config.gateway_address, node_id=config.node_id, config=config)
```
