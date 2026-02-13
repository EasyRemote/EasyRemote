# EasyRemote 安装指南

## 📋 系统要求

### 最低要求
- Python 3.9+
- 操作系统: Windows, macOS, Linux
- 内存: 512MB
- 网络: 稳定的互联网连接

### 推荐配置
- Python 3.9+
- 内存: 2GB+
- CPU: 多核处理器
- 网络: 低延迟网络环境

## 📦 安装方法

### 方法1: 使用pip安装 (推荐)

```bash
pip install easyremote
```

### 方法2: 使用pip安装指定版本

```bash
# 安装最新版本
pip install easyremote --upgrade

# 安装特定版本
pip install easyremote==1.0.0
```

### 方法3: 从源码安装

```bash
# 克隆仓库
git clone https://github.com/Qingbolan/EasyCompute.git
cd EasyCompute

# 安装依赖并安装
pip install -e .
```

## 依赖管理

### 核心依赖
```bash
# EasyRemote的核心依赖会自动安装
pip install grpcio>=1.50.0
pip install protobuf>=4.21.0
```

### 可选依赖
#### 内置扩展包（extras）
```bash
# GPU 指标采集（可选）
pip install "easyremote[gpu]"

# Protobuf/gRPC 代码生成工具（可选）
pip install "easyremote[build]"
```

#### AI/ML工作负载
```bash
# 用于AI推理工作负载
pip install torch torchvision
pip install tensorflow
pip install numpy pandas
```

#### 高级功能
```bash
# 用于监控和日志
pip install prometheus-client
pip install structlog

# 用于加密和安全
pip install cryptography
```

## 🐳 Docker安装

### 拉取官方镜像
```bash
docker pull easyremote/easyremote:latest
```

### 运行网关服务器
```bash
docker run -p 8080:8080 easyremote/easyremote:latest server
```

### 运行计算节点
```bash
docker run easyremote/easyremote:latest node --gateway your-gateway:8080
```

## 🏗️ 开发环境安装

### 推荐流程（贡献者使用 uv）

```bash
uv sync
uv run ruff check easyremote tests gallery examples --output-format=full
uv run pytest -q
uv run python gallery/run_smoke_tests.py
```

### 创建虚拟环境
```bash
# 使用venv
python -m venv easyremote-env
source easyremote-env/bin/activate  # Linux/macOS
# easyremote-env\Scripts\activate   # Windows

# 使用conda
conda create -n easyremote python=3.9
conda activate easyremote
```

### 安装开发依赖
```bash
pip install easyremote[dev]

# 如果使用 uv，安装项目 + 默认 dev/test 分组
uv sync

# 按需安装扩展能力
uv sync --extra gpu --extra build

# 或者手动安装开发工具
pip install pytest
pip install black
pip install flake8
pip install mypy
```

## ✅ 验证安装

### 检查版本
```bash
python -c "import easyremote; print(easyremote.__version__)"
```

### 运行基本测试
```python
# test_installation.py
from easyremote import Server, ComputeNode, Client

print("✅ EasyRemote导入成功")
print("✅ 所有核心组件可用")

# 测试基本功能
try:
    server = Server(port=8081)
    print("✅ Server创建成功")
    
    node = ComputeNode("localhost:8081")
    print("✅ ComputeNode创建成功")
    
    client = Client("localhost:8081") 
    print("✅ Client创建成功")
    
    print("🎉 安装验证完成!")
except Exception as e:
    print(f"❌ 安装验证失败: {e}")
```

## 🔍 故障排除

### 常见问题

#### 1. 导入错误
```bash
# 问题: ModuleNotFoundError: No module named 'easyremote'
# 解决: 确认正确安装
pip list | grep easyremote
pip install easyremote --force-reinstall
```

#### 2. gRPC依赖问题
```bash
# 问题: grpc模块相关错误
# 解决: 重新安装grpc依赖
pip uninstall grpcio
pip install grpcio --no-cache-dir

# 仅在需要重新生成 proto 代码时安装 grpcio-tools
pip install "easyremote[build]"
```

#### 3. 网络连接问题
```bash
# 问题: 无法连接到网关服务器
# 解决: 检查网络和防火墙设置
telnet your-gateway-ip 8080
```

#### 4. 权限问题
```bash
# 问题: Permission denied
# 解决: 使用用户安装
pip install --user easyremote
```

### 平台特定问题

#### Windows
```powershell
# 如果遇到长路径问题
git config --system core.longpaths true

# 如果遇到Visual Studio构建工具问题
# 安装 Microsoft C++ Build Tools
```

#### macOS
```bash
# 如果遇到SSL证书问题
/Applications/Python\ 3.x/Install\ Certificates.command

# 如果遇到权限问题
sudo chown -R $(whoami) /usr/local/lib/python3.x/site-packages
```

#### Linux
```bash
# 如果遇到编译问题，安装构建工具
sudo apt-get install build-essential
sudo apt-get install python3-dev

# CentOS/RHEL
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

## 🎓 下一步

安装完成后，您可以：

1. 📖 [快速开始](quick-start.md) - 5分钟上手教程
2. 🎓 [基础教程](../tutorials/basic-usage.md) - 详细学习指南
3. 📚 [API参考](api-reference.md) - 完整API文档
4. 💡 [示例代码](examples.md) - 实际使用案例

## 🆘 获取帮助

如果您在安装过程中遇到问题：

- 🐛 [GitHub Issues](https://github.com/Qingbolan/EasyCompute/issues)
- 💬 [社区讨论](https://github.com/Qingbolan/EasyCompute/discussions)
- 📧 [邮件支持](mailto:silan.hu@u.nus.edu) 
