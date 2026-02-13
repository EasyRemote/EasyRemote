# EasyRemote 快速开始指南

## 🚀 5分钟上手EasyRemote

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

## 🎯 基本概念

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

## 🎉 成功！

恭喜！您已经成功：
- ✅ 部署了一个分布式计算网络
- ✅ 将本地函数转为全球可访问的服务
- ✅ 实现了零冷启动的函数调用

## 🔗 下一步

- 📖 [详细安装指南](installation.md)
- 🎓 [基础教程](../tutorials/basic-usage.md)
- 🚀 [高级场景](../tutorials/advanced-scenarios.md)
- 📚 [API参考](api-reference.md)
- 💡 [更多示例](examples.md)
- 🧪 Gallery 冒烟测试：`uv run python gallery/run_smoke_tests.py`

## 💡 提示

- 确保VPS和计算节点之间网络连通
- 生产环境建议配置防火墙和安全认证
- 可以在一个网关下注册多个计算节点
- 支持多种负载均衡策略 
