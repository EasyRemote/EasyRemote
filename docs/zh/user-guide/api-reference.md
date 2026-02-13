# EasyRemote API 参考文档

## 📚 概览

EasyRemote提供了简洁而强大的API，主要包含三个核心类：
- `Server` - 网关服务器
- `ComputeNode` - 计算节点  
- `Client` - 客户端

## 🖥️ Server类

网关服务器负责协调和路由计算请求。

### 构造函数

```python
Server(host="0.0.0.0", port=8080, max_workers=10)
```

**参数：**
- `host` (str): 绑定的主机地址，默认 "0.0.0.0"
- `port` (int): 监听端口，默认 8080
- `max_workers` (int): 最大工作线程数，默认 10

**示例：**
```python
from easyremote import Server

# 基本使用
server = Server()

# 自定义配置
server = Server(host="127.0.0.1", port=9090, max_workers=20)
```

### 方法

#### start()
启动服务器（阻塞模式）

```python
server.start()
```

#### start_async()
异步启动服务器

```python
await server.start_async()
```

#### stop()
停止服务器

```python
server.stop()
```

### 属性

- `is_running` (bool): 服务器运行状态
- `node_count` (int): 已注册的节点数量
- `function_count` (int): 已注册的函数数量

## 💻 ComputeNode类

计算节点提供实际的计算服务。

### 构造函数

```python
ComputeNode(server_address, node_id=None, max_workers=5)
```

**参数：**
- `server_address` (str): 网关服务器地址，格式: "host:port"
- `node_id` (str, 可选): 节点ID，默认自动生成
- `max_workers` (int): 最大并发执行数，默认 5

**示例：**
```python
from easyremote import ComputeNode

# 基本使用
node = ComputeNode("192.168.1.100:8080")

# 自定义配置
node = ComputeNode(
    server_address="my-server.com:8080",
    node_id="gpu-node-1",
    max_workers=10
)
```

### 装饰器

#### @register
注册函数到计算节点

```python
@node.register
def function_name(param1, param2, ...):
    # 函数实现
    return result
```

**功能特性：**
- 自动序列化/反序列化参数和返回值
- 支持任意Python数据类型
- 异常处理和错误传播

**示例：**
```python
@node.register
def add_numbers(a, b):
    """简单的加法函数"""
    return a + b

@node.register
def process_data(data_list):
    """处理数据列表"""
    return [x * 2 for x in data_list]

@node.register
def ai_inference(model_input):
    """AI推理示例"""
    # 调用本地AI模型
    result = my_model.predict(model_input)
    return result
```

### 方法

#### serve()
开始提供服务（阻塞模式）

```python
node.serve()
```

#### serve_async()
异步提供服务

```python
await node.serve_async()
```

#### stop()
停止服务

```python
node.stop()
```

#### register_function()
程序化注册函数

```python
def my_function(x):
    return x * 2

node.register_function("multiply_by_2", my_function)
```

### 属性

- `is_connected` (bool): 与服务器连接状态
- `function_count` (int): 已注册函数数量
- `node_id` (str): 节点唯一标识符

## 📱 Client类

客户端用于调用远程函数。

### 构造函数

```python
Client(server_address, timeout=30)
```

**参数：**
- `server_address` (str): 网关服务器地址，格式: "host:port"
- `timeout` (int): 请求超时时间（秒），默认 30

**示例：**
```python
from easyremote import Client

# 基本使用
client = Client("192.168.1.100:8080")

# 自定义超时
client = Client("my-server.com:8080", timeout=60)
```

### 方法

#### execute()
执行远程函数

```python
result = client.execute(function_name, *args, **kwargs)
```

**参数：**
- `function_name` (str): 要调用的函数名
- `*args`: 位置参数
- `**kwargs`: 关键字参数

**返回：**
- 函数执行结果

**异常：**
- `ConnectionError`: 连接失败
- `TimeoutError`: 请求超时
- `RuntimeError`: 远程执行错误

**示例：**
```python
# 基本调用
result = client.execute("add_numbers", 10, 20)

# 传递复杂数据
data = {"input": [1, 2, 3, 4, 5]}
result = client.execute("process_data", data)

# 使用关键字参数
result = client.execute("process_text", text="Hello", language="en")
```

#### execute_async()
异步执行远程函数

```python
result = await client.execute_async(function_name, *args, **kwargs)
```

#### list_functions()
获取可用函数列表

```python
functions = client.list_functions()
```

**返回：**
```python
[
    {
        "name": "add_numbers",
        "node_id": "node-123",
        "description": "Add two numbers"
    },
    # ...
]
```

#### get_function_info()
获取函数详细信息

```python
info = client.get_function_info("add_numbers")
```

**返回：**
```python
{
    "name": "add_numbers",
    "parameters": ["a", "b"],
    "node_id": "node-123",
    "description": "Add two numbers",
    "availability": True
}
```

### 属性

- `is_connected` (bool): 连接状态
- `server_address` (str): 服务器地址

## 工具函数

### 健康检查

```python
from easyremote.utils import health_check

# 检查服务器健康状态
status = health_check("192.168.1.100:8080")
print(status)  # {'status': 'healthy', 'nodes': 3, 'functions': 10}
```

### 日志配置

```python
from easyremote.utils import setup_logging

# 配置日志级别
setup_logging(level="INFO")  # DEBUG, INFO, WARNING, ERROR
```

##  使用模式

### 基本模式

```python
# 1. 启动服务器
from easyremote import Server
server = Server(port=8080)
server.start()  # 在单独进程中运行

# 2. 注册计算节点
from easyremote import ComputeNode
node = ComputeNode("server-ip:8080")

@node.register
def my_function(data):
    return process(data)

node.serve()  # 在单独进程中运行

# 3. 调用函数
from easyremote import Client
client = Client("server-ip:8080")
result = client.execute("my_function", my_data)
```

### 异步模式

```python
import asyncio
from easyremote import Server, ComputeNode, Client

async def main():
    # 异步服务器
    server = Server()
    server_task = asyncio.create_task(server.start_async())
    
    # 异步节点
    node = ComputeNode("localhost:8080")
    
    @node.register
    async def async_function(data):
        # 异步处理
        await asyncio.sleep(1)
        return data * 2
    
    node_task = asyncio.create_task(node.serve_async())
    
    # 异步客户端
    client = Client("localhost:8080")
    result = await client.execute_async("async_function", 42)
    print(f"Result: {result}")

asyncio.run(main())
```

### 错误处理

```python
from easyremote import Client, ConnectionError, TimeoutError

client = Client("server:8080")

try:
    result = client.execute("my_function", data)
except ConnectionError:
    print("无法连接到服务器")
except TimeoutError:
    print("请求超时")
except RuntimeError as e:
    print(f"远程执行错误: {e}")
except Exception as e:
    print(f"其他错误: {e}")
```

## 🔒 安全配置

### TLS/SSL支持

```python
# 服务器启用TLS
server = Server(
    port=8080,
    tls_cert_file="server.crt",
    tls_key_file="server.key"
)

# 客户端使用TLS
client = Client(
    server_address="server:8080",
    tls_ca_file="ca.crt"
)
```

### 认证配置

```python
# 基于Token的认证
client = Client(
    server_address="server:8080",
    auth_token="your-auth-token"
)

# 基于证书的认证
client = Client(
    server_address="server:8080",
    client_cert_file="client.crt",
    client_key_file="client.key"
)
```

## 📊 监控和指标

### 启用监控

```python
from easyremote import Server
from easyremote.monitoring import enable_metrics

# 启用Prometheus指标
server = Server(port=8080)
enable_metrics(server, metrics_port=9090)
server.start()
```

### 获取状态信息

```python
# 服务器状态
server_stats = server.get_stats()
print(f"节点数: {server_stats['nodes']}")
print(f"请求数: {server_stats['total_requests']}")

# 节点状态  
node_stats = node.get_stats()
print(f"执行次数: {node_stats['executions']}")
print(f"平均耗时: {node_stats['avg_duration']}")
```

## 🔗 相关资源

- 📖 [快速开始指南](quick-start.md)
- 🎓 [使用教程](../tutorials/basic-usage.md)
- 💡 [示例代码](examples.md)
- 🏗️ [架构文档](../architecture/overview.md)
- 🐛 [故障排除](../troubleshooting.md) 