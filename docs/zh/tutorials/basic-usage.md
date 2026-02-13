# EasyRemote 基础使用教程

##  学习目标

通过本教程，您将学会：
- 理解EasyRemote的核心概念和工作原理
- 搭建完整的分布式计算环境
- 编写和部署自己的远程函数
- 掌握基本的故障排除方法

## 📚 前置知识

- Python 3.8+ 基础知识
- 基本的网络概念（IP地址、端口）
- 命令行操作经验

## 🏗️ 第一部分：理解架构

### EasyRemote的三角关系

```
     Client (调用者)
        ↓ 请求
    Server (网关)
        ↓ 路由
   ComputeNode (执行者)
```

**角色说明：**
- **Server**: 中央协调器，通常部署在VPS上
- **ComputeNode**: 实际执行计算的设备（您的电脑、服务器等）
- **Client**: 发起计算请求的应用程序

### 通信流程

1. Client向Server发送函数调用请求
2. Server查找可用的ComputeNode
3. Server将请求路由到选定的ComputeNode
4. ComputeNode执行函数并返回结果
5. Server将结果返回给Client

##  第二部分：环境搭建

### 准备工作

1. **安装EasyRemote**
```bash
pip install easyremote
```

2. **准备服务器（可选）**
- 如果您有VPS，记录IP地址
- 如果没有，可以先在本地测试

3. **网络检查**
```bash
# 检查网络连通性
ping your-server-ip

# 检查端口是否开放
telnet your-server-ip 8080
```

### 环境验证

创建测试文件验证安装：

```python
# test_installation.py
from easyremote import Server, ComputeNode, Client

print("✅ EasyRemote安装成功")
print("📦 可用组件:", [Server.__name__, ComputeNode.__name__, Client.__name__])
```

## 🎬 第三部分：第一个完整示例

### 步骤1: 启动网关服务器

创建 `my_server.py`：

```python
from easyremote import Server
import logging

# 配置日志以便调试
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print(" 启动EasyRemote网关服务器")
    
    # 创建服务器实例
    server = Server(
        host="0.0.0.0",  # 监听所有网络接口
        port=8080        # 使用8080端口
    )
    
    print("📡 服务器监听地址: 0.0.0.0:8080")
    print("🔄 等待计算节点连接...")
    
    try:
        # 启动服务器（阻塞运行）
        server.start()
    except KeyboardInterrupt:
        print("\n🛑 服务器停止")
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")

if __name__ == "__main__":
    main()
```

**运行服务器：**
```bash
python my_server.py
```

### 步骤2: 创建计算节点

创建 `my_compute_node.py`：

```python
from easyremote import ComputeNode
import time
import random

def main():
    print("💻 启动计算节点")
    
    # 连接到网关服务器
    # 替换为您的服务器IP地址
    server_address = "localhost:8080"  # 本地测试
    # server_address = "your-vps-ip:8080"  # VPS部署
    
    node = ComputeNode(server_address)
    
    # 注册简单的数学函数
    @node.register
    def add(a, b):
        """加法函数"""
        print(f"🔢 执行加法: {a} + {b}")
        return a + b
    
    @node.register
    def multiply(a, b):
        """乘法函数"""
        print(f"🔢 执行乘法: {a} × {b}")
        return a * b
    
    @node.register
    def power(base, exponent):
        """幂运算函数"""
        print(f"🔢 执行幂运算: {base} ^ {exponent}")
        result = base ** exponent
        return result
    
    # 注册数据处理函数
    @node.register
    def process_list(data_list):
        """处理数据列表"""
        print(f"📊 处理列表，长度: {len(data_list)}")
        # 计算平均值、最大值、最小值
        result = {
            "count": len(data_list),
            "average": sum(data_list) / len(data_list),
            "max": max(data_list),
            "min": min(data_list),
            "sum": sum(data_list)
        }
        return result
    
    # 注册模拟耗时任务
    @node.register
    def slow_task(duration=2):
        """模拟耗时任务"""
        print(f"⏳ 开始耗时任务，预计{duration}秒")
        time.sleep(duration)
        result = f"任务完成，耗时{duration}秒"
        print(f"✅ {result}")
        return result
    
    print(f"🔗 连接到服务器: {server_address}")
    print("📝 已注册函数:")
    print("  - add(a, b): 加法运算")
    print("  - multiply(a, b): 乘法运算") 
    print("  - power(base, exponent): 幂运算")
    print("  - process_list(data_list): 处理数据列表")
    print("  - slow_task(duration): 模拟耗时任务")
    print(" 计算节点准备就绪，等待任务...")
    
    try:
        # 开始提供服务
        node.serve()
    except KeyboardInterrupt:
        print("\n🛑 计算节点停止")
    except Exception as e:
        print(f"❌ 计算节点连接失败: {e}")
        print("💡 请检查:")
        print("  1. 网关服务器是否运行")
        print("  2. 网络连接是否正常")
        print("  3. 服务器地址是否正确")

if __name__ == "__main__":
    main()
```

**运行计算节点：**
```bash
python my_compute_node.py
```

### 步骤3: 创建客户端

创建 `my_client.py`：

```python
from easyremote import Client
import time

def test_basic_functions():
    """测试基本数学函数"""
    print("🧮 测试基本数学函数")
    
    # 连接到服务器
    server_address = "localhost:8080"  # 本地测试
    # server_address = "your-vps-ip:8080"  # VPS部署
    
    try:
        client = Client(server_address)
        print(f"🔗 连接到服务器: {server_address}")
        
        # 测试加法
        result = client.execute("add", 10, 20)
        print(f"➕ 10 + 20 = {result}")
        
        # 测试乘法
        result = client.execute("multiply", 6, 7)
        print(f"✖️ 6 × 7 = {result}")
        
        # 测试幂运算
        result = client.execute("power", 2, 8)
        print(f"🔢 2 ^ 8 = {result}")
        
        print("✅ 基本数学函数测试通过")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def test_data_processing():
    """测试数据处理功能"""
    print("\n📊 测试数据处理功能")
    
    server_address = "localhost:8080"
    
    try:
        client = Client(server_address)
        
        # 准备测试数据
        test_data = [1, 5, 3, 9, 2, 8, 4, 7, 6]
        print(f"📥 输入数据: {test_data}")
        
        # 处理数据
        result = client.execute("process_list", test_data)
        print(f" 处理结果:")
        print(f"  - 数量: {result['count']}")
        print(f"  - 平均值: {result['average']:.2f}")
        print(f"  - 最大值: {result['max']}")
        print(f"  - 最小值: {result['min']}")
        print(f"  - 总和: {result['sum']}")
        
        print("✅ 数据处理测试通过")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def test_slow_task():
    """测试耗时任务"""
    print("\n⏳ 测试耗时任务")
    
    server_address = "localhost:8080"
    
    try:
        client = Client(server_address)
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行耗时任务
        result = client.execute("slow_task", 3)
        
        # 计算实际耗时
        elapsed_time = time.time() - start_time
        
        print(f" 任务结果: {result}")
        print(f"⏱️ 实际耗时: {elapsed_time:.2f}秒")
        print("✅ 耗时任务测试通过")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def main():
    print("🧪 开始客户端测试")
    print("=" * 50)
    
    # 运行所有测试
    test_basic_functions()
    test_data_processing()
    test_slow_task()
    
    print("\n" + "=" * 50)
    print("🎉 所有测试完成！")

if __name__ == "__main__":
    main()
```

**运行客户端：**
```bash
python my_client.py
```

## 第四部分：常见操作

### 错误处理

```python
from easyremote import Client

def robust_client_example():
    client = Client("server:8080")
    
    try:
        result = client.execute("some_function", param1, param2)
        print(f"成功: {result}")
        
    except ConnectionError:
        print("❌ 无法连接到服务器")
        print("💡 请检查服务器是否运行")
        
    except TimeoutError:
        print("❌ 请求超时")
        print("💡 任务可能需要更长时间，或网络延迟")
        
    except RuntimeError as e:
        print(f"❌ 远程执行错误: {e}")
        print("💡 检查函数参数和实现")
        
    except Exception as e:
        print(f"❌ 其他错误: {e}")
```

### 动态函数注册

```python
from easyremote import ComputeNode

node = ComputeNode("server:8080")

# 方法1: 使用装饰器
@node.register
def decorated_function(x):
    return x * 2

# 方法2: 程序化注册
def my_function(x, y):
    return x + y

node.register_function("custom_name", my_function)

# 方法3: Lambda函数
node.register_function("square", lambda x: x ** 2)
```

### 参数类型处理

```python
@node.register
def handle_different_types(
    number: int,
    text: str,
    data_list: list,
    config: dict
):
    """处理不同类型的参数"""
    result = {
        "number_doubled": number * 2,
        "text_upper": text.upper(),
        "list_sum": sum(data_list),
        "config_items": len(config)
    }
    return result

# 客户端调用
result = client.execute(
    "handle_different_types",
    42,                           # int
    "hello world",               # str
    [1, 2, 3, 4, 5],            # list
    {"setting1": "value1"}       # dict
)
```

## 🐛 第五部分：故障排除

### 常见问题及解决方案

#### 1. 连接问题

**症状**: `ConnectionError: 无法连接到服务器`

**排查步骤**:
```bash
# 检查服务器是否运行
netstat -tulpn | grep :8080

# 检查网络连通性
ping server-ip

# 检查端口开放情况
telnet server-ip 8080
```

**解决方案**:
- 确保服务器程序正在运行
- 检查防火墙设置
- 验证IP地址和端口号

#### 2. 函数未找到

**症状**: `RuntimeError: 函数 'xxx' 未找到`

**排查步骤**:
```python
# 在客户端检查可用函数
client = Client("server:8080")
functions = client.list_functions()
print("可用函数:", functions)
```

**解决方案**:
- 确保计算节点正在运行
- 检查函数名拼写
- 确认函数已正确注册

#### 3. 性能问题

**症状**: 函数执行缓慢

**优化方法**:
```python
# 1. 调整超时时间
client = Client("server:8080", timeout=60)

# 2. 使用异步客户端
import asyncio

async def async_example():
    result = await client.execute_async("slow_function", data)
    return result

# 3. 批量处理
@node.register
def batch_process(items):
    """批量处理而非单个处理"""
    return [process_item(item) for item in items]
```

### 调试技巧

#### 启用详细日志

```python
import logging

# 设置日志级别
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 或者只启用EasyRemote日志
logger = logging.getLogger('easyremote')
logger.setLevel(logging.DEBUG)
```

#### 监控网络流量

```bash
# 使用netstat监控连接
watch -n 1 "netstat -an | grep :8080"

# 使用tcpdump捕获网络包
sudo tcpdump -i any port 8080
```

##  第六部分：最佳实践

### 1. 代码组织

```python
# 推荐的项目结构
project/
├── server.py          # 网关服务器
├── nodes/            # 计算节点
│   ├── math_node.py  # 数学计算节点
│   ├── ai_node.py    # AI推理节点
│   └── data_node.py  # 数据处理节点
├── clients/          # 客户端应用
│   ├── web_app.py    # Web应用
│   └── cli_tool.py   # 命令行工具
└── config/           # 配置文件
    └── settings.py   # 配置设置
```

### 2. 错误处理策略

```python
@node.register
def robust_function(data):
    """健壮的函数实现"""
    try:
        # 输入验证
        if not isinstance(data, (list, tuple)):
            raise ValueError("输入必须是列表或元组")
        
        if len(data) == 0:
            raise ValueError("输入不能为空")
        
        # 核心逻辑
        result = process_data(data)
        
        # 输出验证
        if result is None:
            raise RuntimeError("处理失败")
        
        return {
            "success": True,
            "result": result,
            "metadata": {
                "processed_items": len(data),
                "timestamp": time.time()
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }
```

### 3. 性能优化

```python
# 1. 使用缓存
from functools import lru_cache

@node.register
@lru_cache(maxsize=100)
def cached_expensive_function(param):
    """缓存昂贵的计算结果"""
    return expensive_computation(param)

# 2. 批量处理
@node.register
def batch_process(items):
    """批量处理提高效率"""
    results = []
    for item in items:
        result = process_single_item(item)
        results.append(result)
    return results

# 3. 异步处理
import asyncio

@node.register
async def async_function(data):
    """异步处理提高并发"""
    result = await async_process(data)
    return result
```

## 🎓 第七部分：进阶学习

### 下一步学习路径

1. ** [高级场景教程](advanced-scenarios.md)** - 学习复杂应用场景
2. **🏗️ [架构深入](../architecture/overview.md)** - 理解系统架构原理
3. **📚 [API完整参考](../user-guide/api-reference.md)** - 掌握所有API功能
4. **💡 [示例代码库](../user-guide/examples.md)** - 学习实际应用案例

### 实践项目建议

1. **个人AI助手**: 部署本地AI模型为全球服务
2. **分布式爬虫**: 多节点协同数据采集
3. **实时监控系统**: 多地点数据收集和分析
4. **协同计算平台**: 多用户共享计算资源

## 💬 获取帮助

### 社区资源

- 🐛 **问题报告**: [GitHub Issues](https://github.com/Qingbolan/EasyCompute/issues)
- 💬 **技术讨论**: [GitHub Discussions](https://github.com/Qingbolan/EasyCompute/discussions)
- 📧 **邮件支持**: [silan.hu@u.nus.edu](mailto:silan.hu@u.nus.edu)

### 贡献方式

- 📝 改进文档和教程
- 🐛 报告和修复Bug
- 💡 提出新功能建议
- 🌟 分享使用案例

---

**🎉 恭喜您完成了EasyRemote基础教程！**

您现在已经掌握了EasyRemote的核心概念和基本使用方法。继续探索高级功能，构建属于您的分布式计算网络吧！ 