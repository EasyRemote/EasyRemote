# EasyRemote 快速开始指南

##  5分钟上手EasyRemote

EasyRemote让您能够以最简单的方式构建分布式计算网络。只需要12行代码，您就可以将本地函数部署为全球可访问的服务。

## 📦 安装

```bash
pip install easyremote
```

如果是仓库本地开发/测试，使用 uv：

```bash
uv sync
uv run pytest -q
```

##  基本概念

EasyRemote基于三个核心组件：

- **Server (网关服务器)**: 协调和路由请求，通常部署在VPS上
- **ComputeNode (计算节点)**: 提供实际计算资源的设备
- **Client (客户端)**: 调用远程函数的应用程序

## ⚡ 快速示例

### 1. 启动网关服务器 (VPS上)

```python
# vps_server.py
from easyremote import Server

# 启动网关服务器
server = Server(port=8080)
server.start()
```

### 2. 注册计算节点 (您的设备上)

```python
# compute_node.py
from easyremote import ComputeNode

# 连接到网关服务器
node = ComputeNode("your-vps-ip:8080")

# 注册一个简单函数
@node.register
def add_numbers(a, b):
    return a + b

# 注册AI推理函数
@node.register
def ai_inference(text):
    # 这里可以调用您的本地AI模型
    return f"AI处理结果: {text}"

# 开始提供服务
node.serve()
```

### 3. 调用远程函数 (任何地方)

```python
# client.py
from easyremote import Client

# 连接到网关服务器
client = Client("your-vps-ip:8080")

# 调用远程函数
result1 = client.execute("add_numbers", 10, 20)
print(f"计算结果: {result1}")  # 输出: 30

result2 = client.execute("ai_inference", "Hello World")
print(f"AI结果: {result2}")  # 输出: AI处理结果: Hello World
```

### 4. 几行代码升级为稳定远程服务 + 流式调用

```python
from easyremote import remote
from easyremote.core.nodes.client import set_default_gateway

set_default_gateway("your-vps-ip:8080")  # 内置重试与熔断

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

### 5. 远程能力导出为 Agent Skill 管道（跨设备复用）

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

# 将 JSON 通过消息队列/文件/RPC 发送到另一台设备
pipeline_json = skill.export_pipeline(include_gateway=True)

# 在另一台设备重建为可调用管道函数
remote_pipe = pipeline_function(pipeline_json)
print(remote_pipe.capabilities())
```

### 6. 用户侧远程 Agent 服务（运行时安装技能 + 语言偏好）

```python
from easyremote import RemoteAgentService

service = RemoteAgentService(
    user_id="alice",
    preferred_language="zh-CN",
    gateway_address="your-vps-ip:8080",
)

# 远程 agent 将新技能管道推送到用户软件并即时安装
service.install_skill(pipeline_json)

# 直接运行已安装能力
result = service.run_any("transcribe_live", b"pcm16-bytes")
print(result)
```

### 7. 远程 Agent 运行时安装新设备能力（拍照/录视频）

```python
from easyremote import UserDeviceCapabilityHost

host = UserDeviceCapabilityHost(node)  # node = 用户侧 ComputeNode
host.register_action("camera.take_photo", take_photo)
host.register_action("camera.record_video", record_video)

# 服务端 agent 下发技能 payload（metadata.device_action 指定本地动作）
host.install_skill(camera_skill_payload)
```

安装后会立即在节点注册新函数，远程 agent 可直接调用。

### 8. 节点/网关压力保护（生产建议）

```python
from easyremote import Server
from easyremote.core.nodes.compute_node import NodeConfiguration, ComputeNode

# 网关侧：限制总流数、单节点流数、流缓冲区大小
server = Server(
    port=8080,
    max_total_active_streams=512,
    max_streams_per_node=32,
    stream_response_queue_size=256,
)

# 节点侧：限制并发执行与排队深度（超出会快速拒绝）
config = NodeConfiguration(
    gateway_address="your-vps-ip:8080",
    node_id="node-a",
    max_concurrent_executions=8,
    queue_size_limit=512,
)
node = ComputeNode(gateway_address=config.gateway_address, node_id=config.node_id, config=config)
```

## 成功！

恭喜！您已经成功：
- ✅ 部署了一个分布式计算网络
- ✅ 将本地函数转为全球可访问的服务
- ✅ 实现了零冷启动的函数调用

## 🔗 下一步

- 📖 [详细安装指南](installation.md)
- 🎓 [基础教程](../tutorials/basic-usage.md)
-  [高级场景](../tutorials/advanced-scenarios.md)
- 📚 [API参考](api-reference.md)
- 💡 [更多示例](examples.md)
- 🧪 Gallery 冒烟测试：`uv run python gallery/run_smoke_tests.py`

## 💡 提示

- 确保VPS和计算节点之间网络连通
- 生产环境建议配置防火墙和安全认证
- 可以在一个网关下注册多个计算节点
- 支持多种负载均衡策略 
